from __future__ import annotations

import ast
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock
import uuid


APP = Path(__file__).resolve().parents[1]
SOURCE = APP / "source"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from bridges import audio_client
from bridges.audio import audio_router
from bridges.xiaomi import atvv_live_bridge, hid_tap_runtime, xiaomi_config, xiaomi_settings
from process_utils import CREATE_NO_WINDOW, hidden_startupinfo
from standalone import xiaomi_main


class HiddenProcessTests(unittest.TestCase):
    def test_every_subprocess_launch_explicitly_hides_its_window(self) -> None:
        launch_methods = {"run", "Popen", "check_output", "call", "check_call"}
        launches = []
        for path in SOURCE.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            module_aliases = {"subprocess"}
            function_aliases = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    module_aliases.update(
                        item.asname or item.name for item in node.names if item.name == "subprocess"
                    )
                elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
                    function_aliases.update(
                        item.asname or item.name for item in node.names if item.name in launch_methods
                    )
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                direct = isinstance(node.func, ast.Name) and node.func.id in function_aliases
                qualified = (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in module_aliases
                    and node.func.attr in launch_methods
                )
                if not (direct or qualified):
                    continue
                location = f"{path.relative_to(SOURCE)}:{node.lineno}"
                launches.append(location)
                keywords = {item.arg: item.value for item in node.keywords}
                with self.subTest(launch=location):
                    self.assertIn("creationflags", keywords)
                    self.assertIn("startupinfo", keywords)
                    self.assertEqual(ast.unparse(keywords["creationflags"]), "CREATE_NO_WINDOW")
                    self.assertEqual(ast.unparse(keywords["startupinfo"]), "hidden_startupinfo()")
        self.assertGreaterEqual(len(launches), 7, "The scan must include actual launch sites")

    def test_windows_startupinfo_sets_both_required_hidden_flags(self) -> None:
        info = hidden_startupinfo()
        self.assertEqual(CREATE_NO_WINDOW, subprocess.CREATE_NO_WINDOW)
        self.assertTrue(info.dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(info.wShowWindow, subprocess.SW_HIDE)

    def test_elevated_injector_uses_sw_hide(self) -> None:
        path = SOURCE / "bridges" / "xiaomi" / "hid_tap_injector.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        launches = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "ShellExecuteW"
        ]
        self.assertEqual(len(launches), 1)
        self.assertEqual(ast.literal_eval(launches[0].args[1]), "runas")
        self.assertEqual(ast.unparse(launches[0].args[-1]), "SW_HIDE")


