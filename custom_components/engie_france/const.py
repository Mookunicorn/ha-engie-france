"""Constants for the Engie France integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "engie_france"

CONF_COOKIE = "cookie"
CONF_PART_HP = "part_heures_pleines"

DEFAULT_PART_HP = 82  # % of kWh in "heures pleines" (estimated from a real invoice)

BASE_URL = "https://particuliers.engie.fr"
HISTORY_PATH = "/mbe-back-ws/api/private/v1/historiquePrix?origin=maconso"
REFERER = BASE_URL + "/espace-client/consommations/historique-prix-electricite.html"

UPDATE_INTERVAL = timedelta(hours=24)  # the site is queried once a day
CACHE_MAX_AGE = timedelta(hours=20)  # avoid a second call after a restart
STORAGE_VERSION = 1
