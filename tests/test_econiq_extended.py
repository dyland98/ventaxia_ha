"""Read-only APK telemetry, channel discovery and exact mode cancellation."""

from datetime import date
import json
from unittest.mock import AsyncMock, patch

from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_component

from custom_components.ventaxia_ha.const import DOMAIN
from custom_components.ventaxia_ha.diagnostics import async_get_config_entry_diagnostics
from custom_components.ventaxia_ha.econiq import EconiqCache, cancel_payload
from custom_components.ventaxia_ha.econiq_controls import EconiqCancelOverrideButton
from custom_components.ventaxia_ha.econiq_coordinator import EconiqCoordinator
from custom_components.ventaxia_ha.econiq_discovery import (
    EconiqChannelSensor,
    register_dynamic_sensors,
)
from custom_components.ventaxia_ha.econiq_extended import (
    READINGS,
    EconiqExtendedSensor,
    due_date,
)
from custom_components.ventaxia_ha.econiq_topics import (
    channel_present,
)


def coordinator(hass, data):
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id="econiq:TEST-UNIT")
    entry.add_to_hass(hass)
    return EconiqCoordinator(hass, entry)


def feed(c, topic, value):
    payload = json.dumps(value) if isinstance(value, dict) else str(value)
    assert c.cache.update("TEST-UNIT/" + topic, payload.encode())


@pytest.mark.parametrize(
    "last,months,expected",
    [
        ("2024-01-31", 1, date(2024, 2, 29)),
        ("2025-01-31", 1, date(2025, 2, 28)),
        ("2025-10-20", 12, date(2026, 10, 20)),
        ("2025-01-01", 0, None),
        ("2025-02-30", 1, None),
        ("2025-01-01", None, None),
        ("2025-01-01", 1.5, None),
        ("2025-01-01", True, None),
        ("9999-12-31", 1, None),
        ("", 1, None),
    ],
)
def test_calendar_month_intervals(last, months, expected):
    assert due_date(last, months) == expected


async def test_extra_sensors_and_partial_updates(hass, econiq_data):
    c = coordinator(hass, econiq_data)
    sensors = {item.key: EconiqExtendedSensor(c, item) for item in READINGS}
    assert all(sensor.native_value is None for sensor in sensors.values())
    feed(c, "mdet/runt", 7200)
    feed(c, "vent/filtertmr/last", "2026-01-31")
    feed(c, "vent/filtertmr/int", 1)
    feed(c, "mdet/svctmr/last", "2026-01-01")
    feed(c, "mdet/svctmr/int", 12)
    feed(c, "vent/filter1/typ", "G4")
    feed(c, "vent/pf1", {"name": "Absence", "sup": 15, "ext": 17})
    feed(c, "vent/sbs", {"am": 2, "op": 75, "pos": "moving"})
    feed(c, "vent/sbc", {"mod": 3, "gtm": 2, "ect": 12, "ict": 23})
    feed(c, "vent/afstat", {"sta": 3, "pwr": 50, "usa": 1})
    assert sensors["runtime_total"].native_value == 2
    assert sensors["filter_next_due"].native_value == date(2026, 2, 28)
    assert sensors["service_next_due"].native_value == date(2027, 1, 1)
    assert sensors["filter1_type"].native_value == "G4"
    assert sensors["profile_low"].native_value == "Absence"
    assert sensors["profile_low"].extra_state_attributes["extract_target"] == 17
    assert sensors["bypass_state"].native_value == "evening_fresh"
    assert sensors["bypass_open"].native_value == 75
    assert sensors["bypass_position"].native_value == "moving"
    assert sensors["bypass_configured_mode"].native_value == "night_fresh"
    assert sensors["bypass_indoor_threshold"].native_value == 23
    assert sensors["bypass_fan_mode"].native_value == "normal"
    assert sensors["frost_state"].native_value == "preheater_balanced"
    assert sensors["frost_preheater_power"].native_value == 50
    feed(c, "vent/sbs", {"am": 99, "op": 101})
    assert sensors["bypass_state"].native_value == "unknown_code"
    assert sensors["bypass_open"].native_value is None
    assert sensors["bypass_position"].native_value is None
    assert sensors["runtime_total"].native_value == 2
    feed(c, "vent/filtertmr/int", 0)
    assert sensors["filter_next_due"].native_value is None
    assert sensors["filter_last_changed"].native_value == date(2026, 1, 31)
    feed(c, "mdet/runt", "nan")
    assert sensors["runtime_total"].native_value is None


