"""Coordinator safety tests without installing Home Assistant."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

COMPONENT = Path(__file__).parents[1] / "custom_components" / "bresser_rex"


class FakeCoordinatorBase:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.update_interval = kwargs.get("update_interval")


class FakeUpdateFailed(Exception):
    pass


class FakeStates:
    def __init__(self, state):
        self.state = state

    def get(self, entity_id):
        return types.SimpleNamespace(state=self.state)


class FakeServices:
    def __init__(self):
        self.calls = []

    async def async_call(self, domain, action, data, *, blocking):
        self.calls.append((domain, action, data, blocking))


class FakeHass:
    def __init__(self, state):
        self.states = FakeStates(state)
        self.calls = []
        self.services = FakeServices()

    async def async_add_executor_job(self, func, *args):
        self.calls.append((func, args))
        return func(*args)


def load_coordinator():
    # Import only the module under test using minimal HA stand-ins.
    names = [
        "homeassistant",
        "homeassistant.core",
        "homeassistant.const",
        "homeassistant.helpers",
        "homeassistant.helpers.device_registry",
        "homeassistant.helpers.update_coordinator",
    ]
    fake = {key: types.ModuleType(key) for key in names}
    fake["homeassistant.core"].HomeAssistant = FakeHass
    fake["homeassistant.const"].STATE_ON = "on"
    fake["homeassistant.const"].STATE_OFF = "off"
    fake["homeassistant.const"].ATTR_ENTITY_ID = "entity_id"
    fake["homeassistant.const"].SERVICE_TURN_ON = "turn_on"
    fake["homeassistant.const"].SERVICE_TURN_OFF = "turn_off"
    fake["homeassistant.helpers.device_registry"].DeviceInfo = dict
    fake["homeassistant.helpers.update_coordinator"].DataUpdateCoordinator = FakeCoordinatorBase
    fake["homeassistant.helpers.update_coordinator"].UpdateFailed = FakeUpdateFailed

    if "testrex" not in sys.modules:
        pkg = types.ModuleType("testrex")
        pkg.__path__ = [str(COMPONENT)]
        sys.modules["testrex"] = pkg

    with patch.dict(sys.modules, fake):
        spec = importlib.util.spec_from_file_location(
            "testrex.coordinator", COMPONENT / "coordinator.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module


COORDINATOR = load_coordinator()


class CoordinatorPowerTests(unittest.IsolatedAsyncioTestCase):
    def make_coordinator(self, state):
        hass = FakeHass(state)
        coordinator = COORDINATOR.RexCoordinator(
            hass,
            "192.0.2.10",
            "TEST-ID",
            {"Machine Name": "Test printer"},
            {"power_switch": "switch.example_plug"},
        )
        return hass, coordinator

    async def test_off_skips_network_and_clears_values(self):
        hass, coordinator = self.make_coordinator("off")
        with patch.object(COORDINATOR, "get_readings", side_effect=AssertionError("TCP called")):
            snapshot = await coordinator._async_update_data()
        self.assertEqual(hass.calls, [])
        self.assertEqual(snapshot["machine_status"], "OFF")
        self.assertIsNone(snapshot["nozzle"])
        self.assertIsNone(snapshot["progress"])

    async def test_on_polls_printer(self):
        hass, coordinator = self.make_coordinator("on")
        readings = {"machine_status": "READY", "nozzle": 23.0}
        with patch.object(COORDINATOR, "get_readings", return_value=readings):
            result = await coordinator._async_update_data()
        self.assertEqual(result, readings)
        self.assertEqual(len(hass.calls), 1)

    async def test_unavailable_switch_does_not_fake_off(self):
        hass, coordinator = self.make_coordinator("unavailable")
        with patch.object(COORDINATOR, "get_readings", return_value={"machine_status": "READY"}):
            result = await coordinator._async_update_data()
        self.assertEqual(result["machine_status"], "READY")
        self.assertEqual(len(hass.calls), 1)

    async def test_power_off_during_poll_discards_stale_readings(self):
        hass, coordinator = self.make_coordinator("on")

        def poll(host):
            hass.states.state = "off"
            return {"machine_status": "PRINTING", "nozzle": 210.0, "progress": 90.0}

        with patch.object(COORDINATOR, "get_readings", side_effect=poll):
            result = await coordinator._async_update_data()
        self.assertEqual(result["machine_status"], "OFF")
        self.assertIsNone(result["nozzle"])
        self.assertIsNone(result["progress"])

    async def test_led_is_blocked_if_plug_off(self):
        hass, coordinator = self.make_coordinator("off")
        with patch.object(COORDINATOR, "set_led", side_effect=AssertionError("LED TCP called")):
            with self.assertRaises(COORDINATOR.RexError):
                await coordinator.async_set_led(True)
        self.assertEqual(hass.calls, [])

    async def test_warmup_suppresses_tcp_and_keeps_starting(self):
        hass, coordinator = self.make_coordinator("on")
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        with patch.object(COORDINATOR, "monotonic", return_value=102.0):
            with patch.object(
                COORDINATOR, "get_readings", side_effect=AssertionError("premature TCP")
            ):
                data = await coordinator._async_update_data()
        self.assertEqual(data["machine_status"], "STARTING")
        self.assertEqual(hass.calls, [])
        self.assertEqual(coordinator.update_interval.total_seconds(), 5)

    async def test_first_probe_occurs_after_five_seconds(self):
        hass, coordinator = self.make_coordinator("on")
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        with patch.object(COORDINATOR, "monotonic", return_value=105.0):
            with patch.object(
                COORDINATOR, "get_readings",
                return_value={"machine_status": "READY", "nozzle": 23.0},
            ):
                data = await coordinator._async_update_data()
        self.assertEqual(data["machine_status"], "READY")
        self.assertEqual(len(hass.calls), 1)
        self.assertEqual(coordinator.update_interval.total_seconds(), 30)

    async def test_retries_are_fast_during_startup(self):
        hass, coordinator = self.make_coordinator("on")
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        with patch.object(COORDINATOR, "monotonic", return_value=106.0):
            with patch.object(
                COORDINATOR, "get_readings",
                side_effect=COORDINATOR.RexError("booting"),
            ):
                data = await coordinator._async_update_data()
        self.assertEqual(data["machine_status"], "STARTING")
        self.assertEqual(coordinator.update_interval.total_seconds(), 5)

    async def test_power_off_restores_normal_refresh_period(self):
        hass, coordinator = self.make_coordinator("off")
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        self.assertEqual(coordinator.update_interval.total_seconds(), 5)
        coordinator.note_power_off()
        self.assertEqual(coordinator.update_interval.total_seconds(), 30)
        self.assertIsNone(coordinator._power_on_at)

    async def test_transient_boot_failure_stays_starting(self):
        hass, coordinator = self.make_coordinator("on")
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        with patch.object(COORDINATOR, "monotonic", return_value=135.0):
            with patch.object(
                COORDINATOR, "get_readings",
                side_effect=COORDINATOR.RexError("not yet ready"),
            ):
                data = await coordinator._async_update_data()
        self.assertEqual(data["machine_status"], "STARTING")

    async def test_timeout_restores_real_offline_error(self):
        hass, coordinator = self.make_coordinator("on")
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        with patch.object(COORDINATOR, "monotonic", return_value=300.0):
            with patch.object(
                COORDINATOR, "get_readings",
                side_effect=COORDINATOR.RexError("not reachable"),
            ):
                with self.assertRaises(FakeUpdateFailed):
                    await coordinator._async_update_data()
        self.assertEqual(coordinator.update_interval.total_seconds(), 30)

    async def test_successful_boot_recovers_readings(self):
        hass, coordinator = self.make_coordinator("on")
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        with patch.object(COORDINATOR, "monotonic", return_value=140.0):
            with patch.object(
                COORDINATOR, "get_readings",
                return_value={"machine_status": "READY", "nozzle": 23.0},
            ):
                data = await coordinator._async_update_data()
        self.assertEqual(data["machine_status"], "READY")
        self.assertEqual(data["nozzle"], 23.0)
        self.assertFalse(coordinator.is_starting)
        self.assertEqual(coordinator.update_interval.total_seconds(), 30)

    async def test_identity_verified_after_powered_off_start(self):
        hass = FakeHass("on")
        coordinator = COORDINATOR.RexCoordinator(
            hass, "192.0.2.10", "TEST-ID",
            {"Machine Name": "Test printer"},
            {"power_switch": "switch.example_plug"}, identity_verified=False,
        )
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        with patch.object(COORDINATOR, "monotonic", return_value=130.0):
            with patch.object(
                COORDINATOR, "get_identity", return_value={"SN": "TEST-ID"}
            ), patch.object(
                COORDINATOR, "get_readings", return_value={"machine_status": "READY"}
            ):
                data = await coordinator._async_update_data()
        self.assertEqual(data["machine_status"], "READY")
        self.assertTrue(coordinator._identity_verified)
        self.assertEqual(len(hass.calls), 2)

    async def test_startup_guard_blocks_poweroff(self):
        hass, coordinator = self.make_coordinator("on")
        with patch.object(COORDINATOR, "monotonic", return_value=100.0):
            coordinator.note_power_on()
        with patch.object(COORDINATOR, "monotonic", return_value=110.0):
            with self.assertRaises(COORDINATOR.RexError):
                await coordinator.async_set_power(False)
        self.assertEqual(hass.calls, [])
        self.assertEqual(hass.services.calls, [])

    async def test_power_on_calls_selected_external_switch(self):
        hass, coordinator = self.make_coordinator("off")
        await coordinator.async_set_power(True)
        self.assertEqual(
            hass.services.calls,
            [("switch", "turn_on", {"entity_id": "switch.example_plug"}, True)],
        )
        self.assertEqual(hass.calls, [])

    async def test_unknown_switch_state_refuses_control(self):
        hass, coordinator = self.make_coordinator("unavailable")
        with self.assertRaises(COORDINATOR.RexError):
            await coordinator.async_set_power(True)
        with self.assertRaises(COORDINATOR.RexError):
            await coordinator.async_set_power(False)
        self.assertEqual(hass.services.calls, [])

    async def test_power_off_permitted_only_after_fresh_cold_ready_reading(self):
        hass, coordinator = self.make_coordinator("on")
        ready = {
            "machine_status": "READY",
            "nozzle": 25.0, "bed": 23.0,
            "nozzle_target": 0.0, "bed_target": 0.0,
        }
        with patch.object(COORDINATOR, "get_readings", return_value=ready):
            await coordinator.async_set_power(False)
        self.assertEqual(len(hass.calls), 1)
        self.assertEqual(
            hass.services.calls,
            [("switch", "turn_off", {"entity_id": "switch.example_plug"}, True)],
        )

    async def test_power_off_refused_while_printing_or_hot(self):
        for fields in (
            {"machine_status": "PRINTING"},
            {"nozzle": 160.0},
            {"bed": 55.0},
            {"nozzle_target": 200.0},
            {"machine_status": None},
            {"nozzle": None},
        ):
            with self.subTest(fields=fields):
                hass, coordinator = self.make_coordinator("on")
                reading = {
                    "machine_status": "READY",
                    "nozzle": 25.0, "bed": 23.0,
                    "nozzle_target": 0.0, "bed_target": 0.0,
                }
                reading.update(fields)
                with patch.object(COORDINATOR, "get_readings", return_value=reading):
                    with self.assertRaises(COORDINATOR.RexError):
                        await coordinator.async_set_power(False)
                self.assertEqual(hass.services.calls, [])

    async def test_no_power_off_when_printer_unreachable(self):
        hass, coordinator = self.make_coordinator("on")
        with patch.object(
            COORDINATOR, "get_readings", side_effect=COORDINATOR.RexError("offline")
        ):
            with self.assertRaises(COORDINATOR.RexError):
                await coordinator.async_set_power(False)
        self.assertEqual(hass.services.calls, [])

    async def test_idempotent_switch_action_calls_no_services(self):
        for state, action in (("on", True), ("off", False)):
            hass, coordinator = self.make_coordinator(state)
            await coordinator.async_set_power(action)
            self.assertEqual(hass.calls, [])
            self.assertEqual(hass.services.calls, [])


if __name__ == "__main__":
    unittest.main()
