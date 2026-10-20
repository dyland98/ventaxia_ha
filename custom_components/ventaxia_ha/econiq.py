"""Econiq MQTT protocol. No Kinetic protocol assumptions or device writes."""

from __future__ import annotations

import json
import math
import re
import ssl

import aiomqtt

CONF_DEVICE_TYPE = "device_type"
CONF_PREFIX = "mqtt_prefix"
ECONIQ = "econiq"
KINETIC = "kinetic"

# APK-reported SDK modes. OFF is intentionally excluded to avoid stopping
# ventilation; non-Boost modes have not yet been validated on hardware.
ECONIQ_MODE_IDS = {"low": 1, "normal": 2, "boost": 3, "purge": 4, "maximum": 5}


class PskUnavailableError(RuntimeError):
    """The Python/OpenSSL runtime cannot provide TLS-PSK."""


def parse_psk(value: str) -> bytes:
    """Decode hexadecimal bytes, rejecting empty, malformed and all-zero keys."""
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2})+", value):
        raise ValueError("Invalid hexadecimal PSK")
    key = bytes.fromhex(value)
    if not any(key):
        raise ValueError("Zero PSK is not allowed")
    return key


def normalize_prefix(value: str) -> str:
    """Accept an explicit MQTT prefix, never infer it from a Wi-Fi SSID."""
    prefix = value.strip().rstrip("/")
    if not prefix or any(c in prefix for c in ("+", "#", "\x00")):
        raise ValueError("Invalid MQTT prefix")
    return prefix


def create_tls_context(psk_hex: str, identity: str) -> ssl.SSLContext:
    """Use native TLS 1.2 PSK authentication, without certificates."""
    if not getattr(ssl, "HAS_PSK", False) or not hasattr(
        ssl.SSLContext, "set_psk_client_callback"
    ):
        raise PskUnavailableError("Python >=3.13 with OpenSSL PSK support is required")
    key = parse_psk(psk_hex)
    if not identity or "\x00" in identity or len(identity.encode()) > 256:
        raise ValueError("Invalid PSK identity")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.set_ciphers("PSK-AES128-CBC-SHA")
    except ssl.SSLError as err:
        raise PskUnavailableError(
            "OpenSSL does not provide PSK-AES128-CBC-SHA"
        ) from err
    context.set_psk_client_callback(lambda hint: (identity, key))
    return context


def create_client(
    data: dict, identifier: str, context: ssl.SSLContext
) -> aiomqtt.Client:
    """Connect directly to the VMC broker, without HA MQTT or credentials."""
    return aiomqtt.Client(
        hostname=data["host"],
        port=data["port"],
        identifier=identifier,
        protocol=aiomqtt.ProtocolVersion.V311,
        clean_session=True,
        keepalive=60,
        timeout=10,
        tls_context=context,
        max_queued_incoming_messages=1024,
    )


# Only these topics are accepted into the cache; do not store arbitrary MQTT data.
NUMERIC_TOPICS = {
    *(f"io/t{i}" for i in range(1, 5)),
    "io/erh/val",
    "io/irh/val",
    "io/eco2/val",
    "io/ico2/val",
    "zone/2/co2",
    "zone/2/t",
    "sn/1/rh",
    "mdet/pwr",
    "mdet/faults",
    "mdet/warns",
    "mdet/noti",
    "vent/cm",
    "vent/saq",
    "vent/maxaf",
    *(
        f"vent/{fan}/{field}"
        for fan in ("afs", "afe")
        for field in ("fm", "fd", "rpm", "pwr", "pwm", "dr")
    ),
    *(f"vent/filter{i}/{field}" for i in (1, 2) for field in ("pa", "lr")),
}
JSON_TOPICS = {"mdet/moddet", "mdet/wifi/sta", "vent/caf", "vent/cor"}


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


class EconiqCache:
    """Accumulate partial updates; unavailable measurements remain None."""

    def __init__(self, prefix: str) -> None:
        self.prefix = normalize_prefix(prefix) + "/"
        self.values: dict = {}

    def update(self, topic: str, payload: bytes) -> bool:
        if not topic.startswith(self.prefix) or len(payload) > 16384:
            return False
        topic = topic[len(self.prefix) :]
        try:
            text = payload.decode("utf-8")
            if topic in NUMERIC_TOPICS:
                value = float(text)
                value = value if math.isfinite(value) else None
            elif topic in JSON_TOPICS:
                value = _finite(json.loads(text))
                if not isinstance(value, dict):
                    return False
            elif topic == "mdet/name":
                value = text[:255]
            else:
                return False
        except (ValueError, UnicodeError, RecursionError):
            return False
        self.values[topic] = value
        return True

    @property
    def metadata(self) -> dict:
        return self.values.get("mdet/moddet", {})

    @property
    def valid_device(self) -> bool:
        model = self.metadata.get("mn")
        return (
            isinstance(model, str)
            and "econiq" in model.lower()
            and bool(self.metadata.get("sn"))
        )

    @property
    def has_telemetry(self) -> bool:
        """Whether at least one allowlisted device topic has parsed successfully."""
        return bool(self.values)


def boost_payload(cancel: bool = False) -> str:
    """Only Boost is exposed. Cancellation still needs hardware validation."""
    return json.dumps(
        {"gtm": 3, "treq": "00:00:00" if cancel else "00:15:00"}, separators=(",", ":")
    )


def mode_payload(mode: str, duration_minutes: int = 15) -> str:
    """Build a timed mode command; never expose OFF or persistent commands."""
    if mode not in ECONIQ_MODE_IDS:
        raise ValueError("Unsupported Econiq mode")
    if isinstance(duration_minutes, bool) or not 1 <= duration_minutes <= 60:
        raise ValueError("Mode duration must be between 1 and 60 minutes")
    hours, minutes = divmod(duration_minutes, 60)
    duration = f"{hours:02d}:{minutes:02d}:00"
    return json.dumps(
        {"gtm": ECONIQ_MODE_IDS[mode], "treq": duration}, separators=(",", ":")
    )
