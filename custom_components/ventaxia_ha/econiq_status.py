"""Read-only decoding from the supplied Android APK; see doc/ECONIQ_APK.md."""

from __future__ import annotations

import math

MODE_STATES = {0: "off", 1: "low", 2: "normal", 3: "boost", 4: "purge", 5: "maximum"}
OVERRIDE_STATES = dict(
    enumerate(
        (
            "none",
            "zonal_schedule",
            "external_co2",
            "external_humidity",
            "zonal_co2",
            "zonal_voc",
            "zonal_humidity",
            "summer_bypass",
            "zonal_switch",
            "user_override",
            "silent_hours",
            "frost_protection",
            "damper",
            "filter_calibration",
            "shutdown",
            "commissioning",
            "standby",
            "diagnostic",
        )
    )
)
CONTROL_MODE_STATES = {
    0: "fixed_percentage",
    1: "constant_volume",
    2: "constant_pressure",
}
AIR_QUALITY_STATES = {1: "good", 2: "average", 3: "poor"}
ENUM_TOPICS = {
    "vent/caf": MODE_STATES,
    "vent/cor": OVERRIDE_STATES,
    "vent/cm": CONTROL_MODE_STATES,
    "vent/saq": AIR_QUALITY_STATES,
}
# Correlated with the user's live 6144 value and app messages W-12 / W-13.
CONFIRMED_WARNING_BITS = {11: "filter_clean_overdue", 12: "service_overdue"}
WARNING_STATES = [
    "clear",
    "filter_clean_overdue",
    "service_overdue",
    "filter_and_service_overdue",
    "other",
]


def warning_state(value):
    mask = alarm_mask(value)
    if mask is None:
        return None
    if mask & ~6144:
        return "other"
    return {
        0: "clear",
        2048: "filter_clean_overdue",
        4096: "service_overdue",
        6144: "filter_and_service_overdue",
    }[mask]


ALARM_TOPICS = {
    "faults": "mdet/faults",
    "warnings": "mdet/warns",
    "notifications": "mdet/noti",
}


def integer_value(value):
    """Missing, boolean, nonfinite or fractional codes are never guessed."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or int(value) != value:
        return None
    return int(value)


def enum_state(value, states):
    code = integer_value(value)
    return None if code is None else states.get(code, "unknown_code")


def alarm_mask(value):
    """Preserve bit 31 whether the firmware serializes signed or unsigned int32."""
    code = integer_value(value)
    if code is None or not -(2**31) <= code < 2**32:
        return None
    return code & 0xFFFFFFFF


def decode_alarm(value):
    """Report active bit positions, without guessing the diagnostic meanings."""
    mask = alarm_mask(value)
    if mask is None:
        return None
    return {
        "raw_value": integer_value(value),
        "active_bits": [bit for bit in range(32) if mask & (1 << bit)],
    }
