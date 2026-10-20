"""Discover only allowlisted, bounded zones and sensors actually publishing data."""

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory

from .econiq_entities import EconiqSensor
from .econiq_extended import finite_number
from .econiq_topics import CHANNEL_RE, channel_kind, channel_present

# Preserve the previously exposed entities rather than registering duplicates.
LEGACY_TOPICS = {"zone/2/co2", "zone/2/t", "sn/1/rh"}
FIELDS = {
    "t": ("temperature", "°C", SensorDeviceClass.TEMPERATURE),
    "rh": ("humidity", "%", SensorDeviceClass.HUMIDITY),
    "co2": ("co2", None, None),
    "voc": ("voc", None, None),
    "bat": ("battery", None, None),
    "ss": ("signal", None, None),
    "sta": ("status", None, None),
    "dp": ("damper", None, None),
    "sw": ("switch", None, SensorDeviceClass.ENUM),
}


def register_dynamic_sensors(coordinator, async_add_entities):
    seen = set(LEGACY_TOPICS)

    @callback
    def discover():
        entities = []
        for topic in coordinator.cache.values:
            if topic in seen or channel_kind(topic) not in {"number", "boolean"}:
                continue
            if not channel_present(coordinator.cache.values, topic):
                continue
            seen.add(topic)
            entities.append(EconiqChannelSensor(coordinator, topic))
        if entities:
            async_add_entities(entities)

    coordinator.add_update_callback(discover)
    coordinator.entry.async_on_unload(
        lambda: coordinator.remove_update_callback(discover)
    )
    discover()


class EconiqChannelSensor(EconiqSensor):
    def __init__(self, coordinator, topic):
        group, index, field = CHANNEL_RE.fullmatch(topic).groups()
        name, unit, device_class = FIELDS[field]
        super().__init__(
            coordinator, f"{group}_{index}_{field}", topic, unit, device_class
        )
        self.group = group
        self.index = index
        self.field = field
        self._attr_translation_key = f"{group}_{name}"
        self._attr_translation_placeholders = {"index": index}
        if field in {"bat", "ss", "sta", "dp", "sw"}:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if field == "sw":
            self._attr_options = ["on", "off"]

    @property
    def native_value(self):
        value = self.coordinator.cache.values.get(self.topic)
        if self.field == "sw":
            return ("on" if value else "off") if isinstance(value, bool) else None
        return finite_number(value)

    @property
    def extra_state_attributes(self):
        root = f"{self.group}/{self.index}"
        config = self.coordinator.cache.values.get(root + "/conf", {})
        info = self.coordinator.cache.values.get(root + "/info", {})
        return {
            "source_topic": self.topic,
            "configured_name": config.get("name"),
            "zone": config.get("zone"),
            "device_type": info.get("dt"),
            "hardware_type": info.get("ht"),
            "firmware": info.get("fwv"),
        }
