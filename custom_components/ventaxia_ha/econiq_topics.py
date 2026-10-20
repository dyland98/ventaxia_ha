"""Bounded allowlist for extended read-only topics from the Android app."""

import re

EXTRA_NUMERIC_TOPICS = {
    "mdet/runt",
    "vent/filtertmr/int",
    "mdet/svctmr/int",
    "vent/afc",
    "zone/active",
    "sn/active",
}
EXTRA_JSON_TOPICS = {
    "vent/pf1",
    "vent/pf2",
    "vent/pf3",
    "vent/pf4",
    "vent/sbc",
    "vent/sbs",
    "vent/afstat",
}
EXTRA_TEXT_TOPICS = {
    "vent/filter1/typ",
    "vent/filter2/typ",
    "vent/filtertmr/last",
    "mdet/svctmr/last",
    "mdet/rtc",
}
CHANNEL_RE = re.compile(
    r"(zone|sn)/([1-9][0-9]?)/(t|rh|co2|voc|bat|ss|sta|dp|sw|conf|info)\Z"
)


def channel_kind(topic):
    match = CHANNEL_RE.fullmatch(topic)
    if not match:
        return None
    group, index, field = match.groups()
    if int(index) > (15 if group == "zone" else 31):
        return None
    if group == "zone" and field not in {"t", "rh", "co2", "voc", "conf"}:
        return None
    if field in {"conf", "info"}:
        return "json"
    if field == "sw":
        return "boolean"
    return "number"


def channel_present(values, topic):
    """App bit layouts differ: zone index, sensor index minus one."""
    from .econiq_status import alarm_mask

    match = CHANNEL_RE.fullmatch(topic)
    if match is None:
        return True
    group, index, _ = match.groups()
    active_topic = f"{group}/active"
    if active_topic not in values:
        return True  # Firmware may omit the list; a received channel is enough.
    mask = alarm_mask(values[active_topic])
    bit = int(index) if group == "zone" else int(index) - 1
    return mask is not None and bool(mask & (1 << bit))
