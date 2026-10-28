"""Protocol tests that run without installing Home Assistant."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

COMPONENT = Path(__file__).parents[1] / "custom_components" / "bresser_rex"
pkg = types.ModuleType("testrex")
pkg.__path__ = [str(COMPONENT)]
sys.modules["testrex"] = pkg
spec = importlib.util.spec_from_file_location("testrex.protocol", COMPONENT / "protocol.py")
protocol = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = protocol
spec.loader.exec_module(protocol)

LOGIN = b"CMD M601 Received.\r\nControl Success V2.1.\r\nok\r\n"
BUSY = b"CMD M601 Received.\r\nControl failed.\r\nok\r\n"
RELEASE = b"CMD M602 Received.\r\nControl Release.\r\nok\r\n"
TEMP = "CMD M105 Received.\r\nT0:23/0 B:13/0\r\nok\r\n"
STATUS = "CMD M119 Received.\r\nMachineStatus: READY\r\nLED: 1\r\nCurrentFile: \r\nok\r\n"
PROGRESS = "CMD M27 Received.\r\nSD printing byte 0/100\r\nok\r\n"
IDENTITY = "CMD M115 Received.\r\nMachine Type: FlashForge Adventurer III\r\nMachine Name: Bresser\r\nFirmware: v1.3.7\r\nSN: TEST-123\r\nok\r\n"


class FakeSocket:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def settimeout(self, timeout):
        self.timeout = timeout

    def sendall(self, data):
        self.sent.append(data)

    def recv(self, _):
        if not self.replies:
            return b""
        return self.replies.pop(0)


class ProtocolTest(unittest.TestCase):
    def test_idle_does_not_report_false_progress(self):
        result = protocol.parse_readings(TEMP, STATUS, PROGRESS)
        self.assertEqual(result["nozzle"], 23.0)
        self.assertEqual(result["nozzle_target"], 0.0)
        self.assertEqual(result["bed"], 13.0)
        self.assertEqual(result["machine_status"], "READY")
        self.assertIsNone(result["progress"])
        self.assertIsNone(result["current_file"])

    def test_printing_progress_is_calculated(self):
        status = STATUS.replace("READY", "BUILDING_FROM_SD").replace("CurrentFile: ", "CurrentFile: test.gx")
        progress = PROGRESS.replace("0/100", "350/1000")
        result = protocol.parse_readings(TEMP, status, progress)
        self.assertEqual(result["progress"], 35.0)
        self.assertEqual(result["current_file"], "test.gx")

    def test_temp_decimal_and_spaces(self):
        result = protocol.parse_readings("T0:219.5 / 220 B:65.2/70", STATUS, PROGRESS)
        self.assertEqual(result["nozzle"], 219.5)
        self.assertEqual(result["bed_target"], 70.0)

    def test_acquire_and_release(self):
        sock = FakeSocket([LOGIN, TEMP.encode(), RELEASE])
        with patch.object(protocol.socket, "create_connection", return_value=sock):
            result = protocol.transaction("192.0.2.10", ["M105"])
        self.assertEqual(result[0], TEMP)
        self.assertEqual(sock.sent, [b"~M601 S1\r\n", b"~M105\r\n", b"~M602\r\n"])

    def test_busy_does_not_issue_commands(self):
        sock = FakeSocket([BUSY])
        with patch.object(protocol.socket, "create_connection", return_value=sock):
            with self.assertRaises(protocol.RexBusy):
                protocol.transaction("192.0.2.10", ["M105"])
        self.assertEqual(sock.sent, [b"~M601 S1\r\n"])

    def test_identity(self):
        sock = FakeSocket([LOGIN, IDENTITY.encode(), RELEASE])
        with patch.object(protocol.socket, "create_connection", return_value=sock):
            info = protocol.get_identity("192.0.2.10")
        self.assertEqual(info["Firmware"], "v1.3.7")
        self.assertEqual(info["SN"], "TEST-123")

    def test_led_on_uses_known_command(self):
        sock = FakeSocket([LOGIN, b"CMD M146 Received.\r\nok\r\n", RELEASE])
        with patch.object(protocol.socket, "create_connection", return_value=sock):
            protocol.set_led("192.0.2.10", True)
        self.assertEqual(sock.sent[1], b"~M146 r255 g255 b255 F0\r\n")


if __name__ == "__main__":
    unittest.main()
