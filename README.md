# BRESSER REX for Home Assistant (unofficial)

[![Protocol tests](https://github.com/Manantra/home-assistant-bresser-rex/actions/workflows/tests.yml/badge.svg)](https://github.com/Manantra/home-assistant-bresser-rex/actions/workflows/tests.yml)
[![HACS validation](https://github.com/Manantra/home-assistant-bresser-rex/actions/workflows/hacs.yml/badge.svg)](https://github.com/Manantra/home-assistant-bresser-rex/actions/workflows/hacs.yml)

**Experimental community integration** for BRESSER REX / supported FlashForge Adventurer III–compatible printers using the **local** network protocol. No firmware changes, cloud account, or OctoPrint installation required.

> Unofficial independent community project. Not affiliated with or endorsed by BRESSER, FlashForge or Home Assistant. This release has unit-tested protocol logic but **has not yet been confirmed working end-to-end on a production Home Assistant instance**.

## Supported devices

| Device | Status |
| --- | --- |
| BRESSER REX (Adventurer III-compatible) | Protocol responses verified on firmware v1.3.7; Home Assistant runtime beta |
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

In HACS, add `https://github.com/Manantra/home-assistant-bresser-rex` as a **custom repository** of type **Integration**. Install it, restart Home Assistant and use the standard add-integration wizard above. The GitHub repository must exist and pass HACS validation before this method can be used.

## Configuration & device identity

- Hostname/IP is **never hardcoded** in this project. Home Assistant stores it locally in its config entry.
- To change a printer's address: **Settings → Devices & services → BRESSER REX → Reconfigure**. The wizard checks that the replacement address returns the **same serial number**.
- To change polling or camera: select **Configure** on the integration entry.
- The printer serial is used only as a stable identifier within the user's **local Home Assistant configuration**. It is not logged by this integration or sent anywhere else. Never post it in a public issue.
- For multiple printers, each must have its own serial number and IP/hostname.

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
- **Upgrading from 0.1.0**: Keep a backup. Domain and entity unique IDs remain the same, but a first Home Assistant runtime test is still required. Do not use the old `command_line` LED and the new LED switch simultaneously.

## Development

```bash
python -m unittest discover -s tests -v
python -m compileall -q custom_components/bresser_rex
```

GitHub Actions include protocol tests, HACS validation and hassfest. These are **configured** but have not run until the code is published on GitHub. No real IP addresses, serials or MAC addresses belong in this repository; examples use RFC 5737 TEST-NET addresses.

## Privacy & security

- TCP 8899 is unauthenticated. **Never expose it or the camera's TCP 8080 port to the Internet.** Keep printer and Home Assistant on a trusted local network.
- No cloud services, analytics or external API keys are used by this integration.
- Local device information exists only on the user's own Home Assistant installation.
- If you open issues, sanitize logs and screenshots. See [SECURITY.md](SECURITY.md).

## License

MIT – see [LICENSE](LICENSE).
