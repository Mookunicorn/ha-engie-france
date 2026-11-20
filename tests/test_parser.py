import importlib.util
import json
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "parser", ROOT.parent / "custom_components" / "engie_france" / "parser.py"
)
parser = importlib.util.module_from_spec(spec)
sys.modules["parser"] = parser
spec.loader.exec_module(parser)

DATA = json.loads((ROOT / "fixtures" / "historique_prix.json").read_text())


def test_latest_entry_is_selected():
    p = parser.parse_history(DATA, date(2026, 11, 20))
    assert p.date_effet == date(2026, 8, 1)
    assert p.prix_kwh_indicatif == pytest.approx(0.22628095)
    assert p.abonnement_annuel == pytest.approx(188.1078)
    assert p.fourniture_kwh == pytest.approx(0.161268)
    assert p.obligations_kwh == pytest.approx(0.014196)


def test_previous_entry_before_effect_date():
    p = parser.parse_history(DATA, date(2026, 7, 15))
    assert p.date_effet == date(2026, 7, 1)
    assert p.prix_kwh_indicatif == pytest.approx(0.22504289)


def test_slot_prices():
    p = parser.parse_history(DATA, date(2026, 11, 20))
    assert p.prix_kwh_slot("HPB") == pytest.approx(0.161268 + 0.014196 + 0.02052)
    assert p.prix_kwh_slot("HPH") == pytest.approx(0.161268 + 0.014196 + 0.09264)


def test_estimate_matches_october_invoice():
    # Real October invoice: 65.09 EUR for 334 kWh = 0.19488 EUR/kWh (low season)
    p = parser.parse_history(DATA, date(2026, 10, 15))
    assert p.prix_kwh_estime(date(2026, 10, 15), 82) == pytest.approx(0.1949, abs=0.0005)


def test_estimate_high_season():
    p = parser.parse_history(DATA, date(2026, 11, 20))
    est = p.prix_kwh_estime(date(2026, 11, 20), 82)
    assert est == pytest.approx(0.2603, abs=0.0005)
    assert p.prix_kwh_estime(date(2026, 11, 20), 100) == pytest.approx(p.prix_kwh_slot("HPH"))
    assert p.prix_kwh_estime(date(2026, 11, 20), 0) == pytest.approx(p.prix_kwh_slot("HCH"))


def test_subscription_prorata_matches_invoice():
    p = parser.parse_history(DATA, date(2026, 10, 15))
    assert round(p.abonnement_annuel * 31 / 365, 2) == 15.98


@pytest.mark.parametrize("bad", [{}, {"electricite": []}, {"electricite": [{"DateEffet": "x"}]}, None])
def test_bad_payload(bad):
    with pytest.raises(parser.ParseError):
        parser.parse_history(bad, date(2026, 11, 20))
