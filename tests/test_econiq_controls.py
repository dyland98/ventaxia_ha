"""Mode/duration selection must never publish before explicit application."""

import json
from unittest.mock import AsyncMock, patch

from homeassistant.core import State
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_component,
    mock_restore_cache,
)

from custom_components.ventaxia_ha.const import DOMAIN
from custom_components.ventaxia_ha.econiq import ECONIQ_DURATIONS, mode_payload
from custom_components.ventaxia_ha.econiq_controls import (
    EconiqApplyOverrideButton,
    EconiqOverrideSelect,
)
from custom_components.ventaxia_ha.econiq_coordinator import EconiqCoordinator
from custom_components.ventaxia_ha.econiq_entities import EconiqSensor
from custom_components.ventaxia_ha.econiq_status import (
    MODE_STATES,
    OVERRIDE_STATES,
    decode_alarm,
    enum_state,
)


@pytest.mark.parametrize(
    "duration,expected",
    [
        (15, "00:15:00"),
        (30, "00:30:00"),
        (60, "01:00:00"),
        (120, "02:00:00"),
        (240, "04:00:00"),
        (480, "08:00:00"),
    ],
)
def test_apk_durations(duration, expected):
    assert json.loads(mode_payload("boost", duration)) == {"gtm": 3, "treq": expected}


@pytest.mark.parametrize(
    "code,expected",
    [
        (0, "off"),
        (1, "low"),
        (2, "normal"),
        (3, "boost"),
        (4, "purge"),
        (5, "maximum"),
        (999, "unknown_code"),
        (2.5, None),
        (True, None),
        (None, None),
    ],
)
def test_readable_modes(code, expected):
    assert enum_state(code, MODE_STATES) == expected


def test_override_and_invalid_alarm_values():
    assert enum_state(9, OVERRIDE_STATES) == "user_override"
    assert enum_state(0, OVERRIDE_STATES) == "none"
    assert enum_state(19, OVERRIDE_STATES) == "unknown_code"
    assert decode_alarm(6144) == {
        "raw_value": 6144,
        "active_bits": [11, 12],
    }
    assert decode_alarm(-2147483648)["active_bits"] == [31]
    for value in (None, True, -(2**31) - 1, 2**32, float("nan"), float("inf"), 0.5):
        assert decode_alarm(value) is None


async def test_preparation_and_apply(hass, econiq_data):
    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    entry.add_to_hass(hass)
    coordinator = EconiqCoordinator(hass, entry)
    coordinator.available = True
    coordinator._client = AsyncMock()
    mode = EconiqOverrideSelect(coordinator, "override_mode")
    duration = EconiqOverrideSelect(coordinator, "override_duration")
    apply = EconiqApplyOverrideButton(coordinator)
    assert mode.current_option == "boost"
    assert set(mode.options) == {"low", "normal", "boost", "purge", "maximum"}
    assert duration.options == [str(value) for value in ECONIQ_DURATIONS]
    await duration.async_select_option("120")
    await mode.async_select_option("normal")
    coordinator._client.publish.assert_not_awaited()
    assert not coordinator.cache.values
    await apply.async_press()
    coordinator._client.publish.assert_awaited_once_with(
        "TEST-UNIT/vent/uo", '{"gtm":2,"treq":"02:00:00"}', qos=0, retain=False
    )
    assert not coordinator.cache.values
    for invalid in ("off", "unknown"):
        with pytest.raises(ValueError):
            await mode.async_select_option(invalid)
    with pytest.raises(ValueError):
        await duration.async_select_option("0")
    # Boost also supports the selected duration.
    await mode.async_select_option("boost")
    await apply.async_press()
    coordinator._client.publish.assert_awaited_with(
        "TEST-UNIT/vent/uo", '{"gtm":3,"treq":"02:00:00"}', qos=0, retain=False
    )


async def test_readable_status_keeps_diagnostics(hass, econiq_data):
    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    coordinator = EconiqCoordinator(hass, entry)
    mode = EconiqSensor(coordinator, "mode", "vent/caf", None, None)
    override = EconiqSensor(coordinator, "override", "vent/cor", None, None)
    faults = EconiqSensor(coordinator, "faults", "mdet/faults", None, None)
    assert faults.native_value is None
    coordinator.cache.update("TEST-UNIT/vent/caf", b'{"ps":3,"prop":100}')
    coordinator.cache.update(
        "TEST-UNIT/vent/cor",
        b'{"ot":9,"os":129,"trem":"2026-10-20T10:06:26","treq":"00:15:00"}',
    )
    coordinator.cache.update("TEST-UNIT/mdet/faults", b"0")
    assert mode.native_value == "boost" and mode.extra_state_attributes["ps"] == 3
    assert override.native_value == "user_override"
    assert override.extra_state_attributes["trem"] == "2026-10-20T10:06:26"
    assert (
        faults.native_value == "clear"
        and faults.extra_state_attributes["raw_value"] == 0
    )


