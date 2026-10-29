"""Optimistic LED control that is disabled when the smart socket is off."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import RexEntity
from .protocol import RexError


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities = [RexLedSwitch(coordinator)]
    if coordinator.power_switch:
        entities.append(RexPowerSwitch(coordinator))
    async_add_entities(entities)


class RexLedSwitch(RexEntity, SwitchEntity):
    """Toggle the built-in illumination using M146."""

    _attr_translation_key = "led"
    _attr_icon = "mdi:lightbulb"
    _attr_assumed_state = True

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "led")
        self._attr_is_on = None

    @property
    def available(self) -> bool:
        return super().available and not self.coordinator.power_is_off

    @callback
    def _handle_coordinator_update(self) -> None:
        """An unpowered printer cannot have a reliable LED state."""
        if self.coordinator.power_is_off:
            self._attr_is_on = None
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_led(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_led(False)

    async def _set_led(self, on: bool) -> None:
        try:
            await self.coordinator.async_set_led(on)
        except RexError as err:
            raise HomeAssistantError("Unable to control printer LED") from err
        self._attr_is_on = on
        self.async_write_ha_state()


class RexPowerSwitch(RexEntity, SwitchEntity):
    """Proxy the chosen smart plug within the printer device.

    State is read directly from the original plug entity. This is not a
    virtual or optimistic copy, and the plug itself is not moved.
    """

    _attr_translation_key = "power_control"
    _attr_icon = "mdi:power-plug"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power_control")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.power_state

    @property
    def available(self) -> bool:
        # This must remain usable even when printer polling is unavailable.
        return self.coordinator.power_state is not None

    async def async_turn_on(self, **kwargs) -> None:
        try:
            await self.coordinator.async_set_power(True)
        except RexError as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_off(self, **kwargs) -> None:
        try:
            await self.coordinator.async_set_power(False)
        except RexError as err:
            raise HomeAssistantError(str(err)) from err
