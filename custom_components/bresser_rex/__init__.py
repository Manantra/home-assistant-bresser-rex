"""Unofficial local Home Assistant integration for BRESSER REX printers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform, STATE_OFF
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_POWER_SWITCH
from .coordinator import RexCoordinator
from .power import empty_snapshot
from .protocol import RexError, get_identity

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.CAMERA, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up even if the explicitly selected power socket is switched off."""
    host = entry.data[CONF_HOST]
    power_switch = entry.options.get(CONF_POWER_SWITCH)
    is_off = bool(power_switch and hass.states.is_state(power_switch, STATE_OFF))

    if is_off:
        # The serial was verified during the initial config flow. Do not try
        # connecting to an intentionally unpowered printer on HA restart.
        info = {"Machine Name": entry.title or "BRESSER REX"}
    else:
        try:
            info = await hass.async_add_executor_job(get_identity, host)
        except RexError as err:
            raise ConfigEntryNotReady(str(err)) from err
        if info["SN"] != entry.unique_id:
            raise ConfigEntryError(
                "Printer identity changed. Reconfigure the device address."
            )

    coordinator = RexCoordinator(
        hass, host, entry.unique_id, info, entry.options
    )

    if power_switch:
        @callback
        def power_changed(event) -> None:
            """Update immediately when the smart plug changes state."""
            if coordinator.power_is_off:
                coordinator.async_set_updated_data(empty_snapshot("OFF"))
            else:
                # Notify even if the socket becomes unavailable: never retain
                # an old definite on/off status while the source is unknown.
                new_status = "STARTING" if coordinator.power_state is True else None
                coordinator.async_set_updated_data(empty_snapshot(new_status))
                hass.async_create_task(coordinator.async_request_refresh())

        entry.async_on_unload(
            async_track_state_change_event(hass, [power_switch], power_changed)
        )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload entities and remove subscriptions."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply the changed power switch or other options by reloading."""
    await hass.config_entries.async_reload(entry.entry_id)