async def test_selects_in_ha_restore_without_command(hass, econiq_data, fake_client):
    from homeassistant.helpers import entity_registry as er

    mock_component(hass, "frontend")
    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    entry.add_to_hass(hass)
    # Restore state by the stable registered entity IDs created for this device.
    registry = er.async_get(hass)
    mode_entry = registry.async_get_or_create(
        "select",
        DOMAIN,
        "econiq:TEST-UNIT_override_mode",
        suggested_object_id="test_override_mode",
        config_entry=entry,
    )
    duration_entry = registry.async_get_or_create(
        "select",
        DOMAIN,
        "econiq:TEST-UNIT_override_duration",
        suggested_object_id="test_override_duration",
        config_entry=entry,
    )
    mock_restore_cache(
        hass,
        [State(mode_entry.entity_id, "purge"), State(duration_entry.entity_id, "240")],
    )
    fake_client.feed("vent/caf", b'{"ps":2,"prop":100}')
    with patch(
        "custom_components.ventaxia_ha.econiq_coordinator.create_client",
        return_value=fake_client,
    ), patch("custom_components.ventaxia_ha.async_setup", return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get(mode_entry.entity_id).state == "purge"
        assert hass.states.get(duration_entry.entity_id).state == "240"
        fake_client.publish.assert_not_awaited()
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": duration_entry.entity_id, "option": "30"},
            blocking=True,
        )
        fake_client.publish.assert_not_awaited()
        apply_id = registry.async_get_entity_id(
            "button", DOMAIN, "econiq:TEST-UNIT_apply_override"
        )
        await hass.services.async_call(
            "button", "press", {"entity_id": apply_id}, blocking=True
        )
        fake_client.publish.assert_awaited_once_with(
            "TEST-UNIT/vent/uo", '{"gtm":4,"treq":"00:30:00"}', qos=0, retain=False
        )
        confirmed = registry.async_get_entity_id(
            "sensor", DOMAIN, "econiq:TEST-UNIT_mode"
        )
        assert hass.states.get(confirmed).state == "normal"
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_apk_confirmed_units(hass, econiq_data):
    from custom_components.ventaxia_ha.econiq_entities import SENSORS

    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    coordinator = EconiqCoordinator(hass, entry)
    descriptions = {description[0]: description for description in SENSORS}
    runtime = EconiqSensor(coordinator, *descriptions["afs_dr"])
    measured_flow = EconiqSensor(coordinator, *descriptions["afs_fm"])
    target = EconiqSensor(coordinator, *descriptions["afs_fd"])
    coordinator.cache.update("TEST-UNIT/vent/afs/dr", b"20548782")
    coordinator.cache.update("TEST-UNIT/vent/afs/fm", b"33.5")
    assert runtime.native_value == 5707.99
    assert runtime.native_unit_of_measurement == "h"
    assert runtime.extra_state_attributes["raw_seconds"] == 20548782
    assert measured_flow.native_value == 33.5
    assert measured_flow.native_unit_of_measurement == "L/s"
    assert target.native_unit_of_measurement is None
    coordinator.cache.update("TEST-UNIT/vent/afs/fm", b"-1")
    assert measured_flow.native_value is None


@pytest.mark.parametrize(
    "mask,expected",
    [
        (0, "clear"),
        (2048, "filter_clean_overdue"),
        (4096, "service_overdue"),
        (6144, "filter_and_service_overdue"),
        (6145, "other"),
        (1, "other"),
        (None, None),
    ],
)
def test_confirmed_warnings(mask, expected):
    from custom_components.ventaxia_ha.econiq_status import warning_state

    assert warning_state(mask) == expected


async def test_individual_maintenance_alerts(hass, econiq_data):
    from custom_components.ventaxia_ha.binary_sensor import EconiqMaintenanceAlert

    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    coordinator = EconiqCoordinator(hass, entry)
    filter_alert = EconiqMaintenanceAlert(coordinator, 11, "filter_clean_overdue")
    service_alert = EconiqMaintenanceAlert(coordinator, 12, "service_overdue")
    assert filter_alert.is_on is None and service_alert.is_on is None
    coordinator.cache.update("TEST-UNIT/mdet/warns", b"6144")
    assert filter_alert.is_on and service_alert.is_on
    assert filter_alert.extra_state_attributes["warning_code"] == "W-12"
    assert service_alert.extra_state_attributes["warning_code"] == "W-13"
    coordinator.cache.update("TEST-UNIT/mdet/warns", b"2048")
    assert filter_alert.is_on and not service_alert.is_on
    coordinator.cache.update("TEST-UNIT/mdet/warns", b"nan")
    assert filter_alert.is_on is None and service_alert.is_on is None


async def test_readable_control_and_air_quality(hass, econiq_data):
    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    coordinator = EconiqCoordinator(hass, entry)
    control = EconiqSensor(coordinator, "vent_cm", "vent/cm", None, None)
    quality = EconiqSensor(coordinator, "vent_saq", "vent/saq", None, None)
    coordinator.cache.update("TEST-UNIT/vent/cm", b"0")
    coordinator.cache.update("TEST-UNIT/vent/saq", b"1")
    assert control.native_value == "fixed_percentage"
    assert quality.native_value == "good"
    assert control.extra_state_attributes == {"raw_value": 0}
    coordinator.cache.update("TEST-UNIT/vent/saq", b"9")
    assert quality.native_value == "unknown_code"
