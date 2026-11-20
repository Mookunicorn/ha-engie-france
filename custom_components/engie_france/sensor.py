"""Sensors exposing Engie prices (EUR/kWh and EUR)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_PART_HP, DEFAULT_PART_HP, DOMAIN
from .coordinator import EngieCoordinator
from .parser import EngiePrices

PRICE_UNIT = "EUR/kWh"


@dataclass(frozen=True, kw_only=True)
class EngieSensorDescription(SensorEntityDescription):
    value_fn: Callable[[EngiePrices, date, float], Any]


def _slot(slot: str) -> Callable[[EngiePrices, date, float], float]:
    return lambda p, _d, _h: round(p.prix_kwh_slot(slot), 5)


def _price(key: str, fn: Callable[[EngiePrices, date, float], Any]) -> EngieSensorDescription:
    return EngieSensorDescription(
        key=key, translation_key=key, native_unit_of_measurement=PRICE_UNIT,
        suggested_display_precision=4, value_fn=fn,
    )


def _eur(key: str, fn: Callable[[EngiePrices, date, float], Any], digits: int) -> EngieSensorDescription:
    return EngieSensorDescription(
        key=key, translation_key=key, native_unit_of_measurement="EUR",
        device_class=SensorDeviceClass.MONETARY, suggested_display_precision=digits,
        value_fn=fn,
    )


SENSORS: tuple[EngieSensorDescription, ...] = (
    _price("prix_kwh_estime", lambda p, d, h: round(p.prix_kwh_estime(d, h), 5)),
    _price("prix_kwh_indicatif", lambda p, _d, _h: p.prix_kwh_indicatif),
    _price("prix_kwh_fourniture", lambda p, _d, _h: p.fourniture_kwh),
    _price("prix_kwh_obligations", lambda p, _d, _h: p.obligations_kwh),
    _price("prix_kwh_hpb", _slot("HPB")),
    _price("prix_kwh_hcb", _slot("HCB")),
    _price("prix_kwh_hph", _slot("HPH")),
    _price("prix_kwh_hch", _slot("HCH")),
    _eur("abonnement_annuel", lambda p, _d, _h: p.abonnement_annuel, 2),
    _eur("abonnement_mensuel", lambda p, _d, _h: round(p.abonnement_mensuel, 4), 2),
    _eur("abonnement_journalier", lambda p, _d, _h: round(p.abonnement_journalier, 4), 3),
    EngieSensorDescription(
        key="date_effet", translation_key="date_effet",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda p, _d, _h: p.date_effet,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator: EngieCoordinator = entry.runtime_data
    async_add_entities(EngieSensor(coordinator, entry, d) for d in SENSORS)


class EngieSensor(CoordinatorEntity[EngieCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: EngieSensorDescription

    def __init__(self, coordinator, entry, description: EngieSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Engie France",
            manufacturer="Engie",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        part_hp = float(self._entry.options.get(CONF_PART_HP, DEFAULT_PART_HP))
        return self.entity_description.value_fn(
            self.coordinator.data, dt_util.now().date(), part_hp
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        p = self.coordinator.data
        return {"offre": p.offre, "en_vigueur_depuis": p.date_effet.isoformat(), "raison": p.raison}
