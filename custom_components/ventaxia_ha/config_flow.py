# File: ventaxia_ha/config_flow.py
"""Config flow for VentAxia IoT integration."""

from __future__ import annotations

import asyncio
import logging
import ssl
from typing import Any
import uuid

import aiomqtt
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import selector
from ventaxiaiot import AsyncNativePskClient
import voluptuous as vol

from .const import (
    CONF_IDENTITY,
    CONF_PSK_KEY,
    CONF_WIFI_DEVICE_ID,
    DEFAULT_PORT,
    DOMAIN,
)
from .econiq import (
    CONF_DEVICE_TYPE,
    CONF_PREFIX,
    ECONIQ,
    KINETIC,
    EconiqCache,
    PskUnavailableError,
    create_client,
    create_tls_context,
    normalize_prefix,
    parse_psk,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, description={"suggested_value": DEFAULT_PORT}): int,
        vol.Required(CONF_IDENTITY): str,
        vol.Required(CONF_PSK_KEY): str,
        vol.Required(CONF_WIFI_DEVICE_ID): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    client = AsyncNativePskClient(
        wifi_device_id=data[CONF_WIFI_DEVICE_ID],
        identity=data[CONF_IDENTITY],
        psk_key=data[CONF_PSK_KEY],
        host=data[CONF_HOST],
        port=data[CONF_PORT],
    )

    try:
        await client.connect(timeout=10.0)
    except ssl.SSLError as err:
        if "application data after close notify" in str(err):
            _LOGGER.error(
                "Non-critical SSL shutdown error (device misbehavior): %s", err
            )
        elif (
            "bad record mac" in str(err).lower()
            or "wrong version number" in str(err).lower()
        ):
            _LOGGER.error("Invalid credentials: %s", err)
            raise InvalidAuth from err
        else:
            _LOGGER.error("Cannot connect to VentAxia device: %s", err)
            raise CannotConnect from err
    except Exception as err:
        _LOGGER.error("Cannot connect to VentAxia device: %s", err)
        raise

    finally:
        await client.close()

    return {"title": f"VentAxia Device ({data[CONF_HOST]})"}


ECONIQ_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=8883): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_IDENTITY, default="zirconia"): str,
        vol.Required(CONF_PSK_KEY): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_PREFIX): str,
    }
)


async def validate_econiq(hass, data):
    """Validate TLS, MQTT subscription and device telemetry without commands."""
    context = await hass.async_add_executor_job(
        create_tls_context, data[CONF_PSK_KEY], data[CONF_IDENTITY]
    )
    cache = EconiqCache(data[CONF_PREFIX])
    async with create_client(
        data, f"ha-econiq-check-{uuid.uuid4().hex[:12]}", context
    ) as client:
        subscription = await client.subscribe(cache.prefix + "#", qos=0)
        if subscription and any(
            int(getattr(reason, "value", reason)) >= 128 for reason in subscription
        ):
            raise CannotConnect("MQTT subscription was rejected")
        # Keep connection and subscription outside this timeout so their errors
        # cannot be mistaken for missing telemetry.
        async with asyncio.timeout(30):
            async for message in client.messages:
                cache.update(str(message.topic), bytes(message.payload))
                if cache.has_telemetry:
                    model = cache.metadata.get("mn")
                    title = (
                        model
                        if isinstance(model, str) and "econiq" in model.lower()
                        else f"Sentinel Econiq ({data[CONF_HOST]})"
                    )
                    return {"title": title}
        raise CannotConnect("MQTT connection ended before Econiq metadata arrived")


class VentAxiaFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VentAxia IoT."""

    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input[CONF_DEVICE_TYPE] == ECONIQ:
                return await self.async_step_econiq()
            return await self.async_step_kinetic()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "label": "Sentinel Kinetic Advance S",
                                    "value": KINETIC,
                                },
                                {
                                    "label": "Sentinel Econiq (MQTT TLS-PSK)",
                                    "value": ECONIQ,
                                },
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_econiq(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            data = dict(user_input)
            data[CONF_DEVICE_TYPE] = ECONIQ
            try:
                parse_psk(data[CONF_PSK_KEY])
                data[CONF_PREFIX] = normalize_prefix(data[CONF_PREFIX])
                if (
                    not data[CONF_IDENTITY]
                    or "\x00" in data[CONF_IDENTITY]
                    or len(data[CONF_IDENTITY].encode()) > 256
                ):
                    raise ValueError("Invalid identity")
            except ValueError:
                errors["base"] = "invalid_psk_or_prefix"
            else:
                await self.async_set_unique_id(f"econiq:{data[CONF_PREFIX]}")
                self._abort_if_unique_id_configured()
                try:
                    info = await validate_econiq(self.hass, data)
                except PskUnavailableError:
                    errors["base"] = "psk_unavailable"
                except ssl.SSLError:
                    errors["base"] = "auth"
                except TimeoutError:
                    errors["base"] = "no_econiq_metadata"
                except (aiomqtt.MqttError, OSError, CannotConnect):
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(title=info["title"], data=data)
        return self.async_show_form(
            step_id="econiq", data_schema=ECONIQ_SCHEMA, errors=errors
        )

    async def async_step_kinetic(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except InvalidAuth:
                errors["base"] = "auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Create unique ID based on wifi_device_id
                await self.async_set_unique_id(user_input[CONF_WIFI_DEVICE_ID])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="kinetic", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate invalid authentication credentials."""
