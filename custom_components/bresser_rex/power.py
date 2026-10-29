"""Pure helpers for optional smart-plug power monitoring.

An on switch means the socket supplies power, not that the printer has
finished booting. An unavailable switch must NEVER be interpreted as off.
"""

from __future__ import annotations

from typing import Any

READING_KEYS = ("nozzle", "nozzle_target", "bed", "bed_target", "current_file", "progress")


def power_state_from_switch(state: str | None) -> bool | None:
    """Interpret a switch state without claiming unknown means powered off."""
    if state == "on":
        return True
    if state == "off":
        return False
    return None


def empty_snapshot(machine_status: str | None) -> dict[str, Any]:
    """Drop old printer values when power goes off or the printer starts."""
    return {"machine_status": machine_status, **{key: None for key in READING_KEYS}}

# Strict, intentionally conservative cutoff. Running firmware may need fans
# to cool the hotend after a print, so never cut the mains if it is hot.
MAX_SAFE_POWER_OFF_CELSIUS = 40.0


def power_off_block_reason(readings: dict[str, Any] | None) -> str | None:
    """Explain why mains power cannot safely be cut via this integration.

    This cannot guarantee safe shutdown: another program may start printing
    after the status check. Users must still supervise the hardware.
    """
    if not readings or readings.get("machine_status") != "READY":
        return "The printer is not confirmed idle (READY)"

    for key in ("nozzle", "bed"):
        temperature = readings.get(key)
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            return f"Current {key} temperature is unknown"
        if not 0 <= temperature <= MAX_SAFE_POWER_OFF_CELSIUS:
            return f"The {key} is still too hot to cut power"

    for key in ("nozzle_target", "bed_target"):
        target = readings.get(key)
        if isinstance(target, bool) or not isinstance(target, (int, float)):
            return f"The {key} setting is unknown"
        if target != 0:
            return f"The {key} heater is still enabled"

    return None
