"""Unofficial local Home Assistant integration for BRESSER REX printers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .coordinator import RexCoordinator
from .protocol import RexError, get_identity

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.CAMERA]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Verify the printer identity and start the platforms."""
    host = entry.data[CONF_HOST]
    try:
        info = await hass.async_add_executor_job(get_identity, host)
    except RexError as err:
        raise ConfigEntryNotReady(str(err)) from err

    if info["SN"] != entry.unique_id:
        raise ConfigEntryError("Printer identity changed. Reconfigure the device address.")

    coordinator = RexCoordinator(hass, host, info["SN"], info, entry.options)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload all entities and release listeners."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload entities after settings change."""
    await hass.config_entries.async_reload(entry.entry_id)
