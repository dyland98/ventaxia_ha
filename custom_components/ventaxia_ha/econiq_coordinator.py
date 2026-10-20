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
    EconiqCache,
    boost_payload,
    create_client,
    create_tls_context,
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
                    self._client = client
                    # Require fresh metadata after every connection before exposing controls.
                    self.cache.values.clear()
                    async for message in client.messages:
                        if self.cache.update(
                            str(message.topic), bytes(message.payload)
                        ):
                            self.available = self.cache.valid_device
                            if self.available:
                                self._ready.set()
                                delay = 2
                            self._notify_update()
            except aiomqtt.MqttError:
                # Do not log connection exceptions or credentials.
                _LOGGER.warning("Econiq MQTT connection unavailable; retrying")
            finally:
                self._client = None
                self.available = False
                self._notify_update()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def async_boost(self, cancel=False):
        if not self.available or self._client is None:
            raise HomeAssistantError("Econiq is disconnected")
        try:
            await self._client.publish(
                self.cache.prefix + "vent/uo",
                boost_payload(cancel),
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
