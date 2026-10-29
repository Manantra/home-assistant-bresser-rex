# BRESSER REX for Home Assistant (unofficial)

[![Protocol tests](https://github.com/Manantra/home-assistant-bresser-rex/actions/workflows/tests.yml/badge.svg)](https://github.com/Manantra/home-assistant-bresser-rex/actions/workflows/tests.yml)
[![HACS validation](https://github.com/Manantra/home-assistant-bresser-rex/actions/workflows/hacs.yml/badge.svg)](https://github.com/Manantra/home-assistant-bresser-rex/actions/workflows/hacs.yml)

**Experimental community integration** for BRESSER REX / supported FlashForge Adventurer III–compatible printers using the **local** network protocol. No firmware changes, cloud account, or OctoPrint installation required.

> Unofficial independent community project. Not affiliated with or endorsed by BRESSER, FlashForge or Home Assistant. Core functionality of v0.2.0 has been validated on a physical BRESSER REX using firmware v1.3.7. The new optional smart-plug feature in v0.3.0 is **awaiting hardware validation**.

## Supported devices

| Device | Status |
| --- | --- |
| BRESSER REX (Adventurer III-compatible) | v0.2.0 core Home Assistant functions verified on firmware v1.3.7; v0.3.0 smart-plug beta |
| FlashForge Adventurer III / Adventurer 3 | Underlying protocol family compatible; integration not yet hardware-tested across variants |
| Other FlashForge printers | Not supported without verification |

Printer detection requires `M115` to identify `FlashForge Adventurer III` / `Adventurer 3` and provide an SN. Support for additional printer models must be verified before changing detection.

## Features

- UI configuration wizard: enter a **local** IP address or DNS/mDNS hostname, test TCP connection and detect printer model/serial.
- Single device in Home Assistant's device registry; multiple different printers may be added.
- Sensors: nozzle temperature, nozzle target, bed temperature, bed target, machine status, current print file, active print progress (conditional).
- **Optimistic LED switch:** uses `M146`, while avoiding the printer's unreliable `M119` LED state. The actual light state is unknown after restarting Home Assistant or adjusting it elsewhere.
- Optional MJPEG camera, using the printer's camera stream on TCP port 8080 and Home Assistant's authenticated camera view.
- Reconfigure IP/hostname later, preserving identity; options for camera enabled/disabled and refresh interval (15–300 seconds; default 30 seconds).
- **Optional smart socket (v0.3.0 beta):** select an existing Home Assistant `switch` entity to show power supply status on the printer device. When it reports `off`, printer network polling is skipped and stale temperature/print data is cleared. The integration does not switch the socket on or off.
- English and German setup and entity names.
- Polling and LED commands serialized through a single coordinator; error handling for busy devices.

**Not available yet:** file upload, start/stop print, axis movement, heater controls, verified estimated finish time or verified filament sensor state. Polling while another program holds the control channel may fail temporarily.

## Installation

### Manual (recommended for initial testing)

1. Back up Home Assistant.
2. Copy `custom_components/bresser_rex/` from this repository to `/config/custom_components/bresser_rex/`.
3. Fully restart Home Assistant.
4. Go to **Settings → Devices & services → Add integration** and search **BRESSER REX (unofficial)**.
5. Enter your printer's **own** IP address or local hostname (without `http://`, port or path). The wizard verifies the printer and prevents adding the same serial twice.
6. Open the created device to view sensors, LED switch and camera.

### HACS (after public repository is created)

In HACS, add `https://github.com/Manantra/home-assistant-bresser-rex` as a **custom repository** of type **Integration**. Install it, restart Home Assistant and use the standard add-integration wizard above. After installing or updating the files, restart Home Assistant. This custom repository has passed HACS validation for earlier beta versions.

## Configuration & device identity

- Hostname/IP is **never hardcoded** in this project. Home Assistant stores it locally in its config entry.
- To change a printer's address: **Settings → Devices & services → BRESSER REX → Reconfigure**. The wizard checks that the replacement address returns the **same serial number**.
- To change polling, camera or the optional smart socket: select **Configure** on the integration entry.
- The selected socket entity ID is stored only in Home Assistant's local integration options; no addresses or other private identifiers are committed to the repository.
- The printer serial is used only as a stable identifier within the user's **local Home Assistant configuration**. It is not logged by this integration or sent anywhere else. Never post it in a public issue.
- For multiple printers, each must have its own serial number and IP/hostname.

## Optional smart socket (v0.3.0 beta)

Select **Settings → Devices & services → BRESSER REX → Configure → Smart plug (optional)** and choose the Home Assistant `switch` entity that supplies power to your printer. Leave this field blank to use the original network-only behaviour.

| Socket switch state | Printer status | Temperatures/file/progress | LED and camera | TCP polling |
| --- | --- | --- | --- | --- |
| `off` | `OFF` | Cleared (unknown, not stale) | Unavailable | Stopped |
| `on` | `STARTING` then actual printer status | Refreshed when printer responds | Available | Resumes |
| `unknown` / `unavailable` | Determined by regular network poll | Determined by regular network poll | Normal network behaviour | Continues |
| Not configured | Original behaviour | Original behaviour | Original behaviour | Continues |

A separate **Power supply** binary sensor is created on the printer device when a socket is selected. It reflects the external switch's reported on/off state, even when TCP polling fails. It cannot independently confirm that the printer has finished starting or that its physical power switch is on. **The integration does not control power to the printer.**

When powered off, no failed printer connections are generated by polling, and old temperatures and print progress are cleared instead of being displayed as current readings. The LED entity and camera are marked unavailable while there is no power, which accurately describes their function. The printer status stays available and reads `OFF`. If the switch itself is unreachable, the power binary sensor becomes unavailable rather than making a false off claim.

**Suggested hardware test:** after installation, select the smart plug, turn it off, restart Home Assistant with the printer off, then switch it on and ensure status/temperatures recover. Always finish printing and allow the printer to cool before cutting power with an external socket; this integration does not automatically shut down a printer safely.

## Printer protocol and limitations

Control is acquired with `~M601 S1`, read commands include `~M115`, `~M105`, `~M119`, `~M27`; the integrated LED uses `~M146 r255 g255 b255 F0` or zeros; control is released with `~M602`. A busy control connection can temporarily cause unavailable sensors. Data is read only from the printer, without cloud transmission.

`M27` can reply `SD printing byte 0/100` when idle. Print percentage is only calculated for active print states. This feature still needs verification during real print jobs. On some tested firmware, `M119` returns `LED: 1` both when the light is on and off, so the LED entity is intentionally **optimistic**.

The camera is provided at `http://PRINTER_IP:8080/?action=stream` on verified hardware. It can be disabled from the integration's options.

## Troubleshooting

- **Can't connect**: Ensure printer power, networking and port 8899 reachability. Close FlashForgeUI or another app if it currently owns the printer control session.
- **No camera**: Enable the built-in camera in the printer menu; verify its local stream in your browser; optionally disable the camera entity in integration settings.
- **Intermittent camera error after changing LED**: Starting with v0.2.1, the MJPEG connection and camera still-image retrieval retry short-lived failures locally. This is a mitigation pending a real-device retest. If an already-running MJPEG connection is cut by the firmware, the frontend may still need to reopen the view; please report sanitized HA log details if it reproduces.
- **Progress unavailable**: Expected while idle; during a print report sanitized `M119` and `M27` responses in an issue (no serial, file paths or other private data).
- **Changed IP**: Use the reconfigure option rather than removing and re-adding the printer.
- **Smart plug misreported as unknown**: Check that the selected socket's Home Assistant entity is a switch and that its state is exactly `on` or `off`. Use **Configure** to select a different socket or remove the selection.
- **Upgrading from 0.1.0**: Keep a backup. Domain and entity unique IDs remain the same, but a first Home Assistant runtime test is still required. Do not use the old `command_line` LED and the new LED switch simultaneously.

## Development

```bash
python -m unittest discover -s tests -v
python -m compileall -q custom_components/bresser_rex
```

GitHub Actions run protocol/privacy tests, HACS validation and hassfest for each commit. No real IP addresses, serials or MAC addresses belong in this repository; examples use RFC 5737 TEST-NET addresses.

## Privacy & security

- TCP 8899 is unauthenticated. **Never expose it or the camera's TCP 8080 port to the Internet.** Keep printer and Home Assistant on a trusted local network.
- No cloud services, analytics or external API keys are used by this integration.
- Local device information exists only on the user's own Home Assistant installation.
- If you open issues, sanitize logs and screenshots. See [SECURITY.md](SECURITY.md).

## License

MIT – see [LICENSE](LICENSE).
