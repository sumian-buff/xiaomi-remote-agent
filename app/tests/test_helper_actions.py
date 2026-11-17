from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from bridges.xiaomi import app_catalog, helper_actions
from bridges.xiaomi import atvv_live_bridge as xiaomi_core
from bridges.xiaomi.xiaomi_config import agent_button_bindings


class HelperArgumentTests(unittest.TestCase):
    def test_supported_actions_preserve_argument_boundaries(self) -> None:
        for args in (
            ["ok"], ["arrow", "up"], ["arrow", "down"],
            ["session", "prev"], ["session", "next"],
            ["scroll", "240"], ["scroll", "-240"],
        ):
            with self.subTest(args=args):
                self.assertEqual(helper_actions.parse_helper_args({"args": args}), args)
        self.assertEqual(
            helper_actions.parse_helper_args({"args": ["scroll", "+0240"]}),
            ["scroll", "240"],
        )

    def test_rejects_empty_wrong_type_and_unsupported_arguments(self) -> None:
        for args in (
            None, "ok", (), [], [""], [None], [1], ["ok\0"],
            ["ok", "extra"], ["arrow", "left"], ["session", "delete"],
            ["scroll"], ["scroll", "0"], ["scroll", "32768"],
            ["scroll", "-32768"], ["scroll", "240", "extra"],
            ["scroll", "240 & calc.exe"], ["activate"],
            ["activate", "claude", "extra"], ["cmd.exe", "/c", "calc.exe"],
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                helper_actions.parse_helper_args({"args": args})

    def test_activation_resolves_alias_to_installed_app_id(self) -> None:
        with mock.patch.object(
            helper_actions, "resolve_app_id", return_value="Claude_newfamily!Claude"
        ) as resolve:
            result = helper_actions.parse_helper_args({"args": ["activate", "claude"]})
        resolve.assert_called_once_with("claude")
        self.assertEqual(result, ["activate", "Claude_newfamily!Claude"])

    def test_saved_example_app_ids_use_current_catalog(self) -> None:
        catalog = {
            "claude": "Claude_current!Claude",
            "codex": "OpenAI.Codex_current!App",
        }
        with (
            mock.patch.dict(app_catalog.os.environ, {app_catalog.CATALOG_ENV: json.dumps(catalog)}),
            mock.patch.object(app_catalog, "refresh_app_ids") as refresh,
        ):
            for old_id, expected in (
                ("Claude_oldfamily!Claude", catalog["claude"]),
                ("OpenAI.Codex_oldfamily!App", catalog["codex"]),
            ):
                self.assertEqual(
                    helper_actions.parse_helper_args({"args": ["activate", old_id]}),
                    ["activate", expected],
                )
        refresh.assert_not_called()

    def test_shortcut_and_shell_commands_are_never_activation_targets(self) -> None:
        with mock.patch.object(app_catalog, "refresh_app_ids") as refresh:
            for target in ("Claude.lnk", "C:\\Start Menu\\ChatGPT.lnk", "cmd.exe", "claude & calc"):
                with self.subTest(target=target), self.assertRaises(ValueError):
                    helper_actions.parse_helper_args({"args": ["activate", target]})
        refresh.assert_not_called()

    def test_command_always_uses_bundled_helper_beside_frozen_executable(self) -> None:
        executable = SOURCE.parent / "dist" / "folder with spaces" / "XiaomiRemoteAgent.exe"
        with (
            mock.patch.object(app_catalog.sys, "frozen", True, create=True),
            mock.patch.object(app_catalog.sys, "executable", str(executable)),
        ):
            command = helper_actions.helper_command({
                "type": "helper", "args": ["ok"],
                "executable": "cmd.exe", "command": "calc.exe", "shell": True,
            })
        self.assertEqual(command, [str(executable.parent / "remote-helper.exe"), "ok"])

    def test_source_mode_helper_path_is_inside_app_helper(self) -> None:
        with mock.patch.object(app_catalog.sys, "frozen", False, create=True):
            self.assertEqual(
                app_catalog.helper_path(), SOURCE.parent / "helper" / "remote-helper.exe"
            )


class HelperDispatchTests(unittest.TestCase):
    def make_hook(self):
        hook = xiaomi_core.XiaomiSpecialKeyHook.__new__(xiaomi_core.XiaomiSpecialKeyHook)
        hook.button_bindings = agent_button_bindings()
        hook.key_send_lock = threading.Lock()
        hook._load_bridge_core = mock.Mock(
            side_effect=AssertionError("helper actions must not load the keyboard mapper")
        )
        return hook

    def test_helper_dispatch_has_hidden_windows_flags_and_no_shell(self) -> None:
        hook = self.make_hook()
        executable = SOURCE.parent / "helper" / "remote-helper.exe"
        with (
            mock.patch.object(helper_actions, "helper_path", return_value=executable),
            mock.patch.object(xiaomi_core.subprocess, "Popen") as launch,
            mock.patch("builtins.print"),
        ):
            self.assertTrue(hook._perform_button_action("ok"))
        self.assertEqual(launch.call_args.args[0], [str(executable), "ok"])
        options = launch.call_args.kwargs
        self.assertEqual(options["creationflags"], subprocess.CREATE_NO_WINDOW)
        self.assertFalse(options.get("shell", False))
        self.assertTrue(options["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(options["startupinfo"].wShowWindow, subprocess.SW_HIDE)
        hook._load_bridge_core.assert_not_called()

    def test_invalid_helper_action_does_not_launch_a_process(self) -> None:
        hook = self.make_hook()
        hook.button_bindings["ok"] = [{"type": "helper", "args": ["cmd.exe"]}]
        with (
            mock.patch.object(xiaomi_core.subprocess, "Popen") as launch,
            mock.patch("builtins.print"),
        ):
            self.assertFalse(hook._perform_button_action("ok"))
        launch.assert_not_called()
        hook._load_bridge_core.assert_not_called()

    def test_volume_hold_repeats_helper_scroll_through_existing_worker(self) -> None:
        for name, usage, delta in (("volume_up", 0x80, "240"), ("volume_down", 0x81, "-240")):
            with self.subTest(name=name):
                hook = self.make_hook()
                hook.direct_state_lock = threading.Lock()
                hook.direct_active_usages = {usage}
                hook.volume_repeat_generation = 0
                hook.volume_repeat_delay = 0.40
                hook.volume_repeat_interval = 0.12
                hook.action_gate = mock.Mock()
                hook.action_gate.is_ready.return_value = True
                hook.stop_event = mock.Mock()
                hook.stop_event.is_set.return_value = False
                hook.stop_event.wait.side_effect = [False, False, True]
                with (
                    mock.patch.object(xiaomi_core.threading, "Thread") as thread,
                    mock.patch.object(xiaomi_core.subprocess, "Popen") as launch,
                    mock.patch("builtins.print"),
                ):
                    hook._start_volume_repeat(usage, name)
                    # Run the captured callback synchronously; no thread or child is started.
                    thread.call_args.kwargs["target"]()
                self.assertEqual(launch.call_count, 2)
                for call in launch.call_args_list:
                    self.assertEqual(call.args[0][-2:], ["scroll", delta])
                self.assertEqual(
                    hook.stop_event.wait.call_args_list,
                    [mock.call(0.40), mock.call(0.12), mock.call(0.12)],
                )

    def test_volume_release_cancels_pending_repeats(self) -> None:
        hook = self.make_hook()
        hook.direct_state_lock = threading.Lock()
        hook.direct_active_usages = {0x80}
        hook.volume_repeat_generation = 0
        hook.volume_repeat_delay = 0.40
        hook.volume_repeat_interval = 0.12
        hook.stop_event = mock.Mock()
        hook.stop_event.is_set.return_value = False
        hook.stop_event.wait.return_value = False
        hook.action_gate = mock.Mock()
        hook.action_gate.is_ready.return_value = True
        with (
            mock.patch.object(xiaomi_core.threading, "Thread") as thread,
            mock.patch.object(xiaomi_core.subprocess, "Popen") as launch,
            mock.patch("builtins.print"),
        ):
            hook._start_volume_repeat(0x80, "volume_up")
            hook._cancel_volume_repeat()
            thread.call_args.kwargs["target"]()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
