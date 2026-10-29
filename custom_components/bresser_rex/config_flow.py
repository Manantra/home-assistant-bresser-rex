"""UI setup, reconfiguration and options for supported Adventurer III devices."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers import entity_registry, selector

from .const import (
    CONF_CAMERA_ENABLED,
    CONF_POWER_SWITCH,
    CONF_UPDATE_SECONDS,
    DEFAULT_UPDATE_SECONDS,
    DOMAIN,
    MAX_UPDATE_SECONDS,
    MIN_UPDATE_SECONDS,
)
from .protocol import RexBusy, RexError, get_identity

# Do not accept URLs, port numbers or paths in a hostname field.
# IPv4 and ordinary DNS/mDNS hostnames are supported in this version.
HOST_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.-]*$")


def _host_schema(default: str | None = None) -> vol.Schema:
    """Create a reusable form for the printer host."""
    key = vol.Required(CONF_HOST, default=default) if default else vol.Required(CONF_HOST)
    return vol.Schema({key: str})


class BresserRexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Add supported printers through the Home Assistant UI."""

    VERSION = 1

    async def _async_validate(self, host: str) -> tuple[dict[str, str] | None, str | None]:
        """Validate host syntax and verify model/serial locally over TCP."""
        if not HOST_PATTERN.fullmatch(host) or len(host) > 253 or ".." in host:
            return None, "invalid_host"
        try:
            info = await self.hass.async_add_executor_job(get_identity, host)
        except RexBusy:
            return None, "printer_busy"
        except RexError:
            return None, "cannot_connect"
        except OSError:
            return None, "cannot_connect"
        return info, None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Validate a supplied printer address and create one entry per serial."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            info, error = await self._async_validate(host)
            if error:
                errors["base"] = error
            else:
                assert info is not None
                await self.async_set_unique_id(info["SN"])
                self._abort_if_unique_id_configured()
                title = info.get("Machine Name") or "BRESSER REX"
                return self.async_create_entry(title=title, data={CONF_HOST: host})

        return self.async_show_form(
            step_id="user",
            data_schema=_host_schema(user_input.get(CONF_HOST) if user_input else None),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        """Allow changing the IP/DNS name without losing entities or the device."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            info, error = await self._async_validate(host)
            if error:
                errors["base"] = error
            else:
                assert info is not None
                await self.async_set_unique_id(info["SN"])
                self._abort_if_unique_id_mismatch()
                # A loaded entry has an options-update listener. Updating the
                # entry triggers that listener to reload without a second reload.
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_HOST: host}
                )
                return self.async_abort(
                    reason="reconfigure_successful", translation_domain="homeassistant"
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_host_schema(
                user_input.get(CONF_HOST) if user_input else entry.data[CONF_HOST]
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Expose polling rate and camera configuration in the UI."""
        return BresserRexOptionsFlow()


class BresserRexOptionsFlow(config_entries.OptionsFlow):
    """Configure optional smart-plug monitoring and connection settings."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Show a selector for an optional existing switch entity."""
        errors: dict[str, str] = {}
        if user_input is not None:
            power_switch = user_input.get(CONF_POWER_SWITCH)
            if power_switch:
                registered = entity_registry.async_get(self.hass).async_get(power_switch)
                if registered is not None and registered.platform == DOMAIN:
                    errors[CONF_POWER_SWITCH] = "invalid_power_switch"
            if not errors:
                return self.async_create_entry(data=user_input)

        old_switch = self.config_entry.options.get(CONF_POWER_SWITCH)
        optional_switch = (
            vol.Optional(
                CONF_POWER_SWITCH,
                description={"suggested_value": old_switch},
            )
            if old_switch
            else vol.Optional(CONF_POWER_SWITCH)
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_SECONDS,
                        default=self.config_entry.options.get(
                            CONF_UPDATE_SECONDS, DEFAULT_UPDATE_SECONDS
                        ),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_UPDATE_SECONDS, max=MAX_UPDATE_SECONDS),
                    ),
                    vol.Required(
                        CONF_CAMERA_ENABLED,
                        default=self.config_entry.options.get(CONF_CAMERA_ENABLED, True),
                    ): bool,
                    optional_switch: selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="switch")
                    ),
                }
            ),
            errors=errors,
        )
