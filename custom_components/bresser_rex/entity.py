"""Common identity of entities belonging to one BRESSER REX device."""

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import RexCoordinator


class RexEntity(CoordinatorEntity[RexCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RexCoordinator, key: str):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.serial}_{key}"
        self._attr_device_info = coordinator.device_info
