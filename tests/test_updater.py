import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

import updater  # noqa: E402
from analyzer import merge_rules  # noqa: E402


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))
        self.assertEqual(updater.parse_version("1.10"), (1, 10))
        self.assertEqual(updater.parse_version("v2.0.0"), (2,))
        self.assertEqual(updater.parse_version("v1.3-beta"), (1, 3))
        self.assertEqual(updater.parse_version("nonsense"), (0,))

    def test_is_newer(self):
        self.assertTrue(updater.is_newer("v1.10", "1.9"))
        self.assertTrue(updater.is_newer("v1.1", "1.0"))
        self.assertFalse(updater.is_newer("v1.0", "1.0"))
        self.assertFalse(updater.is_newer("v1.0.0", "1.0"))
        self.assertFalse(updater.is_newer("v0.9", "1.0"))


class ReleaseJsonTests(unittest.TestCase):
    def test_picks_exe_asset_and_digest(self):
        data = {
            "tag_name": "v1.2", "body": "notes", "html_url": "https://github.com/x/y/releases/tag/v1.2",
            "assets": [
                {"name": "iPhonePanicAnalyzer-v1.2-windows.zip", "browser_download_url": "zip", "size": 5},
                {"name": "iPhonePanicAnalyzer.exe", "browser_download_url": "exe", "size": 42,
                 "digest": "sha256:ABCDEF"},
            ],
        }
        rel = updater.release_from_json(data)
        self.assertEqual((rel.version, rel.tag, rel.exe_url, rel.exe_size, rel.exe_sha256),
                         ("1.2", "v1.2", "exe", 42, "abcdef"))

    def test_release_without_exe_yet(self):
        rel = updater.release_from_json({"tag_name": "v1.3", "assets": []})
        self.assertIsNone(rel.exe_url)


class MergeRulesTests(unittest.TestCase):
    def test_user_edits_win_and_new_codes_arrive(self):
        bundled = {"version": 2, "sensors": {"PRS0": {"name": "new"}, "TG0B": {"name": "battery"}},
                   "rules": [{"id": "a", "title": "A2"}, {"id": "b", "title": "B"}]}
        user = {"version": 1, "sensors": {"PRS0": {"name": "mine"}, "XYZ": {"name": "custom"}},
                "rules": [{"id": "a", "title": "A-mine"}, {"id": "c", "title": "C"}]}
        m = merge_rules(bundled, user)
        self.assertEqual(m["sensors"]["PRS0"]["name"], "mine")
        self.assertIn("TG0B", m["sensors"])
        self.assertIn("XYZ", m["sensors"])
        self.assertEqual([r["id"] for r in m["rules"]], ["a", "c", "b"])
        self.assertEqual(m["rules"][0]["title"], "A-mine")


if __name__ == "__main__":
    unittest.main()
