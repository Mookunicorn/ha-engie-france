"""Constants for the Engie France integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "engie_france"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_STORAGE_KEY = "storage_key"
CONF_FACTOR = "factor"
CONF_CODE = "code"
CONF_PART_HP = "part_heures_pleines"

DEFAULT_PART_HP = 82  # % of kWh in "heures pleines" (estimated from a real invoice)

BASE_URL = "https://particuliers.engie.fr"
OKTA_URL = "https://identite-prd.engie.fr"
DGP_URL = "https://api.dgp.engie.fr"

HISTORY_PATH = "/mbe-back-ws/api/private/v1/historiquePrix?origin=maconso"
REFERER = BASE_URL + "/espace-client/consommations/historique-prix-electricite.html"
CALLBACK_URL = BASE_URL + "/auth-ws/auth-callback"
OAUTH_CLIENT_ID = "gAeNcRIOkLBQxK0HeZu8JDIPgVn9Pb8n"
OAUTH_SCOPE = "openid profile idb2c apihour:read apihour:write"
# "kml" = "keep me logged in" in the site's own state parameter.
STATE_SUFFIX = "|parcours=MFA_CHALLENGE|kml=true"

UPDATE_INTERVAL = timedelta(hours=24)  # the site is queried once a day
CACHE_MAX_AGE = timedelta(hours=20)  # avoid a second call after a restart
STORAGE_VERSION = 1
