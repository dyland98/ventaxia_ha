"""HA entry setup selects only the appropriate entities and unloads cleanly."""

from unittest.mock import AsyncMock, patch

from homeassistant.const import Platform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ventaxia_ha import async_setup_entry, async_unload_entry
from custom_components.ventaxia_ha.button import async_setup_entry as setup_buttons
from custom_components.ventaxia_ha.const import DOMAIN
from custom_components.ventaxia_ha.econiq_entities import (
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
        forward.assert_awaited_once_with(
            entry,
            [Platform.SENSOR, Platform.BUTTON, Platform.SELECT, Platform.BINARY_SENSOR],
        )
        sensors = []
        buttons = []
        await setup_sensors(hass, entry, lambda entities: sensors.extend(entities))
        await setup_buttons(hass, entry, lambda entities: buttons.extend(entities))
        assert len(sensors) > 20 and all(isinstance(s, EconiqSensor) for s in sensors)
        assert {button.unique_id for button in buttons} == {
            "econiq:TEST-UNIT_apply_override",
            "econiq:TEST-UNIT_cancel_selected_override",
        }
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
    registry = er.async_get(hass)
    retired = []
    for key in (
        "boost_15",
        "cancel_boost",
        "low_15_unverified",
        "normal_15_unverified",
        "purge_15_unverified",
        "maximum_15_unverified",
    ):
        retired.append(
            registry.async_get_or_create(
                "button",
                DOMAIN,
                f"{entry.unique_id}_{key}",
                config_entry=entry,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION,
            ).entity_id
        )
    cancel = registry.async_get_or_create(
        "button",
        DOMAIN,
        f"{entry.unique_id}_cancel_selected_override",
        config_entry=entry,
        suggested_object_id="my_existing_cancel",
    )
    unrelated = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.unique_id}_boost_15",
        config_entry=entry,
    )
    other_entry = MockConfigEntry(
        domain=DOMAIN, data=econiq_data, unique_id="econiq:OTHER"
    )
    other_entry.add_to_hass(hass)
    other = registry.async_get_or_create(
        "button",
        DOMAIN,
        "econiq:OTHER_boost_15",
        config_entry=other_entry,
    )
    fake_client.metadata()
    fake_client.feed("io/t1", b"9.8")
    with patch(
        "custom_components.ventaxia_ha.econiq_coordinator.create_client",
        return_value=fake_client,
    ), patch("custom_components.ventaxia_ha.async_setup", return_value=True):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        assert all(registry.async_get(entity_id) is None for entity_id in retired)
        assert registry.async_get(unrelated.entity_id)
        assert registry.async_get(other.entity_id)
        assert (
            registry.async_get_entity_id(
                "button", DOMAIN, f"{entry.unique_id}_cancel_selected_override"
            )
            == cancel.entity_id
        )
        assert (
            hass.states.get(cancel.entity_id)
            .attributes["friendly_name"]
            .endswith("Cancel selected override")
        )
        fake_client.publish.assert_not_awaited()
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
