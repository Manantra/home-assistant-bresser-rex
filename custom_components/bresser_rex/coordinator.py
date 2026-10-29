"""One shared poll, with optional power-switch awareness and serialized I/O."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POWER_SWITCH, CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS, DOMAIN
from .power import empty_snapshot, power_off_block_reason, power_state_from_switch
from .protocol import RexError, get_readings, set_led

_LOGGER = logging.getLogger(__name__)


class RexCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Share printer readings and adapt them to the configured socket state."""

    def __init__(
        self, hass: HomeAssistant, host: str, serial: str, info: dict[str, str], options
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="BRESSER REX",
            update_interval=timedelta(
                seconds=options.get(CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS)
            ),
        )
        self.host = host
        self.serial = serial
        self.power_switch = options.get(CONF_POWER_SWITCH)
        self.lock = asyncio.Lock()
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="BRESSER",
            model=info.get("Machine Type") or "Adventurer III compatible",
            name=info.get("Machine Name") or "BRESSER REX",
            sw_version=info.get("Firmware"),
        )

    @property
    def power_state(self) -> bool | None:
        """Return plug on/off or unknown if unconfigured or not reporting."""
        if not self.power_switch:
            return None
        state = self.hass.states.get(self.power_switch)
        return power_state_from_switch(state.state if state else None)

    @property
    def power_is_off(self) -> bool:
        """Only an explicit off report suppresses printer communication."""
        return self.power_state is False

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll the printer, unless the selected plug explicitly reports off."""
        async with self.lock:
            if self.power_is_off:
                return empty_snapshot("OFF")
            try:
                readings = await self.hass.async_add_executor_job(get_readings, self.host)
            except RexError as err:
                # The switch might have changed while the TCP call was running.
                if self.power_is_off:
                    return empty_snapshot("OFF")
                raise UpdateFailed(str(err)) from err
            # Do not publish stale data when power changed during a poll.
            if self.power_is_off:
                return empty_snapshot("OFF")
            return readings

    async def async_set_led(self, on: bool) -> None:
        """Protect the LED command from executing while the printer is off."""
        async with self.lock:
            if self.power_is_off:
                raise RexError("The configured power switch is off")
            await self.hass.async_add_executor_job(set_led, self.host, on)

    async def async_set_power(self, on: bool) -> None:
        """Switch the selected external plug, refusing unsafe power-offs.

        Never claim that a plug is on/off until its own HA entity reports it.
        """
        if not self.power_switch or self.power_state is None:
            raise RexError("The selected smart plug is unavailable")
        if self.power_state is on:
            return

        async with self.lock:
            if self.power_state is None:
                raise RexError("The selected smart plug is unavailable")
            if self.power_state is on:
                return
            if not on:
                # Never rely on cached readings: re-read temperature and
                # status immediately before requesting mains shutdown.
                if self.power_state is not True:
                    raise RexError("Cannot verify that the smart plug is on")
                try:
                    readings = await self.hass.async_add_executor_job(
                        get_readings, self.host
                    )
                except RexError as err:
                    raise RexError(
                        "Cannot verify the printer is idle and cool; power-off blocked"
                    ) from err

                if reason := power_off_block_reason(readings):
                    raise RexError(f"Unsafe to turn off printer: {reason}")
                if self.power_state is not True:
                    raise RexError("Smart plug state changed; power-off cancelled")

            await self.hass.services.async_call(
                "switch",
                SERVICE_TURN_ON if on else SERVICE_TURN_OFF,
                {ATTR_ENTITY_ID: self.power_switch},
                blocking=True,
            )
