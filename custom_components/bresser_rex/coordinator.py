"""One shared poll, with optional power-switch awareness and serialized I/O."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from time import monotonic
import logging
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, SERVICE_TURN_OFF, SERVICE_TURN_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_POWER_SWITCH, CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS, DOMAIN
from .power import empty_snapshot, power_off_block_reason, power_state_from_switch
from .protocol import get_identity
from .protocol import RexError, get_readings, set_led

_LOGGER = logging.getLogger(__name__)

# Give the printer time to boot before attempting its exclusive TCP protocol.
POWER_ON_SETTLE_SECONDS = 5
POWER_ON_RETRY_SECONDS = 5
POWER_ON_RECOVERY_SECONDS = 180


class RexCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Share printer readings and adapt them to the configured socket state."""

    def __init__(
        self, hass: HomeAssistant, host: str, serial: str, info: dict[str, str], options, *, identity_verified: bool = True
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
        self._normal_update_seconds = options.get(
            CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS
        )
        self.lock = asyncio.Lock()
        self._power_on_at: float | None = None
        self._identity_verified = identity_verified
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

    def note_power_on(self) -> None:
        """Begin a bounded warm-up after a real off-to-on transition."""
        self._power_on_at = monotonic()
        # During startup, probe every few seconds instead of waiting for
        # the normal (often 30-second) sensor polling interval.
        self.update_interval = timedelta(seconds=POWER_ON_RETRY_SECONDS)

    def note_power_off(self) -> None:
        """Reset the startup countdown when the socket is switched off."""
        self._power_on_at = None
        self.update_interval = timedelta(seconds=self._normal_update_seconds)

    @property
    def is_starting(self) -> bool:
        """Keep the printer in STARTING for a bounded recovery period."""
        return (
            self.power_state is True
            and self._power_on_at is not None
            and monotonic() - self._power_on_at < POWER_ON_RECOVERY_SECONDS
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Poll only after warm-up, retaining STARTING on short boot failures."""
        async with self.lock:
            if self.power_is_off:
                self.note_power_off()
                return empty_snapshot("OFF")

            if self.is_starting and (
                monotonic() - self._power_on_at < POWER_ON_SETTLE_SECONDS
            ):
                return empty_snapshot("STARTING")

            try:
                # After HA started while the printer was off or booting,
                # validate its serial before trusting the network endpoint.
                if not self._identity_verified:
                    identity = await self.hass.async_add_executor_job(
                        get_identity, self.host
                    )
                    if identity.get("SN") != self.serial:
                        raise UpdateFailed(
                            "Printer serial differs from the configured device"
                        )
                    self._identity_verified = True
                readings = await self.hass.async_add_executor_job(
                    get_readings, self.host
                )
            except RexError as err:
                if self.power_is_off:
                    self.note_power_off()
                    return empty_snapshot("OFF")
                if self.is_starting:
                    _LOGGER.debug(
                        "BRESSER REX still booting / reconnecting: %s", err
                    )
                    return empty_snapshot("STARTING")
                # Once the bounded recovery window ends, stop rapid probes
                # and report genuine connectivity problems normally.
                if self._power_on_at is not None:
                    self._power_on_at = None
                    self.update_interval = timedelta(
                        seconds=self._normal_update_seconds
                    )
                raise UpdateFailed(
                    f"Printer control connection unavailable: {err}"
                ) from err

            if self.power_is_off:
                self.note_power_off()
                return empty_snapshot("OFF")
            if self._power_on_at is not None:
                self._power_on_at = None
                self.update_interval = timedelta(
                    seconds=self._normal_update_seconds
                )
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
                if self.is_starting:
                    raise RexError(
                        "Printer still starting or reconnecting; power-off blocked"
                    )
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
