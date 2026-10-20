# Ventaxia for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![License][license-shield]](LICENSE)

[![Project Maintenance][maintenance-shield]][user_profile]

[![Discord][discord-shield]][discord]
[![Community Forum][forum-shield]][forum]

This custom component integrates Vent Axia Sentinel Kinetic Advance S MVHR (mechanical ventilation with heat recovery) System with the Wifi module with [Home Assistant][ha], allowing you to monitor various parameters from your device.

# Supported Devices

The Kinetic backend uses the [ventaxiaiot Python library](https://github.com/JosyBan/ventaxiaiot). The Econiq backend uses a separate direct MQTT/TLS-PSK connection through aiomqtt. Supported models:

    Vent Axia Sentinel Kinetic Advance S
    Vent Axia Sentinel Econiq 300 (implementation pending hardware validation)

**This component will set up the following platforms.**

| Platform  | Description                                        |
| --------- | -------------------------------------------------- |
| `sensor`  | Provides various readings for your Ventaxia device |
| `button`  | Run some of the airflow commands                   |
| `service` | Add a service to update the airflow                |

![example][logo]

## Fork, compatibility and release procedure

This fork is maintained at **https://github.com/dyland98/ventaxia_ha**.
The original project is [JosyBan/ventaxia_ha](https://github.com/JosyBan/ventaxia_ha).
The MIT license and original credits are preserved.

The domain remains `ventaxia_ha`: changing it would affect imports, translation
lookup, services, device identifiers and existing config entries. Entries without
`device_type` continue to use Kinetic, with their existing unique IDs. Econiq
entries use `econiq:<mqtt_prefix>` and cannot invoke the Kinetic controls.

**Read the exact French guide: [installation, replacement, publication and updates](doc/HACS_FR.md).**
**Home Assistant 2026.10.0 or newer** is the declared, conservatively tested baseline.
Native TLS-PSK support is checked in the HA Python/OpenSSL runtime. Local automated
tests do not prove installation via HACS or operation on a physical VMC.
Version `0.3.0` is prepared locally; no GitHub release is implied by this README.

### Replacing the original installation

Back up Home Assistant and save the current integration folder. Remove
only the original repository/download in HACS, **keep the Vent Axia config entry in
Settings > Devices & Services**, then add this fork as an Integration custom
repository. Install it into the single `/config/custom_components/ventaxia_ha`
folder and restart HA. Removing a HACS download may remove the files: reinstall
the fork before restarting. Do not keep both repositories managing this domain,
and do not copy a second integration folder under another name. Existing Kinetic
entries should keep their entities; verify them after the restart.

## HACS Installation

This is the recommended way to install.

1. Open [HACS][hacs] in your Home Assistant UI
2. Click on the three dots in the top right corner and select Custom repositories.
3. In the "Add custom repository" field, paste https://github.com/dyland98/ventaxia_ha.
4. Select Integration as the Category.
5. Click ADD
6. Once added, search for "ventaxia" in the HACS Integrations section.
7. Click on the "ventaxia" integration.
8. Click Download and confirm.
9. Restart Home Assistant.
10. In the HA UI, click Settings in the left nav bar, then click "Devices & Services". By default you should be viewing the Integrations tab. Click "+ Add Integration" button at bottom right and then search for "ventaxia".

## Manual Installation

1. Download the integration: Download the latest release from the [Release Page][ventaxia-releases].
2. In the GitHub source archive, find `custom_components/ventaxia_ha` (not the repository root).
3. Stop Home Assistant, then copy that entire integration folder into your Home Assistant's custom_components directory. If this directory doesn't exist, you'll need to create it.
4. Your Home Assistant configuration directory typically resides at /config (e.g., /config/custom_components/ventaxia_ha/).
5. Restart Home Assistant.
6. In the HA UI, click Settings in the left nav bar, then click "Devices & Services". By default you should be viewing the Integrations tab. Click "+ Add Integration" button at bottom right and then search for "ventaxia".

## Econiq configuration

Add **Vent Axia** in Settings > Devices & Services and select **Sentinel Econiq**.
Enter its host, port (default 8883), PSK identity (default `zirconia`), private
hexadecimal PSK and explicit MQTT prefix, optionally ending with `/`. The prefix
is not the Wi-Fi SSID. No broker add-on, cloud account or bridge is needed.
The connection check establishes TLS/MQTT, subscribes to this prefix, then waits
up to 30 seconds for Econiq model/serial metadata. If that metadata does not
arrive, verify the prefix and device messages.

The hexadecimal PSK is decoded to bytes, never encoded as the literal hex text.
The key is masked in the form, stored in HA config entry storage and excluded
from exported diagnostics. Protect HA backups containing config entries.

Temperatures T1–T4 retain neutral names. Airflow `fm`/`fd` and filter `pa`/`lr`
values have no assumed units. Warnings/faults are raw values, not counts.
Mode shows raw `vent/caf.ps`; only `3` (Boost) is confirmed by the supplied traces.
Override attributes preserve `trem` without interpreting its time semantics.
Nonfinite or absent measurements become unknown, never zero. Connection loss
makes entities unavailable; a reconnect waits for fresh model metadata.

The **Boost 15 minutes** button sends `{"gtm":3,"treq":"00:15:00"}` to
`<prefix>/vent/uo`, QoS 0, retain false. The **Cancel Boost (to validate)** button
is disabled by default; enable it deliberately to test the APK-derived
`{"gtm":3,"treq":"00:00:00"}`. Neither button changes the displayed mode until
telemetry confirms it. No commands are sent on startup or reconnection.
The bundled Kinetic dashboard card and services are for Kinetic entries only.

## Kinetic configuration

After installation and restarting Home Assistant, you can configure the Ventaxia integration via the Home Assistant UI.

    Go to Settings > Devices & Services.

    Click on ADD INTEGRATION.

    Search for "Ventaxia" and select it.

    Follow the on-screen prompts to enter your Ventaxia device's connection details:

        Host/IP Address: The IP address or hostname of your Ventaxia device on your local network.

        Key: This is the WIFI Key printed on the device (see example image)

        Device ID: This is the WIFI SSID of the device (see example image)

![example][module]

Once successfully configured, the integration will automatically discover and create relevant sensor entities. You can find the full list of available entities under Settings > Devices & Services > Ventaxia integration once it's set up.

## Troubleshooting

Troubleshooting

    Integration not found after restart:
        Ensure the ventaxia_ha folder is directly inside custom_components (i.e., custom_components/ventaxia_ha/ and not custom_components/ventaxia_ha/ventaxia_ha/).
        Clear your browser cache.

    Failed to connect / Device offline:
        Verify the IP address or hostname entered during configuration is correct.
        Ensure your Ventaxia device is powered on and connected to your local network.
        Check for any firewall rules on your Home Assistant host or network that might be blocking communication with the Ventaxia device.
        Review your Home Assistant logs (Settings > System > Logs) for more specific error messages related to the ventaxia integration.

    Sensors not updating:
        Confirm that your Ventaxia device is actively operating.
        Restart Home Assistant to force a re-initialization of the integration.
        Check the Home Assistant logs for any errors originating from the ventaxia_ha component.

For further assistance, please open an issue on the GitHub repository.

<!---->

## Contributions are welcome!

If you want to contribute to this please read the [Contribution guidelines](CONTRIBUTING.md).

## Credits

Fork of [JosyBan/ventaxia_ha](https://github.com/JosyBan/ventaxia_ha), copyright (c) 2025 JosyBan, MIT licensed.

This project was generated from [@oncleben31](https://github.com/oncleben31)'s [Home Assistant Custom Component Cookiecutter](https://github.com/oncleben31/cookiecutter-homeassistant-custom-component) template.

Code template was mainly taken from [@Ludeeus](https://github.com/ludeeus)'s [integration_blueprint][integration_blueprint] template.

And it was heavely inspired by [@CJNE](https://github.com/CJNE)'s [ha-myenergi] project.

---

[integration_blueprint]: https://github.com/custom-components/integration_blueprint
[ha-myenergi]: https://github.com/CJNE/ha-myenergi
[ventaxia_ha]: https://github.com/dyland98/ventaxia_ha
[ventaxia-releases]: https://github.com/dyland98/ventaxia_ha/releases
[commits]: https://github.com/dyland98/ventaxia_ha/commits/main/
[ha]: https://home-assistant.io
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge
[discord]: https://discord.gg/Qa5fW2R
[discord-shield]: https://img.shields.io/discord/330944238910963714.svg?style=for-the-badge
[logo]: logo@2x.png
[module]: advance_wifi_module.png
[forum-shield]: https://img.shields.io/badge/community-forum-brightgreen.svg?style=for-the-badge
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/dyland98/ventaxia_ha.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40dyland98-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/v/release/dyland98/ventaxia_ha.svg?style=for-the-badge
[releases]: https://github.com/dyland98/ventaxia_ha/releases
[user_profile]: https://github.com/dyland98
