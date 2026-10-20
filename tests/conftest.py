"""All device traffic is simulated; real sockets are disabled by pytest."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def econiq_data():
    # Synthetic key, never a real device credential.
    return {
        "device_type": "econiq",
        "host": "vmc.example",
        "port": 8883,
        "identity": "zirconia",
        "psk_key": "a1b2c3d4",
        "mqtt_prefix": "TEST-UNIT",
    }


class FakeClient:
    def __init__(self):
        self.queue = asyncio.Queue()
        self.subscribe = AsyncMock()
        self.publish = AsyncMock()
        self.closed = False
        self.messages = self
        self.connect_error = None

    async def __aenter__(self):
        if self.connect_error:
            raise self.connect_error
        return self

    async def __aexit__(self, *args):
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        message = await self.queue.get()
        if isinstance(message, Exception):
            raise message
        return message

    def feed(self, topic, payload):
        self.queue.put_nowait(
            SimpleNamespace(topic=f"TEST-UNIT/{topic}", payload=payload)
        )

    def metadata(self):
        self.feed(
            "mdet/moddet", b'{"sn":"synthetic-unit","mn":"Econiq 300","fwv":1012004}'
        )


@pytest.fixture
def fake_client():
    return FakeClient()