@pytest.mark.parametrize(
    "mode,expected",
    [("low", 1), ("normal", 2), ("boost", 3), ("purge", 4), ("maximum", 5)],
)
async def test_cancel_only_selected_mode(hass, econiq_data, mode, expected):
    c = coordinator(hass, econiq_data)
    c.available = True
    c._client = AsyncMock()
    c.select_override(mode=mode)
    feed(c, "vent/caf", {"ps": 2, "prop": 100})  # Maximum may keep the previous ps.
    await EconiqCancelOverrideButton(c).async_press()
    c._client.publish.assert_awaited_once_with(
        "TEST-UNIT/vent/uo",
        json.dumps({"gtm": expected, "treq": "00:00:00"}, separators=(",", ":")),
        qos=0,
        retain=False,
    )
    assert c.cache.values["vent/caf"]["ps"] == 2
    with pytest.raises(ValueError):
        cancel_payload("off")


@pytest.mark.parametrize(
    "topic",
    [
        "sn/0/t",
        "sn/32/t",
        "zone/16/t",
        "zone/0/t",
        "zone/1/bat",
        "sn/1/remove",
        "sn/1/conf/wr",
        "zone/2/restdef",
        "vent/sbc/wr",
        "vent/filtertmr/reset",
        "mdet/svctmr/reset",
    ],
)
def test_unsupported_topics_never_enter_cache(topic):
    cache = EconiqCache("TEST-UNIT")
    assert not cache.update("TEST-UNIT/" + topic, b"1")
    assert not cache.values


async def test_dynamic_discovery_and_active_masks(hass, econiq_data):
    c = coordinator(hass, econiq_data)
    c.available = True
    entities = []
    register_dynamic_sensors(c, lambda values: entities.extend(values))
    feed(c, "zone/3/t", 20.5)
    feed(c, "zone/3/conf", {"name": "Salon"})
    feed(c, "sn/5/rh", 53)
    feed(c, "sn/5/info", {"dt": 1, "fwv": 1001001, "ht": 2})
    feed(c, "sn/5/conf", {"name": "Sonde salon", "zone": 3})
    feed(c, "sn/5/sw", "true")
    feed(c, "zone/2/t", 12)  # Existing entity keeps its original identity.
    feed(c, "sn/1/rh", 40)
    c._notify_update()
    assert len(entities) == 3
    assert all(isinstance(entity, EconiqChannelSensor) for entity in entities)
    zone = next(entity for entity in entities if entity.topic == "zone/3/t")
    remote = next(entity for entity in entities if entity.topic == "sn/5/rh")
    switch = next(entity for entity in entities if entity.topic == "sn/5/sw")
    assert (
        zone.native_value == 20.5
        and zone.extra_state_attributes["configured_name"] == "Salon"
    )
    assert remote.native_value == 53 and remote.extra_state_attributes["zone"] == 3
    assert switch.native_value == "on"
    c._notify_update()
    assert len(entities) == 3
    feed(c, "zone/active", 8)  # Zone bit uses the ID itself.
    feed(c, "sn/active", 16)  # Remote bit uses ID - 1.
    assert zone.available and remote.available
    feed(c, "zone/active", 0)
    feed(c, "sn/active", 0)
    assert not zone.available and not remote.available
    feed(c, "sn/active", "nan")
    assert not channel_present(c.cache.values, "sn/5/rh")
    feed(c, "zone/4/t", 22)
    c._notify_update()
    assert len(entities) == 3
    feed(c, "zone/active", 16)
    c._notify_update()
    assert len(entities) == 4
    feed(c, "sn/5/rh", "-inf")
    assert remote.native_value is None


