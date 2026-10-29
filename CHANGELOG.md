# Changelog

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
