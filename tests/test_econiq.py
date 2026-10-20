"""Protocol, cache, lifecycle, controls and diagnostics tests."""

import asyncio
import json
import ssl
from unittest.mock import patch

import aiomqtt
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ventaxia_ha.const import DOMAIN
from custom_components.ventaxia_ha.diagnostics import async_get_config_entry_diagnostics
from custom_components.ventaxia_ha.econiq import (
    EconiqCache,
    PskUnavailableError,
    boost_payload,
    create_client,
    create_tls_context,
    normalize_prefix,
    parse_psk,
)
from custom_components.ventaxia_ha.econiq_coordinator import EconiqCoordinator
from custom_components.ventaxia_ha.econiq_entities import (
    EconiqBoostButton,
    EconiqSensor,
)


@pytest.mark.parametrize("value", ["", "0", "xyz", "00", "0000", "ab cd", "testPsk"])
def test_invalid_psk(value):
    with pytest.raises(ValueError):
        parse_psk(value)


def test_psk_decodes_bytes_and_tls_settings():
    assert parse_psk("A1b2") == b"\xa1\xb2"
    context = create_tls_context("a1b2", "zirconia")
    assert context.minimum_version == context.maximum_version == ssl.TLSVersion.TLSv1_2
    assert not context.check_hostname
    assert context.verify_mode == ssl.CERT_NONE
    assert "PSK-AES128-CBC-SHA" in {c["name"] for c in context.get_ciphers()}
    with patch("ssl.HAS_PSK", False), pytest.raises(PskUnavailableError):
        create_tls_context("a1b2", "zirconia")


@pytest.mark.parametrize("prefix", ["", "/", "#", "a/+", "abc\x00"])
def test_invalid_prefix(prefix):
    with pytest.raises(ValueError):
        normalize_prefix(prefix)


def test_cache_partial_messages_and_malformed_payloads():
    cache = EconiqCache("TEST-UNIT/")
    assert cache.update("TEST-UNIT/io/t1", b"9.8")
    assert cache.update("TEST-UNIT/mdet/warns", b"6144")
    assert cache.values["io/t1"] == 9.8
    assert cache.values["mdet/warns"] == 6144
    assert not cache.update("OTHER/io/t1", b"2")
    assert not cache.update("TEST-UNIT/io/t1", b"broken")
    assert not cache.update("TEST-UNIT/io/t1", b"\xff")
    assert not cache.update("TEST-UNIT/vent/caf", b"[]")
    assert not cache.update("TEST-UNIT/vent/caf", b"{")
    assert not cache.update("TEST-UNIT/secret", b"42")
    assert cache.values["io/t1"] == 9.8
    assert "io/t2" not in cache.values
    assert cache.update("TEST-UNIT/vent/caf", b'{"ps":3,"prop":100}')
    assert cache.values["vent/caf"] == {"ps": 3, "prop": 100}
    for payload in (b"nan", b"inf", b"-inf"):
        cache.update("TEST-UNIT/io/t1", payload)
        assert cache.values["io/t1"] is None
    cache.update("TEST-UNIT/vent/cor", b'{"ot":9,"trem":"uninterpreted","bad":NaN}')
    assert cache.values["vent/cor"]["bad"] is None


def test_mqtt_client_parameters(econiq_data):
    context = create_tls_context("a1b2", "zirconia")
    with patch("custom_components.ventaxia_ha.econiq.aiomqtt.Client") as factory:
        create_client(econiq_data, "stable-id", context)
    kwargs = factory.call_args.kwargs
    assert kwargs["identifier"] == "stable-id"
    assert kwargs["protocol"] == aiomqtt.ProtocolVersion.V311
    assert kwargs["clean_session"] is True
    assert kwargs["tls_context"] is context
    assert kwargs["keepalive"] == 60
    assert "username" not in kwargs and "password" not in kwargs


async def make_coordinator(hass, data):
    entry = MockConfigEntry(domain=DOMAIN, data=data, unique_id="econiq:TEST-UNIT")
    entry.add_to_hass(hass)
    return EconiqCoordinator(hass, entry)


async def test_reconnect_clean_shutdown_and_commands(hass, econiq_data, fake_client):
    coordinator = await make_coordinator(hass, econiq_data)
    fake_client.metadata()
    with patch(
        "custom_components.ventaxia_ha.econiq_coordinator.create_client",
        return_value=fake_client,
    ) as factory:
        await coordinator.async_start()
        assert coordinator.available
        fake_client.subscribe.assert_awaited_once_with("TEST-UNIT/#", qos=0)
        fake_client.publish.assert_not_awaited()
        await coordinator.async_boost()
        fake_client.publish.assert_awaited_with(
            "TEST-UNIT/vent/uo", '{"gtm":3,"treq":"00:15:00"}', qos=0, retain=False
        )
        await coordinator.async_boost(cancel=True)
        fake_client.publish.assert_awaited_with(
            "TEST-UNIT/vent/uo", '{"gtm":3,"treq":"00:00:00"}', qos=0, retain=False
        )
        assert "vent/caf" not in coordinator.cache.values  # No optimistic confirmation.
        fake_client.queue.put_nowait(aiomqtt.MqttError("simulated disconnect"))
        await asyncio.sleep(0)
        assert not coordinator.available
        with pytest.raises(HomeAssistantError):
            await coordinator.async_boost()
        # Wait through the first real backoff to verify a new session and fresh metadata.
        fake_client.metadata()
        async with asyncio.timeout(4):
            while factory.call_count < 2 or not coordinator.available:
                await asyncio.sleep(0.01)
        assert factory.call_args_list[0].args[1] == factory.call_args_list[1].args[1]
        assert fake_client.publish.await_count == 2  # No writes on reconnect.
        await coordinator.async_stop()
        assert (
            fake_client.closed
            and not coordinator.available
            and coordinator._task is None
        )


async def test_stop_during_failed_connection(hass, econiq_data, fake_client):
    coordinator = await make_coordinator(hass, econiq_data)
    fake_client.connect_error = aiomqtt.MqttError("simulated failure")
    with patch(
        "custom_components.ventaxia_ha.econiq_coordinator.create_client",
        return_value=fake_client,
    ):
        starting = asyncio.create_task(coordinator.async_start())
        await asyncio.sleep(0.05)
        starting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await starting
    assert coordinator._task is None
    assert not coordinator.available


async def test_entity_unknown_and_raw_values(hass, econiq_data):
    coordinator = await make_coordinator(hass, econiq_data)
    sensor = EconiqSensor(coordinator, "t1", "io/t1", "°C", None)
    assert sensor.native_value is None
    coordinator.cache.update("TEST-UNIT/io/t1", b"12.3")
    assert sensor.native_value == 12.3
    warnings = EconiqSensor(coordinator, "warnings", "mdet/warns", None, None)
    coordinator.cache.update("TEST-UNIT/mdet/warns", b"6144")
    assert warnings.native_value == 6144
    assert warnings.native_unit_of_measurement is None
    assert (
        EconiqBoostButton(coordinator, cancel=True).entity_registry_enabled_default
        is False
    )
    assert json.loads(boost_payload()) == {"gtm": 3, "treq": "00:15:00"}
    coordinator.cache.update(
        "TEST-UNIT/mdet/wifi/sta", b'{"rssi":-72,"ssid":"private"}'
    )
    hass.data[DOMAIN] = {coordinator.entry.entry_id: coordinator}
    exported = json.dumps(
        await async_get_config_entry_diagnostics(hass, coordinator.entry)
    )
    assert econiq_data["psk_key"] not in exported
    assert "ssid" not in exported and "psk" not in exported