async def test_actual_ha_discovery_restart_and_unload(hass, econiq_data, fake_client):
    mock_component(hass, "frontend")
    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    entry.add_to_hass(hass)
    fake_client.feed("mdet/runt", b"7200")
    with patch(
        "custom_components.ventaxia_ha.econiq_coordinator.create_client",
        return_value=fake_client,
    ), patch("custom_components.ventaxia_ha.async_setup", return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        total = registry.async_get_entity_id(
            "sensor", DOMAIN, "econiq:TEST-UNIT_runtime_total"
        )
        assert hass.states.get(total).state == "2.0"
        fake_client.feed("zone/3/t", b"21.5")
        await hass.async_block_till_done()
        dynamic = registry.async_get_entity_id(
            "sensor", DOMAIN, "econiq:TEST-UNIT_zone_3_t"
        )
        assert dynamic and hass.states.get(dynamic).state == "21.5"
        fake_client.feed("zone/active", b"0")
        await hass.async_block_till_done()
        assert hass.states.get(dynamic).state == "unavailable"
        c = hass.data[DOMAIN][entry.entry_id]
        fake_client.publish.assert_not_awaited()
        # Explicit startup subscriptions remain read-only, including reconnects.
        subscribed = [
            topic for topic, qos in fake_client.subscribe.await_args_list[1].args[0]
        ]
        assert "TEST-UNIT/vent/sbs" in subscribed
        assert all(
            not topic.endswith(("/wr", "/reset", "/restdef", "/remove"))
            for topic in subscribed
        )
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert not c._callbacks
        fake_client.feed("zone/3/t", b"22.5")
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert (
            registry.async_get_entity_id("sensor", DOMAIN, "econiq:TEST-UNIT_zone_3_t")
            == dynamic
        )
        assert hass.states.get(dynamic).state == "22.5"
        fake_client.publish.assert_not_awaited()
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_diagnostics_include_measurements_but_no_remote_names(hass, econiq_data):
    c = coordinator(hass, econiq_data)
    hass.data[DOMAIN] = {c.entry.entry_id: c}
    feed(c, "mdet/runt", 3600)
    feed(c, "sn/5/rh", 50)
    feed(c, "sn/5/conf", {"name": "Private bedroom", "zone": 1})
    exported = await async_get_config_entry_diagnostics(hass, c.entry)
    assert exported["telemetry"]["mdet/runt"] == 3600
    assert exported["telemetry"]["sn/5/rh"] == 50
    assert "sn/5/conf" not in exported["telemetry"]
    assert econiq_data["psk_key"] not in json.dumps(exported)


@pytest.mark.parametrize(
    "override,clock,expected",
    [
        (
            {"ot": 9, "trem": "2026-10-20T10:00:00", "treq": "00:15:00"},
            "2026-10-20T10:05:00",
            10,
        ),
        (
            {"ot": 9, "trem": "2026-10-20T10:00:00", "treq": "00:15:00"},
            "2026-10-20T10:30:00",
            0,
        ),
        (
            {"ot": 9, "trem": "2026-10-20T10:00:00", "treq": "00:15:00"},
            "2026-10-20T09:59:00",
            None,
        ),
        ({"ot": 9, "trem": "invalid", "treq": "00:15:00"}, "2026-10-20T10:00:00", None),
        ({"ot": 9, "trem": "2026-10-20T10:00:00", "treq": "00:15:00"}, None, None),
        (
            {"ot": 9, "trem": "2026-10-20T10:00:00", "treq": "00:99:00"},
            "2026-10-20T10:00:00",
            None,
        ),
        (
            {"ot": 9, "trem": "2026-10-20T10:00:00", "treq": "00:15:00"},
            "2026-10-20T10:05:00+02:00",
            None,
        ),
        ({"ot": 0}, None, 0),
        ({"ot": 11}, None, None),
        ({}, None, None),
        (None, None, None),
    ],
)
def test_remaining_uses_only_the_device_clock(override, clock, expected):
    from custom_components.ventaxia_ha.econiq_extended import override_remaining

    assert override_remaining(override, clock) == expected


async def test_duration_sensors_update_from_device_messages(hass, econiq_data):
    c = coordinator(hass, econiq_data)
    sensors = {item.key: EconiqExtendedSensor(c, item) for item in READINGS}
    feed(c, "vent/cor", {"ot": 9, "trem": "2026-10-20T10:00:00", "treq": "02:00:00"})
    assert sensors["override_requested_duration"].native_value == 120
    assert sensors["override_remaining"].native_value is None
    feed(c, "mdet/rtc", "2026-10-20T10:30:00")
    assert sensors["override_remaining"].native_value == 90


async def test_optional_subscribe_failure_keeps_base_connection(
    hass, econiq_data, fake_client
):
    import aiomqtt

    c = coordinator(hass, econiq_data)
    fake_client.subscribe.side_effect = [
        None,
        aiomqtt.MqttError("optional read rejected"),
    ]
    fake_client.feed("io/t1", b"10.0")
    with patch(
        "custom_components.ventaxia_ha.econiq_coordinator.create_client",
        return_value=fake_client,
    ):
        await c.async_start()
        assert c.available and c.cache.values["io/t1"] == 10
        fake_client.publish.assert_not_awaited()
        await c.async_stop()
        assert fake_client.closed
