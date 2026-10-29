"""Expose the optional smart socket's on/off state on the printer device."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .entity import RexEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Create the power status only if a smart plug is configured."""
    coordinator = entry.runtime_data
    if coordinator.power_switch:
        async_add_entities([RexPowerBinarySensor(coordinator)])


class RexPowerBinarySensor(RexEntity, BinarySensorEntity):
    """Show supplied power; unknown plugs are unavailable, never assumed off."""

    _attr_translation_key = "power"
    _attr_device_class = BinarySensorDeviceClass.POWER

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "power")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.power_state

    @property
    def available(self) -> bool:
        # This entity reports the socket even if the printer poll failed.
        return self.coordinator.power_state is not None
