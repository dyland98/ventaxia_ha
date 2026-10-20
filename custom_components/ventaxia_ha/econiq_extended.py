"""Additional read-only Econiq telemetry, grounded in the supplied APK."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
import math
import re

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from .econiq_entities import EconiqSensor
from .econiq_status import MODE_STATES, enum_state, integer_value

BYPASS_CONFIG_STATES = dict(
    enumerate(("off", "normal", "evening_fresh", "night_fresh"))
)
BYPASS_STATES = dict(
    enumerate(
        (
            "inactive",
            "normal",
            "evening_fresh",
            "night_fresh",
            "frost_protection",
            "manual_open",
        )
    )
)
FROST_STATES = dict(
    enumerate(
        (
            "inactive",
            "airflow_imbalance",
            "bypass",
            "preheater_balanced",
            "preheater_imbalanced",
        )
    )
)


def finite_number(value):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        return None
    return value


def device_date(value):
    """Dates have no timezone; reject timestamps and malformed device values."""
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def due_date(last, interval):
    """The app adds calendar months; zero disables the interval."""
    last = device_date(last)
    months = integer_value(interval)
    if last is None or months is None or not 1 <= months <= 1200:
        return None
    year, month0 = divmod(last.year * 12 + last.month - 1 + months, 12)
    if not 1 <= year <= 9999:
        return None
    month = month0 + 1
    return date(year, month, min(last.day, calendar.monthrange(year, month)[1]))


def requested_seconds(value):
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-2][0-9]:[0-5][0-9]:[0-5][0-9]", value
    ):
        return None
    hours, minutes, seconds = map(int, value.split(":"))
    return hours * 3600 + minutes * 60 + seconds if hours < 24 else None


def override_remaining(override, rtc):
    """Compare two device timestamps; never assume the HA clock/timezone matches."""
    if not isinstance(override, dict):
        return None
    kind = integer_value(override.get("ot"))
    if kind == 0:
        return 0
    if (
        kind != 9
        or not isinstance(rtc, str)
        or not isinstance(override.get("trem"), str)
    ):
        return None
    duration = requested_seconds(override.get("treq"))
    if duration is None:
        return None
    try:
        elapsed = (
            datetime.fromisoformat(rtc) - datetime.fromisoformat(override["trem"])
        ).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return None
    if elapsed < 0:
        return None
    return round(max(0, duration - elapsed) / 60, 2)


@dataclass(frozen=True)
class Reading:
    key: str
    topic: str
    field: str | None = None
    kind: str = "number"
    unit: str | None = None
    device_class: SensorDeviceClass | None = None
    states: dict | None = None


READINGS = [
    Reading(
        "override_requested_duration",
        "vent/cor",
        "treq",
        kind="requested_duration",
        unit="min",
        device_class=SensorDeviceClass.DURATION,
    ),
    Reading(
        "override_remaining",
        "vent/cor",
        kind="remaining",
        unit="min",
        device_class=SensorDeviceClass.DURATION,
    ),
    Reading(
        "runtime_total",
        "mdet/runt",
        kind="hours",
        unit="h",
        device_class=SensorDeviceClass.DURATION,
    ),
    Reading("filter_interval", "vent/filtertmr/int", kind="months"),
    Reading(
        "filter_last_changed",
        "vent/filtertmr/last",
        kind="date",
        device_class=SensorDeviceClass.DATE,
    ),
    Reading(
        "filter_next_due",
        "vent/filtertmr/last",
        kind="due",
        device_class=SensorDeviceClass.DATE,
    ),
    Reading("service_interval", "mdet/svctmr/int", kind="months"),
    Reading(
        "service_last_done",
        "mdet/svctmr/last",
        kind="date",
        device_class=SensorDeviceClass.DATE,
    ),
    Reading(
        "service_next_due",
        "mdet/svctmr/last",
        kind="due",
        device_class=SensorDeviceClass.DATE,
    ),
    *(Reading(f"filter{i}_type", f"vent/filter{i}/typ", kind="text") for i in (1, 2)),
    *(
        Reading(f"profile_{mode}", f"vent/pf{i}", "name", kind="text")
        for i, mode in enumerate(("low", "normal", "boost", "purge"), 1)
    ),
    Reading("bypass_state", "vent/sbs", "am", kind="enum", states=BYPASS_STATES),
    Reading("bypass_open", "vent/sbs", "op", kind="percent", unit="%"),
    Reading("bypass_position", "vent/sbs", "pos", kind="text"),
    Reading(
        "bypass_configured_mode",
        "vent/sbc",
        "mod",
        kind="enum",
        states=BYPASS_CONFIG_STATES,
    ),
    Reading("bypass_fan_mode", "vent/sbc", "gtm", kind="enum", states=MODE_STATES),
    Reading(
        "bypass_outdoor_threshold",
        "vent/sbc",
        "ect",
        unit="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    Reading(
        "bypass_indoor_threshold",
        "vent/sbc",
        "ict",
        unit="°C",
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    Reading("frost_state", "vent/afstat", "sta", kind="enum", states=FROST_STATES),
    Reading("frost_preheater_power", "vent/afstat", "pwr"),
    Reading("frost_preheater_usage", "vent/afstat", "usa"),
    Reading("frost_configuration", "vent/afc"),
]


class EconiqExtendedSensor(EconiqSensor):
    def __init__(self, coordinator, reading):
        super().__init__(
            coordinator, reading.key, reading.topic, reading.unit, reading.device_class
        )
        self.reading = reading
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if reading.states:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = [*reading.states.values(), "unknown_code"]

    @property
    def native_value(self):
        spec = self.reading
        value = self._coordinator_values.get(spec.topic)
        if spec.kind == "remaining":
            return override_remaining(value, self._coordinator_values.get("mdet/rtc"))
        if spec.kind == "due":
            interval_topic = (
                "vent/filtertmr/int"
                if spec.key.startswith("filter")
                else "mdet/svctmr/int"
            )
            return due_date(value, self._coordinator_values.get(interval_topic))
        if spec.field is not None:
            value = value.get(spec.field) if isinstance(value, dict) else None
        if spec.kind == "requested_duration":
            seconds = requested_seconds(value)
            return seconds / 60 if seconds is not None else None
        if spec.kind == "enum":
            return enum_state(value, spec.states)
        if spec.kind == "date":
            return device_date(value)
        if spec.kind == "text":
            return value[:255] if isinstance(value, str) and value else None
        number = finite_number(value)
        if number is None:
            return None
        if spec.kind == "hours":
            return round(number / 3600, 2) if number >= 0 else None
        if spec.kind == "months":
            return integer_value(number) if number >= 0 else None
        if spec.kind == "percent" and not 0 <= number <= 100:
            return None
        return number

    @property
    def _coordinator_values(self):
        return self.coordinator.cache.values

    @property
    def extra_state_attributes(self):
        spec = self.reading
        value = self._coordinator_values.get(spec.topic)
        if spec.topic.startswith("vent/pf") and isinstance(value, dict):
            return {
                "source_topic": spec.topic,
                "supply_target": value.get("sup"),
                "extract_target": value.get("ext"),
                "control_mode": self._coordinator_values.get("vent/cm"),
            }
        if isinstance(value, dict):
            return {"source_topic": spec.topic, **value}
        return {"source_topic": spec.topic, "raw_value": value}
