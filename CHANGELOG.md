# Changelog

## v0.4.2 – Faster reconnect after smart-plug power-on (beta)

- Reduce the initial post-power-on settling period from 20 to 5 seconds.
- Poll every 5 seconds while the printer is starting, regardless of the normal user-configured refresh interval.
- Immediately restore the configured refresh interval when the printer responds, is switched off, or the three-minute recovery window expires.
- Keep the safety interlock for mains power-off unchanged; no forced power-off or rapid polling while the printer is already running.
- Add regression tests for first probe timing, fast retries, interval restoration and startup expiration.


## v0.4.1 – Smart-plug startup reconnect fix (beta; hardware retest pending)

- Do not clear printer readings when only the smart plug's attributes change (e.g. current wattage).
- Gracefully handle a 20-second boot period and transient TCP failures for up to 3 minutes after actual power-on, with periodic retries.
- Allow integration to load after HA restarts during printer boot; re-verify saved serial before trusting readings.
- Preserve the safety interlock: power-off stays blocked until a fresh READY, cool printer reading is available.
- Regression tests for state changes, startup recovery and safe power-off.


## v0.4.0 – Control selected smart plug from the printer device (beta, hardware retest pending)

- The selected plug now appears as a **Printer power** switch alongside the existing read-only power supply binary sensor.
- Switching on directly calls the original plug's Home Assistant switch service.
- Switching off is **guarded**: only READY, zero heater targets, nozzle and bed at or below 40 °C based on a fresh printer reading. Missing, hot or active readings deny shutdown.
- The original smart plug remains independently usable; this integration cannot prevent manual cutoff outside its own new power switch.
- No plug configuration means no added power switch.


## v0.3.0 – Smart-plug power monitoring (beta, awaiting hardware validation)

- Optional smart socket selector under integration options (any external `switch` entity).
- New power supply binary sensor on the same printer device.
- When the socket reports off: stop TCP polling, clear old numeric/print data, show printer status `OFF`, and mark LED/camera unavailable.
- Resume polling immediately on power-on. An unknown/unavailable socket never masquerades as off.
- Allow Home Assistant to start the integration while the selected socket reports off; no initial connection to the unpowered printer is required.
- Power is **read-only**: the integration never controls the socket and never cuts power during a print.

## v0.2.1 – MJPEG camera reconnect mitigation

- Retry temporary camera connection failures after LED changes (requires hardware retest).

## v0.2.0 – Public beta

- HACS-installable setup flow, local sensors, LED, camera, German/English translations.
- Core device functions validated on a BRESSER REX with firmware v1.3.7.
