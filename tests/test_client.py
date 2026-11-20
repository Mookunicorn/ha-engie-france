"""Tests of the login flow and API client against a fake Engie/Okta server."""
import importlib
import json
import sys
import types
from pathlib import Path

import aiohttp
import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer

ROOT = Path(__file__).resolve().parent
CC = ROOT.parent / "custom_components" / "engie_france"
pkg = types.ModuleType("engie_france")  # avoid running __init__.py (needs Home Assistant)
pkg.__path__ = [str(CC)]
sys.modules["engie_france"] = pkg
api = importlib.import_module("engie_france.api")

HISTORY = json.loads((ROOT / "fixtures" / "historique_prix.json").read_text())
EMAIL, PASSWORD, CODE = "me@example.com", "s3cret", "123456"


class FakeEngie:
    def __init__(self):
        self.sessions: set[str] = set()
        self.authn_calls = 0
        self.last_state = ""
        self.app = web.Application()
        r = self.app.router
        r.add_post("/okta/api/v1/authn", self.authn)
        r.add_post("/okta/api/v1/authn/factors/{fid}/verify", self.verify)
        r.add_get("/dgp/oauth/v1/authorize", self.dgp_authorize)
        r.add_get("/okta/oauth2/x/v1/authorize", self.okta_authorize)
        r.add_get("/dgp/oauth/v1/callback", self.dgp_callback)
        r.add_get("/site/auth-ws/auth-callback", self.site_callback)
        r.add_post("/site/digital-common-ws/api-management/creation-cookie", self.creation_cookie)
        r.add_get("/site/mbe-back-ws/api/private/v1/historiquePrix", self.history)

    def base(self, request, prefix):
        return f"http://localhost:{request.url.port}{prefix}"

    async def authn(self, request):
        self.authn_calls += 1
        body = await request.json()
        if body["username"] != EMAIL or body["password"] != PASSWORD:
            return web.json_response({"errorCode": "E0000004"}, status=401)
        if request.cookies.get("DT") == "dev":
            return web.json_response({"status": "SUCCESS", "sessionToken": "sess-tok"})
        href = lambda fid: self.base(request, f"/okta/api/v1/authn/factors/{fid}/verify")
        return web.json_response(
            {
                "status": "MFA_REQUIRED",
                "stateToken": "st1",
                "_embedded": {
                    "factors": [
                        {"id": "f1", "factorType": "email", "_links": {"verify": {"href": href("f1")}}},
                        {"id": "f2", "factorType": "sms", "_links": {"verify": {"href": href("f2")}}},
                    ]
                },
            }
        )

    async def verify(self, request):
        body = await request.json()
        if "passCode" not in body:
            assert body["stateToken"] == "st1"
            return web.json_response({"status": "MFA_CHALLENGE", "stateToken": "st2"})
        assert body["stateToken"] == "st2"
        if body["passCode"] != CODE:
            return web.json_response({"errorCode": "E0000068"}, status=403)
        resp = web.json_response({"status": "SUCCESS", "sessionToken": "sess-tok"})
        if request.query.get("rememberDevice") == "true":
            resp.set_cookie("DT", "dev", path="/")
        return resp

    async def dgp_authorize(self, request):
        q = request.query
        assert q["client_id"] == api.OAUTH_CLIENT_ID and q["sessionToken"] == "sess-tok"
        assert q["redirect_uri"].endswith("/auth-ws/auth-callback") and q["response_type"] == "code"
        self.last_state = q["state"]
        raise web.HTTPFound(self.base(request, "/okta/oauth2/x/v1/authorize") + "?sessionToken=sess-tok")

    async def okta_authorize(self, request):
        raise web.HTTPFound(self.base(request, "/dgp/oauth/v1/callback") + "?code=c&state=s")

    async def dgp_callback(self, request):
        raise web.HTTPFound(self.base(request, "/site/auth-ws/auth-callback") + "?code=c&state=s")

    async def site_callback(self, request):
        resp = web.json_response({"statut": "OK", "data": None, "erreur": None})
        resp.set_cookie("SESSION", "sid", path="/")
        self.sessions.add("sid")
        return resp

    async def creation_cookie(self, request):
        return web.json_response({"status": {"code": "OK"}})

    async def history(self, request):
        if request.cookies.get("SESSION") in self.sessions:
            return web.json_response(HISTORY)
        return web.json_response({"error": "unauthorized"}, status=401)


@pytest_asyncio.fixture
async def fake(monkeypatch):
    f = FakeEngie()
    server = TestServer(f.app)
    await server.start_server()
    port = server.port
    monkeypatch.setattr(api, "BASE_URL", f"http://localhost:{port}/site")
    monkeypatch.setattr(api, "OKTA_URL", f"http://localhost:{port}/okta")
    monkeypatch.setattr(api, "DGP_URL", f"http://localhost:{port}/dgp")
    monkeypatch.setattr(api, "CALLBACK_URL", f"http://localhost:{port}/site/auth-ws/auth-callback")
    yield f
    await server.close()


@pytest_asyncio.fixture
async def make_client():
    sessions = []

    def factory(password=PASSWORD):
        s = aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar())
        sessions.append(s)
        return api.EngieClient(s, EMAIL, password)

    yield factory
    for s in sessions:
        await s.close()


async def login_with_code(client):
    assert await client.async_login() is api.LoginState.MFA_REQUIRED
    await client.async_send_code("sms")
    await client.async_verify_code(CODE)


async def test_full_login_with_code(fake, make_client):
    c = make_client()
    assert await c.async_login() is api.LoginState.MFA_REQUIRED
    assert c.factor_types == ["sms", "email"]  # sms first
    await c.async_send_code("sms")
    with pytest.raises(api.EngieInvalidCode):
        await c.async_verify_code("000000")
    await c.async_verify_code(CODE)
    assert fake.last_state.endswith("|parcours=MFA_CHALLENGE|kml=true")
    data = await c.async_fetch_history()
    assert data["electricite"][-1]["DateEffet"] == "20260801"
    assert {x["name"] for x in c.export_cookies()} >= {"DT", "SESSION"}


async def test_saved_session_needs_no_login(fake, make_client):
    c = make_client()
    await login_with_code(c)
    saved = c.export_cookies()
    fake.authn_calls = 0
    c2 = make_client()
    c2.import_cookies(saved)
    assert (await c2.async_fetch_history())["gaz"] == []
    assert fake.authn_calls == 0


async def test_expired_session_relogs_without_code_on_remembered_device(fake, make_client):
    c = make_client()
    await login_with_code(c)
    only_device = [x for x in c.export_cookies() if x["name"] == "DT"]
    fake.sessions.clear()
    c2 = make_client()
    c2.import_cookies(only_device)
    data = await c2.async_fetch_history()
    assert data["electricite"]
    assert fake.authn_calls == 2  # one for c, one for c2


async def test_unknown_device_requires_code(fake, make_client):
    c = make_client()
    with pytest.raises(api.EngieMfaRequired):
        await c.async_fetch_history()


async def test_bad_password(fake, make_client):
    c = make_client(password="nope")
    with pytest.raises(api.EngieAuthError) as exc:
        await c.async_login()
    assert not isinstance(exc.value, api.EngieMfaRequired)


async def test_unreachable(monkeypatch, make_client):
    monkeypatch.setattr(api, "OKTA_URL", "http://localhost:1")
    c = make_client()
    with pytest.raises(api.EngieConnectionError):
        await c.async_login()
