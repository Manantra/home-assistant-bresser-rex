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
