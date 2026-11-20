"""Pure-Python parsing of the Engie "historiquePrix" response (no HA dependency)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

HIGH_SEASON_MONTHS = frozenset({11, 12, 1, 2, 3})  # default TURPE high season
SLOTS = ("HPB", "HCB", "HPH", "HCH")


class ParseError(Exception):
    """Raised when the payload does not look like a price history."""


@dataclass(frozen=True)
class EngiePrices:
    """Prices in force on a given date (all TTC)."""

    date_effet: date
    offre: str
    raison: str
    abonnement_annuel: float  # EUR / year (supply + network)
    prix_kwh_indicatif: float  # EUR / kWh, Engie's own average
    fourniture_kwh: float
    obligations_kwh: float
    acheminement: dict[str, float] = field(default_factory=dict)  # per slot

    @property
    def abonnement_mensuel(self) -> float:
        return self.abonnement_annuel / 12

    @property
    def abonnement_journalier(self) -> float:
        return self.abonnement_annuel / 365

    def prix_kwh_slot(self, slot: str) -> float:
        """Full price of one kWh in a given network slot (HPB/HCB/HPH/HCH)."""
        return self.fourniture_kwh + self.obligations_kwh + self.acheminement[slot]

    def prix_kwh_estime(self, today: date, part_hp: float) -> float:
        """Price of a kWh for the current season, weighted by the share of peak hours."""
        saison = "H" if today.month in HIGH_SEASON_MONTHS else "B"
        hp = self.prix_kwh_slot(f"HP{saison}")
        hc = self.prix_kwh_slot(f"HC{saison}")
        share = min(max(part_hp, 0.0), 100.0) / 100
        return hp * share + hc * (1 - share)


def _f(value: Any) -> float:
    return float(str(value).replace(",", "."))


def _entry_to_prices(entry: dict[str, Any]) -> EngiePrices:
    d = datetime.strptime(entry["DateEffet"], "%Y%m%d").date()
    return EngiePrices(
        date_effet=d,
        offre=entry.get("Libelle") or entry.get("Offre") or "",
        raison=entry.get("Raison") or "",
        abonnement_annuel=_f(entry["TotalAbonnement"][0]["PrixTTC"]),
        prix_kwh_indicatif=_f(entry["TotalConsommation"][0]["PrixTTC"]),
        fourniture_kwh=_f(entry["Consommation"][0]["PrixTTC"]),
        obligations_kwh=_f(entry["Obligation"][0]["PrixTTC"]),
        acheminement={
            c["IdCadran"]: _f(c["PrixTTC"]) for c in entry["ConsommationAcheminement"]
        },
    )


def parse_history(payload: Any, today: date) -> EngiePrices:
    """Return the prices in force on `today` (latest DateEffet <= today)."""
    try:
        entries = payload["electricite"]
        if not entries:
            raise ParseError("empty electricity history")
        dated = sorted(entries, key=lambda e: e["DateEffet"])
        past = [e for e in dated if datetime.strptime(e["DateEffet"], "%Y%m%d").date() <= today]
        prices = _entry_to_prices((past or dated)[-1 if past else 0])
        missing = [s for s in SLOTS if s not in prices.acheminement]
        if missing:
            raise ParseError(f"missing network slots: {missing}")
        return prices
    except ParseError:
        raise
    except (KeyError, IndexError, TypeError, ValueError) as err:
        raise ParseError(f"unexpected payload: {err!r}") from err
