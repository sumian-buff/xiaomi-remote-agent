from pathlib import Path
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
from bridges.xiaomi import app_catalog


class AppCatalogTests(unittest.TestCase):
    def test_matches_current_package_families_and_codex_chatgpt_name(self):
        entries = [
            {"name": "Claude", "app_id": "Claude_newpublisher!Claude"},
            {"name": "ChatGPT", "app_id": "OpenAI.Codex_newpublisher!App"},
            {"name": "Claude", "app_id": "C:\\stale\\Claude.lnk"},
            {"name": "Other", "app_id": "Claude_wrong!Claude"},
        ]
        self.assertEqual(app_catalog.select_app_ids(entries), {
            "claude": "Claude_newpublisher!Claude",
            "codex": "OpenAI.Codex_newpublisher!App",
        })

    def test_saved_aumid_is_resolved_again_without_launching_anything(self):
        with mock.patch.dict(os.environ, {
            app_catalog.CATALOG_ENV: '{"codex": "OpenAI.Codex_current!App"}'
        }):
            self.assertEqual(app_catalog.resolve_app_id("OpenAI.Codex_old!App"),
                             "OpenAI.Codex_current!App")

    def test_missing_app_has_no_shortcut_fallback(self):
        with mock.patch.dict(os.environ, {app_catalog.CATALOG_ENV: "{}"}), \
                mock.patch.object(app_catalog, "refresh_app_ids", return_value={}):
            with self.assertRaises(ValueError):
                app_catalog.resolve_app_id("claude")


if __name__ == "__main__":
    unittest.main()
