"""Econiq entities use neutral topic names where semantics are unconfirmed."""

from homeassistant.components.button import ButtonEntity
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import Entity, EntityCategory

from .econiq_status import (
    ALARM_TOPICS,
    CONFIRMED_WARNING_BITS,
    ENUM_TOPICS,
    WARNING_STATES,
    decode_alarm,
    enum_state,
    warning_state,
)
from .econiq_topics import channel_present

# key, topic, native unit, device class. fd and filter readings keep unknown units.
SENSORS = [
    *((f"t{i}", f"io/t{i}", "°C", SensorDeviceClass.TEMPERATURE) for i in range(1, 5)),
    ("erh", "io/erh/val", "%", SensorDeviceClass.HUMIDITY),
    ("irh", "io/irh/val", "%", SensorDeviceClass.HUMIDITY),
    # Measurements retained by the parser but kept unit-neutral until confirmed.
    ("eco2", "io/eco2/val", None, None),
    ("ico2", "io/ico2/val", None, None),
    ("zone2_co2", "zone/2/co2", None, None),
    ("zone2_t", "zone/2/t", None, None),
    ("sn1_rh", "sn/1/rh", None, None),
    ("power", "mdet/pwr", "W", SensorDeviceClass.POWER),
    ("vent_cm", "vent/cm", None, None),
    ("vent_saq", "vent/saq", None, None),
    ("vent_maxaf", "vent/maxaf", None, None),
    *(
        (f"{fan}_{field}", f"vent/{fan}/{field}", unit, cls)
        for fan in ("afs", "afe")
        for field, unit, cls in (
            ("rpm", "rpm", None),
            ("pwr", "W", SensorDeviceClass.POWER),
            ("fm", "L/s", SensorDeviceClass.VOLUME_FLOW_RATE),
            ("fd", None, None),
            ("pwm", None, None),
            ("dr", "h", SensorDeviceClass.DURATION),
        )
    ),
    *(
        (f"filter{i}_{field}", f"vent/filter{i}/{field}", None, None)
        for i in (1, 2)
        for field in ("pa", "lr")
    ),
    ("faults", "mdet/faults", None, None),
    ("warnings", "mdet/warns", None, None),
    ("notifications", "mdet/noti", None, None),
    ("mode", "vent/caf", None, None),
    ("override", "vent/cor", None, None),
    ("rssi", "mdet/wifi/sta", "dBm", SensorDeviceClass.SIGNAL_STRENGTH),
]


class EconiqEntity(Entity):
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{key}"
        self._attr_translation_key = key

    @property
    def device_info(self):
        return self.coordinator.device_info

    @property
    def available(self):
        return self.coordinator.available

    async def async_added_to_hass(self):
        self.coordinator.add_update_callback(self.async_write_ha_state)
        self.async_on_remove(
            lambda: self.coordinator.remove_update_callback(self.async_write_ha_state)
        )


class EconiqSensor(EconiqEntity, SensorEntity):
    def __init__(self, coordinator, key, topic, unit, device_class):
        super().__init__(coordinator, key)
        self.topic = topic
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        if topic in ENUM_TOPICS:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = [*ENUM_TOPICS[topic].values(), "unknown_code"]
        if topic in set(ALARM_TOPICS.values()):
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = (
                WARNING_STATES if topic == "mdet/warns" else ["clear", "active"]
            )
        if key in {
            "afs_dr",
            "afe_dr",
            "afs_pwm",
            "afe_pwm",
            "vent_cm",
            "vent_saq",
            "vent_maxaf",
        }:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if unit:
            self._attr_state_class = SensorStateClass.MEASUREMENT
        if key in {"faults", "warnings", "notifications", "override"} or key.startswith(
            "filter"
        ):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        return self.coordinator.available and channel_present(
            self.coordinator.cache.values, self.topic
        )

    @property
    def native_value(self):
        value = self.coordinator.cache.values.get(self.topic)
        if isinstance(value, dict):
            if self.topic == "vent/caf":
                value = value.get("ps")
            elif self.topic == "mdet/wifi/sta":
                value = value.get("rssi")
            else:
                value = value.get("ot")
        if self.topic in ENUM_TOPICS:
            return enum_state(value, ENUM_TOPICS[self.topic])
        if self.topic == "mdet/warns":
            return warning_state(value)
        for topic in ALARM_TOPICS.values():
            if self.topic == topic:
                decoded = decode_alarm(value)
                if decoded is None:
                    return None
                return "active" if decoded["raw_value"] else "clear"
        if (
            value is None
            or isinstance(value, bool)
            or not isinstance(value, (int, float))
        ):
            return None
        if self.topic.endswith("/dr"):
            return round(value / 3600, 2) if value >= 0 else None
        if self.topic.endswith("/fm") and value < 0:
            return None
        return value

    @property
    def extra_state_attributes(self):
        value = self.coordinator.cache.values.get(self.topic)
        if self.topic.endswith("/dr"):
            return {"raw_seconds": value}
        for topic in ALARM_TOPICS.values():
            if self.topic == topic:
                decoded = decode_alarm(value)
                if decoded is not None and topic == "mdet/warns":
                    decoded["confirmed_codes"] = [
                        name
                        for bit, name in CONFIRMED_WARNING_BITS.items()
                        if bit in decoded["active_bits"]
                    ]
                    decoded["unmapped_bits"] = (int(value) & 0xFFFFFFFF) & ~6144
                return decoded
        if self.topic in ENUM_TOPICS and not isinstance(value, dict):
            return {"raw_value": value}
        if self.topic in {"vent/caf", "vent/cor"} and isinstance(value, dict):
            attributes = dict(value)
            if self.topic == "vent/caf" and value.get("ps") in (1, 2, 3, 4):
                profile = self.coordinator.cache.values.get(
                    f"vent/pf{int(value['ps'])}", {}
                )
                attributes["profile_name"] = profile.get("name")
            return attributes
        return None


class EconiqBoostButton(EconiqEntity, ButtonEntity):
    _attr_icon = "mdi:fan-plus"

    def __init__(self, coordinator, cancel=False):
        super().__init__(coordinator, "cancel_boost" if cancel else "boost_15")
        self.cancel = cancel
        # An inferred command must be explicitly enabled by the user.
        self._attr_entity_registry_enabled_default = not cancel

    async def async_press(self):
        await self.coordinator.async_boost(self.cancel)


class EconiqModeButton(EconiqEntity, ButtonEntity):
    """Explicit timed mode control; non-Boost modes are marked unverified."""

    MODES = ("low", "normal", "purge", "maximum")

    def __init__(self, coordinator, mode: str):
        if mode not in self.MODES:
            raise ValueError("Unsupported Econiq mode button")
        super().__init__(coordinator, f"{mode}_15_unverified")
        self.mode = mode
        self._attr_icon = "mdi:fan"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_entity_registry_enabled_default = False

    async def async_press(self):
        await self.coordinator.async_set_mode(self.mode, duration_minutes=15)
