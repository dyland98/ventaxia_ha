"""Prepare mode/duration locally, then explicitly apply a timed override."""

from homeassistant.components.button import ButtonEntity
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .econiq import ECONIQ_DURATIONS, ECONIQ_SELECT_MODES
from .econiq_entities import EconiqEntity


class EconiqOverrideSelect(EconiqEntity, RestoreEntity, SelectEntity):
    """Selections are requested settings, distinct from confirmed telemetry."""

    _attr_icon = "mdi:fan-clock"

    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self.key = key
        self._attr_options = (
            list(ECONIQ_SELECT_MODES)
            if key == "override_mode"
            else [str(value) for value in ECONIQ_DURATIONS]
        )

    @property
    def current_option(self):
        if self.key == "override_mode":
            return self.coordinator.selected_mode
        return str(self.coordinator.selected_duration)

    @property
    def extra_state_attributes(self):
        if self.key != "override_mode":
            return None
        values = self.coordinator.cache.values
        return {
            "profile_names": {
                mode: values.get(f"vent/pf{i}", {}).get("name")
                for i, mode in enumerate(("low", "normal", "boost", "purge"), 1)
            }
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state in self.options:
            self._set_selection(last_state.state)

    def _set_selection(self, option):
        if option not in self.options:
            raise ValueError("Invalid override selection")
        if self.key == "override_mode":
            self.coordinator.select_override(mode=option)
        else:
            self.coordinator.select_override(duration=int(option))

    async def async_select_option(self, option):
        self._set_selection(option)


class EconiqApplyOverrideButton(EconiqEntity, ButtonEntity):
    _attr_icon = "mdi:play-circle-outline"

    def __init__(self, coordinator):
        super().__init__(coordinator, "apply_override")

    async def async_press(self):
        await self.coordinator.async_apply_override()


class EconiqCancelOverrideButton(EconiqEntity, ButtonEntity):
    _attr_icon = "mdi:cancel"

    def __init__(self, coordinator):
        super().__init__(coordinator, "cancel_selected_override")

    async def async_press(self):
        await self.coordinator.async_cancel_selected_override()
