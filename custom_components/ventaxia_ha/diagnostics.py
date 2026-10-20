"""Export only explicitly safe Econiq diagnostic fields; never entry data."""

from .const import DOMAIN
from .econiq import CONF_DEVICE_TYPE, ECONIQ
from .econiq_topics import EXTRA_NUMERIC_TOPICS, EXTRA_TEXT_TOPICS, channel_kind


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if entry.data.get(CONF_DEVICE_TYPE) != ECONIQ:
        return {"backend": "kinetic", "connected": coordinator.available}
    # No entry serialization, network identifiers, serial, Wi-Fi SSID or PSK.
    return {
        "backend": ECONIQ,
        "connected": coordinator.available,
        "telemetry": {
            topic: value
            for topic, value in coordinator.cache.values.items()
            if topic.startswith(("vent/", "io/"))
            or topic in {"mdet/pwr", "mdet/faults", "mdet/warns", "mdet/noti"}
            or topic in EXTRA_NUMERIC_TOPICS | EXTRA_TEXT_TOPICS
            or channel_kind(topic) in {"number", "boolean"}
        },
    }
