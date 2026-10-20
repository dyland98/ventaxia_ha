"""Config flow routes models separately and preserves Kinetic identifiers."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiomqtt
from homeassistant import config_entries
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, mock_component

from custom_components.ventaxia_ha.config_flow import (
    CannotConnect,
    validate_econiq,
    validate_input,
)
from custom_components.ventaxia_ha.const import DOMAIN
from custom_components.ventaxia_ha.econiq import PskUnavailableError

KINETIC_DATA = {
    "host": "kinetic.example",
    "port": 47811,
    "identity": "test",
    "psk_key": "synthetic-wifi-key",
    "wifi_device_id": "KINETIC-TEST",
}


def test_device_selector_field_is_translated_in_all_catalogs():
    translation_dir = (
        Path(__file__).parents[1] / "custom_components" / "ventaxia_ha" / "translations"
    )
    for path in translation_dir.glob("*.json"):
        translations = json.loads(path.read_text(encoding="utf-8"))
        steps = translations["config"]["step"]
        assert steps["user"]["data"]["device_type"], path.name
        assert set(steps["kinetic"]["menu_options"]) == {"kinetic", "econiq"}


async def start_flow(hass, step):
    if "frontend" not in hass.config.components:
        mock_component(hass, "frontend")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device_type": step}
    )


async def test_device_selector_has_explicit_labels(hass):
    if "frontend" not in hass.config.components:
        mock_component(hass, "frontend")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    options = result["data_schema"].schema["device_type"].config["options"]
    assert options == [
        {"label": "Sentinel Kinetic Advance S", "value": "kinetic"},
        {"label": "Sentinel Econiq (MQTT TLS-PSK)", "value": "econiq"},
    ]


async def test_econiq_success_and_duplicate(hass, econiq_data):
    with patch(
        "custom_components.ventaxia_ha.config_flow.validate_econiq",
        return_value={"title": "Econiq 300"},
    ), patch("custom_components.ventaxia_ha.async_setup_entry", return_value=True):
        result = await start_flow(hass, "econiq")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {k: v for k, v in econiq_data.items() if k != "device_type"},
        )
        assert result["type"] == "create_entry"
        assert result["result"].unique_id == "econiq:TEST-UNIT"
        assert result["data"]["device_type"] == "econiq"
        second = await start_flow(hass, "econiq")
        second = await hass.config_entries.flow.async_configure(
            second["flow_id"],
            {k: v for k, v in econiq_data.items() if k != "device_type"},
        )
        assert second["reason"] == "already_configured"


@pytest.mark.parametrize(
    "error,expected",
    [
        (PskUnavailableError(), "psk_unavailable"),
        (aiomqtt.MqttError(), "cannot_connect"),
        (TimeoutError(), "no_econiq_metadata"),
    ],
)
async def test_econiq_errors(hass, econiq_data, error, expected):
    with patch(
        "custom_components.ventaxia_ha.config_flow.validate_econiq", side_effect=error
    ):
        result = await start_flow(hass, "econiq")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {k: v for k, v in econiq_data.items() if k != "device_type"},
        )
        assert result["errors"] == {"base": expected}


async def test_econiq_invalid_key(hass, econiq_data):
    econiq_data["psk_key"] = "0000"
    with patch("custom_components.ventaxia_ha.config_flow.validate_econiq") as validate:
        result = await start_flow(hass, "econiq")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {k: v for k, v in econiq_data.items() if k != "device_type"},
        )
        assert result["errors"] == {"base": "invalid_psk_or_prefix"}
        validate.assert_not_called()


async def test_kinetic_success_with_econiq_entry(hass, econiq_data):
    MockConfigEntry(
        domain=DOMAIN, unique_id="econiq:TEST-UNIT", data=econiq_data
    ).add_to_hass(hass)
    with patch(
        "custom_components.ventaxia_ha.config_flow.validate_input",
        return_value={"title": "Kinetic test"},
    ), patch("custom_components.ventaxia_ha.async_setup_entry", return_value=True):
        result = await start_flow(hass, "kinetic")
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], KINETIC_DATA
        )
        assert result["type"] == "create_entry"
        assert result["result"].unique_id == "KINETIC-TEST"
        assert "device_type" not in result["data"]


async def test_validation_receives_metadata_without_commands(
    hass, econiq_data, fake_client
):
    fake_client.metadata()
    fake_client.subscribe.return_value = [SimpleNamespace(value=0)]
    with patch(
        "custom_components.ventaxia_ha.config_flow.create_client",
        return_value=fake_client,
    ):
        assert await validate_econiq(hass, econiq_data) == {"title": "Econiq 300"}
    fake_client.publish.assert_not_awaited()
    assert fake_client.closed


async def test_validation_accepts_paho_reason_code_suback(
    hass, econiq_data, fake_client
):
    fake_client.subscribe.return_value = [SimpleNamespace(value=0)]
    fake_client.feed("vent/afs/fm", b"33")
    with patch(
        "custom_components.ventaxia_ha.config_flow.create_client",
        return_value=fake_client,
    ):
        result = await validate_econiq(hass, econiq_data)
    assert result["title"] == "Sentinel Econiq (vmc.example)"
    assert fake_client.closed


async def test_validation_accepts_known_telemetry_without_model_metadata(
    hass, econiq_data, fake_client
):
    fake_client.feed("vent/afs/fm", b"33")
    fake_client.feed("mdet/wifi/sta", b'{"rssi":-72,"mode":2}')
    with patch(
        "custom_components.ventaxia_ha.config_flow.create_client",
        return_value=fake_client,
    ):
        result = await validate_econiq(hass, econiq_data)
    assert result["title"] == "Sentinel Econiq (vmc.example)"
    fake_client.publish.assert_not_awaited()
    assert fake_client.closed


async def test_validation_reports_timeout_only_after_successful_subscribe(
    hass, econiq_data, fake_client
):
    fake_client.queue.put_nowait(TimeoutError("simulated metadata wait timeout"))
    with patch(
        "custom_components.ventaxia_ha.config_flow.create_client",
        return_value=fake_client,
    ):
        with pytest.raises(TimeoutError):
            await validate_econiq(hass, econiq_data)
    fake_client.subscribe.assert_awaited_once_with("TEST-UNIT/#", qos=0)
    assert fake_client.closed


async def test_validation_reports_rejected_subscription_as_connection_error(
    hass, econiq_data, fake_client
):
    fake_client.subscribe.return_value = [128]
    with patch(
        "custom_components.ventaxia_ha.config_flow.create_client",
        return_value=fake_client,
    ):
        with pytest.raises(CannotConnect, match="subscription was rejected"):
            await validate_econiq(hass, econiq_data)
    assert fake_client.closed


async def test_kinetic_validation_cleanup(hass):
    client = AsyncMock()
    client.connect.side_effect = ConnectionError("simulated")
    with patch(
        "custom_components.ventaxia_ha.config_flow.AsyncNativePskClient",
        return_value=client,
    ):
        with pytest.raises(ConnectionError):
            await validate_input(hass, KINETIC_DATA)
    client.close.assert_awaited_once()
