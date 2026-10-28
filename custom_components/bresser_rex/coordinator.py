"""One shared poll and a lock protecting local printer control sessions."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS, DOMAIN
from .protocol import RexError, get_readings, set_led

_LOGGER = logging.getLogger(__name__)


class RexCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Share snapshots between all sensors; serialize writes and reads."""

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
        self.lock = asyncio.Lock()
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="BRESSER",
            model=info.get("Machine Type") or "Adventurer III compatible",
            name=info.get("Machine Name") or "BRESSER REX",
            sw_version=info.get("Firmware"),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update every sensor with a single network transaction."""
        async with self.lock:
            try:
                return await self.hass.async_add_executor_job(get_readings, self.host)
            except RexError as err:
                raise UpdateFailed(str(err)) from err

    async def async_set_led(self, on: bool) -> None:
        """Switch the built-in light using a known supported command."""
        async with self.lock:
            await self.hass.async_add_executor_job(set_led, self.host, on)