class AgentIsolationTests(unittest.TestCase):
    def test_all_runtime_ports_use_agent_range(self) -> None:
        self.assertEqual(audio_client.PCM_PORT, 32680)
        self.assertEqual(audio_router.DEFAULT_PCM_PORT, 32680)
        self.assertEqual(audio_client.CONTROL_PORT, 32681)
        self.assertEqual(audio_router.DEFAULT_CONTROL_PORT, 32681)
        self.assertEqual(hid_tap_runtime.HID_TAP_PORT, 32684)
        self.assertEqual(xiaomi_main.CONTROL_PORT, 32690)
        self.assertEqual(atvv_live_bridge.XIAOMI_CONTROL_PORT, 32690)
        self.assertEqual(xiaomi_settings.DEFAULT_HUB_PORT, 32690)
        self.assertIn("let port = 32684;", hid_tap_runtime.GADGET_SCRIPT)

    def test_config_logs_mutex_and_gadget_runtime_are_isolated(self) -> None:
        self.assertEqual(xiaomi_main.APP_NAME, "Xiaomi Remote Agent")
        self.assertEqual(xiaomi_main.APP_ID, "XiaomiRemoteAgent")
        self.assertEqual(xiaomi_config.APPDATA.name, "XiaomiRemoteAgent")
        self.assertEqual(xiaomi_config.CONFIG_PATH.parent, xiaomi_config.APPDATA)
        self.assertEqual(xiaomi_config.KEYS_CONFIG_PATH.parent, xiaomi_config.APPDATA)
        self.assertEqual(xiaomi_main.LOG_DIR, xiaomi_config.APPDATA / "logs")
        self.assertIn("XiaomiRemoteAgent", hid_tap_runtime.secure_runtime_directory().parts)
        self.assertTrue(hid_tap_runtime.GADGET_DLL_NAME.startswith("XiaomiRemoteAgent"))
        host = (SOURCE / "standalone" / "xiaomi_main.py").read_text(encoding="utf-8")
        self.assertIn("Global\\\\XiaomiRemoteAgentApp", host)

    def test_source_has_no_legacy_environment_or_runtime_identifiers(self) -> None:
        for path in SOURCE.rglob("*.py"):
            text = path.read_text(encoding="utf-8-sig")
            with self.subTest(path=path.relative_to(SOURCE)):
                self.assertNotRegex(text, r"\b(?:REMOTE_BRIDGE_|MIVIBE_)")
                self.assertNotRegex(text, r"\b(?:316[89]\d|3068[014]|28690)\b")
                self.assertNotIn('"MiVibeRemote"', text)
                self.assertNotIn("RemoteBridgeHidTap", text)
                self.assertNotIn("MiVibeRemote.ico", text)

    def test_mivibe_detection_reads_process_names_without_touching_processes(self) -> None:
        process = mock.Mock()
        process.info = {"name": "MIVIBEREMOTE.EXE"}
        with mock.patch.object(xiaomi_main.psutil, "process_iter", return_value=[process]) as listing:
            self.assertTrue(xiaomi_main.mivibe_is_running())
        listing.assert_called_once_with(["name"])
        process.assert_not_called()
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        with mock.patch.object(
            xiaomi_main.psutil, "process_iter",
            return_value=[SimpleNamespace(info={"name": "other.exe"}), SimpleNamespace(info={"name": None})],
        ):
            self.assertFalse(xiaomi_main.mivibe_is_running())

    def test_mivibe_conflict_exits_before_config_gui_or_workers(self) -> None:
        with (
            mock.patch.object(xiaomi_main, "mivibe_is_running", return_value=True),
            mock.patch.object(xiaomi_main.ctypes.windll.user32, "MessageBoxW") as dialog,
            mock.patch.object(xiaomi_main, "acquire_single_instance") as mutex,
            mock.patch.object(xiaomi_main, "refresh_app_ids") as apps,
            mock.patch.object(xiaomi_main, "load_config") as config,
            mock.patch.object(xiaomi_main.tk, "Tk") as gui,
            mock.patch.object(xiaomi_main, "XiaomiApp") as application,
            mock.patch.object(xiaomi_main.subprocess, "Popen") as launch,
        ):
            self.assertEqual(xiaomi_main.main([]), 1)
        dialog.assert_called_once_with(
            None, "请先退出 MiVibe Remote，两者不能同时连接遥控器", "Xiaomi Remote Agent", 0x30
        )
        for untouched in (mutex, apps, config, gui, application, launch):
            untouched.assert_not_called()

    def test_installer_has_its_own_guid_and_product_identity(self) -> None:
        setup = APP / "delivery" / "standalone" / "setup"
        files = list(setup.glob("XiaomiRemote*Setup.iss"))
        self.assertEqual(len(files), 1)
        text = files[0].read_text(encoding="utf-8-sig")
        identity = re.search(r'SetupAppId\s+"\{\{([0-9A-Fa-f-]{36})\}', text)
        self.assertIsNotNone(identity)
        self.assertNotEqual(
            uuid.UUID(identity.group(1)), uuid.UUID("C87B7439-E849-47B9-A3AC-B35AC7986CE4")
        )
        self.assertIn('ProductId "XiaomiRemoteAgent"', text)
        self.assertIn('AppExeName "XiaomiRemoteAgent.exe"', text)

    def test_spec_is_renamed_and_build_stays_offline(self) -> None:
        self.assertTrue((SOURCE / "XiaomiRemoteAgent.spec").is_file())
        self.assertFalse((SOURCE / "XiaomiRemoteBridge.spec").exists())
        text = (APP / "delivery" / "build-standalone-packages.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("XiaomiRemoteAgent.spec", text)
        self.assertIn(r".venv\Scripts\python.exe", text)
        self.assertIn("PYINSTALLER_CONFIG_DIR", text)
        for forbidden in ("fetch-third-party", "Invoke-WebRequest", "Invoke-RestMethod", "pip install", "curl.exe"):
            self.assertNotIn(forbidden.casefold(), text.casefold())
        self.assertRegex(text, r"(?is)(?:ISCC|Inno).*(?:skip|跳过)")


if __name__ == "__main__":
    unittest.main()
