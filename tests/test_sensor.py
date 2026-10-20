"""HA entry setup selects only the appropriate entities and unloads cleanly."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import Platform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ventaxia_ha import async_setup_entry, async_unload_entry
from custom_components.ventaxia_ha.button import async_setup_entry as setup_buttons
from custom_components.ventaxia_ha.const import DOMAIN
from custom_components.ventaxia_ha.econiq_entities import (
    EconiqBoostButton,
    EconiqModeButton,
    EconiqSensor,
)
from custom_components.ventaxia_ha.sensor import async_setup_entry as setup_sensors


async def test_econiq_platforms(hass, econiq_data, fake_client):
    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    entry.add_to_hass(hass)
    fake_client.metadata()
    with patch(
        "custom_components.ventaxia_ha.econiq_coordinator.create_client",
        return_value=fake_client,
    ), patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ) as forward:
        assert await async_setup_entry(hass, entry)
        forward.assert_awaited_once_with(entry, [Platform.SENSOR, Platform.BUTTON])
        sensors = []
        buttons = []
        await setup_sensors(hass, entry, lambda entities: sensors.extend(entities))
        await setup_buttons(hass, entry, lambda entities: buttons.extend(entities))
        assert len(sensors) > 20 and all(isinstance(s, EconiqSensor) for s in sensors)
        assert len(buttons) == 6
        assert sum(isinstance(button, EconiqBoostButton) for button in buttons) == 2
        assert sum(isinstance(button, EconiqModeButton) for button in buttons) == 4
        assert len({s.unique_id for s in sensors}) == len(sensors)
        assert {s.device_info["identifiers"].pop() for s in sensors} == {
            (DOMAIN, "econiq:TEST-UNIT")
        }
        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=False
        ):
            assert not await async_unload_entry(hass, entry)
            assert hass.data[DOMAIN][entry.entry_id].available
        with patch.object(
            hass.config_entries, "async_unload_platforms", return_value=True
        ):
            assert await async_unload_entry(hass, entry)
        assert fake_client.closed
        assert entry.entry_id not in hass.data[DOMAIN]


async def test_old_entry_uses_kinetic(hass):
    entry = MockConfigEntry(
        domain=DOMAIN, data={"wifi_device_id": "legacy"}, unique_id="legacy"
    )
    entry.add_to_hass(hass)
    coordinator = AsyncMock()
    with patch(
        "custom_components.ventaxia_ha.VentAxiaCoordinator", return_value=coordinator
    ) as factory, patch.object(
        hass.config_entries, "async_forward_entry_setups", new=AsyncMock()
    ) as forward:
        assert await async_setup_entry(hass, entry)
        factory.assert_called_once_with(hass, entry)
        forward.assert_awaited_once_with(
            entry, [Platform.SENSOR, Platform.BUTTON, Platform.SELECT]
        )
    with patch.object(hass.config_entries, "async_unload_platforms", return_value=True):
        assert await async_unload_entry(hass, entry)
    coordinator.async_stop.assert_awaited_once()


async def test_entities_registered_in_home_assistant(hass, econiq_data, fake_client):
    """Exercise real HA platform setup, translation, push updates and cleanup."""
    from homeassistant.helpers import entity_registry as er
    from pytest_homeassistant_custom_component.common import mock_component

    mock_component(hass, "frontend")
    entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:TEST-UNIT"
    )
    entry.add_to_hass(hass)
    fake_client.metadata()
    fake_client.feed("io/t1", b"9.8")
    with patch(
        "custom_components.ventaxia_ha.econiq_coordinator.create_client",
        return_value=fake_client,
    ), patch("custom_components.ventaxia_ha.async_setup", return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        entity_id = registry.async_get_entity_id(
            "sensor", DOMAIN, "econiq:TEST-UNIT_t1"
        )
        assert entity_id
        assert hass.states.get(entity_id).state == "9.8"
        assert hass.states.get(entity_id).attributes["unit_of_measurement"] == "°C"
        fake_client.feed("io/t1", b"nan")
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "unknown"
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert len(coordinator._callbacks) > 20
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert not coordinator._callbacks
        assert fake_client.closed
