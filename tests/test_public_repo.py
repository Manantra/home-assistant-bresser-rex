"""Basic no-leak / repository-structure checks for a public beta."""

from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    p for p in ROOT.rglob("*")
    if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
    and p.suffix in (".py", ".md", ".json", ".yaml", ".yml")
]


class PublicRepoTests(unittest.TestCase):
    def test_no_private_ip_or_mac_literals(self):
        for path in FILES:
            if path.name == "test_public_repo.py":
                continue
            content = path.read_text()
            with self.subTest(path=str(path.relative_to(ROOT))):
                # Check for RFC1918 examples from a personal network, not for
                # the reserved documentation network (192.0.2.0/24).
                self.assertNotRegex(content, r"192\.168\.\d{1,3}\.\d{1,3}")
                self.assertNotRegex(content, r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}")
                self.assertNotRegex(content, r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}")
                self.assertNotRegex(content, r"SNFFAD\d+")

    def test_translations_match_keys(self):
        base = ROOT / "custom_components" / "bresser_rex"
        strings = json.loads((base / "strings.json").read_text())
        for locale in ("de", "en"):
            translations = json.loads((base / "translations" / f"{locale}.json").read_text())
            self.assertEqual(set(strings), set(translations))
            self.assertEqual(
                set(strings["entity"]["sensor"]),
                set(translations["entity"]["sensor"]),
            )
            self.assertEqual(
                set(strings["entity"]["binary_sensor"]),
                set(translations["entity"]["binary_sensor"]),
            )

    def test_manifest_and_hacs_metadata(self):
        manifest = json.loads((ROOT / "custom_components" / "bresser_rex" / "manifest.json").read_text())
        self.assertEqual(manifest["domain"], "bresser_rex")
        self.assertTrue(manifest["config_flow"])
        self.assertEqual(manifest["iot_class"], "local_polling")
        self.assertTrue((ROOT / "hacs.json").exists())


if __name__ == "__main__":
    unittest.main()
