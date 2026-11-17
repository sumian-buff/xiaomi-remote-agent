from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from standalone.about_info import LICENSE_NOTICE, PROJECT_LINKS, UPSTREAM_NOTICE
from standalone.about_window import AboutWindow, about_window_size


class AboutWindowTests(unittest.TestCase):
    def make_about(self) -> AboutWindow:
        return AboutWindow(mock.Mock(), "Xiaomi Remote Agent", "0.1.21", mock.Mock())

    def test_project_attribution_and_gpl_notice(self) -> None:
        self.assertEqual(UPSTREAM_NOTICE, "基于 MiVibe Remote（wyuzhi/MiVibe-Remote）修改")
        self.assertIn("GPL-3.0", LICENSE_NOTICE)
        self.assertIn("版权", LICENSE_NOTICE)
        self.assertEqual(PROJECT_LINKS, (
            ("上游项目", "https://github.com/wyuzhi/MiVibe-Remote"),
            ("本项目", "https://github.com/sumian-buff/xiaomi-remote-agent"),
        ))

    def test_repeated_show_activates_existing_toplevel(self) -> None:
        about = self.make_about()
        existing = mock.Mock()
        existing.winfo_exists.return_value = 1
        about.window = existing
        with mock.patch.object(about, "_build") as build:
            about.show()
        build.assert_not_called()
        existing.deiconify.assert_called_once_with()
        existing.lift.assert_called_once_with()
        existing.focus_force.assert_called_once_with()

    def test_destroyed_window_can_be_recreated(self) -> None:
        about = self.make_about()
        about.window = mock.Mock()
        about.window.winfo_exists.side_effect = tk.TclError("destroyed")
        with mock.patch.object(about, "_build") as build:
            about.show()
        build.assert_called_once_with()
        self.assertIsNone(about.window)

    def test_close_is_safe_when_already_closed(self) -> None:
        about = self.make_about()
        existing = mock.Mock()
        about.window = existing
        about.close()
        about.close()
        existing.destroy.assert_called_once_with()
        self.assertIsNone(about.window)

    def test_preferred_size_is_constrained_to_the_screen(self) -> None:
        self.assertEqual(about_window_size(1920, 1080), (640, 360))
        for screen in ((640, 480), (300, 300), (200, 180)):
            width, height = about_window_size(*screen)
            self.assertLessEqual(width, screen[0])
            self.assertLessEqual(height, screen[1])
        with self.assertRaises(ValueError):
            about_window_size(0, 1080)

    def test_project_links_open_only_on_explicit_action(self) -> None:
        with mock.patch("standalone.about_window.webbrowser.open", return_value=True) as opened:
            about = self.make_about()
            opened.assert_not_called()
            about._open_link(PROJECT_LINKS[1][1])
        opened.assert_called_once_with(PROJECT_LINKS[1][1], new=2)

    def test_link_errors_are_logged(self) -> None:
        about = self.make_about()
        with mock.patch("standalone.about_window.webbrowser.open", side_effect=OSError("unavailable")):
            about._open_link(PROJECT_LINKS[0][1])
        self.assertIn("unavailable", about.logger.call_args.args[0])

    def test_about_has_no_social_assets_or_update_dependency(self) -> None:
        source = (SOURCE / "standalone" / "about_window.py").read_text(encoding="utf-8")
        for obsolete in ("ImageTk", "check_updates", "copy_wechat", "SOCIAL_PROFILES"):
            self.assertNotIn(obsolete, source)


if __name__ == "__main__":
    unittest.main()
