"""Optimistic LED control; this firmware does not report LED state reliably."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import RexEntity
from .protocol import RexError


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([RexLedSwitch(entry.runtime_data)])


class RexLedSwitch(RexEntity, SwitchEntity):
    """Toggle the internal light with M146."""

    _attr_translation_key = "led"
    _attr_icon = "mdi:lightbulb"
    _attr_assumed_state = True

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "led")
        self._attr_is_on = None  # Unknown after HA restart or external adjustment.

    async def async_turn_on(self, **kwargs):
        await self._set_led(True)

    async def async_turn_off(self, **kwargs):
        await self._set_led(False)

    async def _set_led(self, on: bool) -> None:
        try:
            await self.coordinator.async_set_led(on)
        except RexError as err:
            raise HomeAssistantError("Unable to control printer LED") from err
        self._attr_is_on = on
        self.async_write_ha_state()
