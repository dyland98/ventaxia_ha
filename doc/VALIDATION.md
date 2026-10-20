# Local validation — 2026-10-20

Working tree: `feat/econiq-hacs`; candidate version `0.3.0`.
Remote `origin`: `https://github.com/dyland98/ventaxia_ha.git`; no `upstream`.
No commit, push, tag, GitHub release, Home Assistant deployment or device command
was made. No second repository was cloned.

Environment: macOS, Python 3.14.4, OpenSSL 3.0.19, Home Assistant 2026.10.0,
aiomqtt 2.5.1, ventaxiaiot 0.1.12. Native `ssl.HAS_PSK` and
`SSLContext.set_psk_client_callback` are available **locally**. The installed
ventaxiaiot source was inspected: its Kinetic client encodes its Wi-Fi key as
UTF-8 and uses a separate message processor/command API. Econiq instead decodes
hex bytes and uses MQTT; the two transports are not shared.

Passed commands:

```sh
.venv/bin/pytest --disable-socket --allow-unix-socket tests
.venv/bin/black --check custom_components scripts tests
.venv/bin/isort --check-only --profile black custom_components scripts tests
.venv/bin/flake8 custom_components scripts tests
.venv/bin/python scripts/check_release.py --tag v0.3.0
git diff --check
```

Results: **29 tests passed**. JSON and GitHub YAML parsed successfully.
The release check rejected an intentionally mismatched `v9.9.9` tag.
Unix sockets are allowed only for asyncio's internal wakeup mechanism; network
sockets remain blocked and all MQTT clients in these tests are simulated.

Tests cover hexadecimal decoding, native TLS context settings, invalid keys and
prefixes, model selection, duplicate entries, configuration failures, metadata
validation, partial cache updates, malformed/nonfinite payloads, raw warning
values, exact Boost/cancel publications with QoS 0 and retain false, no optimistic
mode confirmation, disconnect availability, reconnect/stable client ID, shutdown,
HA entity registration, push updates, unload/listener cleanup, redacted diagnostics
and selection of the existing Kinetic backend for entries without `device_type`.

Limits: HACS/Hassfest actions are prepared but have not run on GitHub. GitHub
Actions/Issues settings and public accessibility of the fork were not verified
(the web reader could not retrieve the fork). The config-flow tests mock the
frontend dependency, and the platform integration test mocks global setup;
these tests do not validate the bundled Lovelace card or a full HA installation.
Kinetic hardware behavior has not been regression-tested. The actual Proxmox HA
runtime, physical Econiq telemetry, Boost/cancellation, reboot/reconnect behavior,
HACS installation and subsequent HACS update have **not** been tested.

Follow [the French installation and hardware-validation procedure](HACS_FR.md)
to complete those checks before claiming device or HACS validation.
