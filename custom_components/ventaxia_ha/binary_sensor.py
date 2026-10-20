"""Maintenance warnings correlated with this user's firmware and app messages."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .econiq import CONF_DEVICE_TYPE, ECONIQ
from .econiq_entities import EconiqEntity
from .econiq_status import CONFIRMED_WARNING_BITS, alarm_mask


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get(CONF_DEVICE_TYPE) == ECONIQ:
        coordinator = hass.data[DOMAIN][entry.entry_id]
        async_add_entities(
            EconiqMaintenanceAlert(coordinator, bit, name)
            for bit, name in CONFIRMED_WARNING_BITS.items()
        )


class EconiqMaintenanceAlert(EconiqEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, bit, name):
        super().__init__(coordinator, name)
        self.bit = bit

    @property
    def is_on(self):
        mask = alarm_mask(self.coordinator.cache.values.get("mdet/warns"))
        return None if mask is None else bool(mask & (1 << self.bit))

    @property
    def extra_state_attributes(self):
        return {"warning_code": f"W-{self.bit + 1:02d}"}
