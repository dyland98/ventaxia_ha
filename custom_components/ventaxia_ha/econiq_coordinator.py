"""Persistent push connection for Econiq, with bounded reconnect backoff."""

from __future__ import annotations

import asyncio
import logging

import aiomqtt
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
from .econiq import (
    CONF_PREFIX,
    ECONIQ_DURATIONS,
    ECONIQ_MODE_IDS,
    ECONIQ_SELECT_MODES,
    EconiqCache,
    boost_payload,
    cancel_payload,
    create_client,
    create_tls_context,
    mode_payload,
)

_LOGGER = logging.getLogger(__name__)


class EconiqCoordinator:
    """Own one MQTT session and notify entities on messages and disconnects."""

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.data = entry.data
        self.cache = EconiqCache(self.data[CONF_PREFIX])
        self.available = False
        self._callbacks = set()
        self._client = None
        self._task = None
        self._ready = asyncio.Event()
        self._context = None
        self.selected_mode = "boost"
        self.selected_duration = 15

    @property
    def device_info(self):
        metadata = self.cache.metadata
        return DeviceInfo(
            identifiers={(DOMAIN, self.entry.unique_id)},
            manufacturer="Vent-Axia",
            name=metadata.get("mn", "Sentinel Econiq"),
            model=metadata.get("mn"),
            serial_number=str(metadata["sn"]) if metadata.get("sn") else None,
            sw_version=str(metadata["fwv"]) if metadata.get("fwv") else None,
        )

    def add_update_callback(self, callback):
        self._callbacks.add(callback)

    def remove_update_callback(self, callback):
        self._callbacks.discard(callback)

    def _notify_update(self):
        for callback in tuple(self._callbacks):
            callback()

    async def async_start(self):
        self._context = await self.hass.async_add_executor_job(
            create_tls_context, self.data["psk_key"], self.data["identity"]
        )
        self._task = self.entry.async_create_background_task(
            self.hass, self._run(), "econiq_mqtt"
        )
        try:
            async with asyncio.timeout(20):
                await self._ready.wait()
        except BaseException:
            await self.async_stop()
            raise

    async def _run(self):
        delay = 2
        while True:
            try:
                # Keep the identifier stable across reloads and reconnects.
                async with create_client(
                    self.data, f"ha-econiq-{self.entry.entry_id}", self._context
                ) as client:
                    await client.subscribe(self.cache.prefix + "#", qos=0)
                    # Keep the single wildcard subscription validated on Econiq.
                    # Additional/multi-topic SUBSCRIBE packets can close the broker
                    # session; catching that error cannot restore the dead socket.
                    self._client = client
                    # Require fresh, allowlisted telemetry after every connection.
                    self.cache.values.clear()
                    async for message in client.messages:
                        if self.cache.update(
                            str(message.topic), bytes(message.payload)
                        ):
                            # Some devices do not publish mdet/moddet in response
                            # to a fresh subscription. Valid allowlisted telemetry
                            # still confirms the active MQTT data path.
                            self.available = self.cache.has_telemetry
                            if self.available:
                                self._ready.set()
                                delay = 2
                            self._notify_update()
            except aiomqtt.MqttError as err:
                # Keep diagnostics useful without logging exception text, PSK,
                # identity or telemetry. Return codes are optional in aiomqtt.
                code = getattr(err, "rc", None)
                code = getattr(code, "value", code)
                _LOGGER.warning(
                    "Econiq MQTT connection unavailable (%s, code=%s); retrying",
                    type(err).__name__,
                    code if isinstance(code, int) else "unknown",
                )
            finally:
                self._client = None
                self.available = False
                self._notify_update()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def async_boost(self, cancel=False):
        await self._async_publish_command(boost_payload(cancel))

    async def async_set_mode(self, mode: str, duration_minutes: int = 15):
        """Send an explicitly requested timed mode command."""
        if mode not in ECONIQ_MODE_IDS:
            raise HomeAssistantError("Unsupported Econiq mode")
        await self._async_publish_command(mode_payload(mode, duration_minutes))

    def select_override(self, *, mode=None, duration=None):
        """Prepare a local request without sending a device command."""
        if mode is not None:
            if mode not in ECONIQ_SELECT_MODES:
                raise ValueError("Unsupported mode selection")
            self.selected_mode = mode
        if duration is not None:
            if (
                isinstance(duration, bool)
                or not isinstance(duration, int)
                or duration not in ECONIQ_DURATIONS
            ):
                raise ValueError("Unsupported override duration")
            self.selected_duration = duration
        self._notify_update()

    async def async_apply_override(self):
        await self.async_set_mode(self.selected_mode, self.selected_duration)

    async def async_cancel_selected_override(self):
        await self._async_publish_command(cancel_payload(self.selected_mode))

    async def _async_publish_command(self, payload: str):
        if not self.available or self._client is None:
            raise HomeAssistantError("Econiq is disconnected")
        try:
            await self._client.publish(
                self.cache.prefix + "vent/uo",
                payload,
                qos=0,
                retain=False,
            )
        except aiomqtt.MqttError as err:
            raise HomeAssistantError("Econiq command could not be sent") from err
        # Successful publish means sent, never infer a confirmed mode here.

    async def async_stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.available = False
        self._notify_update()
