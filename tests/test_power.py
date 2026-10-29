"""Pure power-state tests; no Home Assistant installation required."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest

COMPONENT = Path(__file__).parents[1] / "custom_components" / "bresser_rex"
if "testrex" not in sys.modules:
    package = types.ModuleType("testrex")
    package.__path__ = [str(COMPONENT)]
    sys.modules["testrex"] = package
spec = importlib.util.spec_from_file_location("testrex.power", COMPONENT / "power.py")
power = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = power
spec.loader.exec_module(power)


class PowerTests(unittest.TestCase):
    def test_only_explicit_off_means_unpowered(self):
        self.assertIs(power.power_state_from_switch("off"), False)
        self.assertIs(power.power_state_from_switch("on"), True)
        for state in ("unavailable", "unknown", None, "idle"):
            self.assertIsNone(power.power_state_from_switch(state))

    def test_off_clears_all_old_readings(self):
        values = power.empty_snapshot("OFF")
        self.assertEqual(values["machine_status"], "OFF")
        self.assertEqual(set(values) - {"machine_status"}, set(power.READING_KEYS))
        self.assertTrue(all(values[k] is None for k in power.READING_KEYS))

    def test_starting_does_not_reuse_stale_progress(self):
        values = power.empty_snapshot("STARTING")
        self.assertEqual(values["machine_status"], "STARTING")
        self.assertIsNone(values["progress"])
        self.assertIsNone(values["current_file"])


if __name__ == "__main__":
    unittest.main()
