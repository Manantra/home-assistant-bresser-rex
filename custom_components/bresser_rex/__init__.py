"""Unofficial local Home Assistant integration for BRESSER REX printers."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform, STATE_OFF
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.event import async_track_state_change_event

from .const import CONF_POWER_SWITCH
from .coordinator import RexCoordinator
from .power import empty_snapshot, power_state_changed
from .protocol import RexError, get_identity

PLATFORMS = [Platform.SENSOR, Platform.SWITCH, Platform.CAMERA, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up even if the explicitly selected power socket is switched off."""
    host = entry.data[CONF_HOST]
    power_switch = entry.options.get(CONF_POWER_SWITCH)
    is_off = bool(power_switch and hass.states.is_state(power_switch, STATE_OFF))

    identity_verified = False
    if is_off:
        # During an HA restart, the powered-off printer is intentionally
        # unreachable. Verify its serial later when the socket is on.
        info = {"Machine Name": entry.title or "BRESSER REX"}
    else:
        try:
            info = await hass.async_add_executor_job(get_identity, host)
        except RexError as err:
            if not power_switch:
                raise ConfigEntryNotReady(str(err)) from err
            # A selected plug may report ON before the printer has finished
            # booting. Keep the integration and its power switch available.
            info = {"Machine Name": entry.title or "BRESSER REX"}
        else:
            if info["SN"] != entry.unique_id:
                raise ConfigEntryError(
                    "Printer identity changed. Reconfigure the device address."
                )
            identity_verified = True

    coordinator = RexCoordinator(
        hass, host, entry.unique_id, info, entry.options,
        identity_verified=identity_verified,
    )
    if power_switch and not is_off and not identity_verified:
        coordinator.note_power_on()

    if power_switch:
        @callback
        def power_changed(event) -> None:
            """Only true state transitions should reset printer readings."""
            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")
            old_value = old_state.state if old_state is not None else None
            new_value = new_state.state if new_state is not None else None
            if not power_state_changed(old_value, new_value):
                # Smart plugs often change attributes (W, kWh, etc.) while
                # remaining on. Never reset the printer on those events.
                return

            if coordinator.power_is_off:
                coordinator.note_power_off()
                coordinator.async_set_updated_data(empty_snapshot("OFF"))
                return

            if coordinator.power_state is True:
                coordinator.note_power_on()
                coordinator.async_set_updated_data(empty_snapshot("STARTING"))
            else:
                # Unknown plug state must not masquerade as OFF.
                coordinator.async_set_updated_data(empty_snapshot(None))
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
