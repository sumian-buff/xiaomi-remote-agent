from __future__ import annotations

from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
SETUP = ROOT / "delivery" / "standalone" / "setup"


class StandalonePackageTests(unittest.TestCase):
    def test_only_xiaomi_entry_remains(self) -> None:
        self.assertTrue((SOURCE / "standalone" / "xiaomi_main.py").is_file())
        for name in ("t1_main.py", "v60_main.py", "windows_update.py"):
            self.assertFalse((SOURCE / "standalone" / name).exists(), name)

    def test_xiaomi_owns_a_separate_config_and_runtime_root(self) -> None:
        text = (SOURCE / "standalone" / "xiaomi_main.py").read_text(encoding="utf-8")
        self.assertIn('XIAOMI_REMOTE_AGENT_XIAOMI_APP_ID", APP_ID', text)
        self.assertIn('XIAOMI_REMOTE_AGENT_XIAOMI_RUNTIME_ID", APP_ID', text)
        self.assertIn('XIAOMI_REMOTE_AGENT_XIAOMI_CONTROL_PORT", str(CONTROL_PORT)', text)
        self.assertIn('child_environment["PYTHONUTF8"] = "1"', text)
        self.assertIn('child_environment["PYTHONIOENCODING"] = "utf-8"', text)
        self.assertNotIn("from bridges.t1", text)
        self.assertNotIn("from bridges.hanvon", text)

    def test_xiaomi_host_has_no_online_update_integration(self) -> None:
        text = (SOURCE / "standalone" / "xiaomi_main.py").read_text(encoding="utf-8")
        for marker in ("WinSparkle", "windows_update", "self.check_updates", "MainThreadShutdownBridge"):
            self.assertNotIn(marker, text)

    def test_xiaomi_host_exposes_environment_check_and_in_app_guide(self) -> None:
        text = (SOURCE / "standalone" / "xiaomi_main.py").read_text(encoding="utf-8")
        self.assertIn("EnvironmentCheckWindow", text)
        self.assertIn('text="环境检查"', text)
        self.assertIn('text="使用教程"', text)
        self.assertIn("def show_guide", text)
        self.assertIn('self.root.geometry("820x540")', text)

    def test_xiaomi_settings_restart_is_confirmed_by_host(self) -> None:
        settings = (
            SOURCE / "bridges" / "xiaomi" / "xiaomi_settings.py"
        ).read_text(encoding="utf-8")
        standalone = (SOURCE / "standalone" / "xiaomi_main.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('"request_id": request_id', settings)
        self.assertIn("client.recvfrom(4096)", settings)
        self.assertIn("settings restart confirmed", standalone)

    def test_xiaomi_settings_window_is_single_instance(self) -> None:
        text = (
            SOURCE / "bridges" / "xiaomi" / "xiaomi_settings.py"
        ).read_text(encoding="utf-8")

        self.assertIn("def claim_settings_instance", text)
        self.assertIn("notify_existing_settings(port)", text)
        self.assertIn('name="xiaomi-settings-single-instance"', text)

    def test_build_names_xiaomi_remote_agent(self) -> None:
        text = (ROOT / "delivery" / "build-standalone-packages.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("XiaomiRemoteAgent", text)
        self.assertIn("XiaomiRemoteAgent.exe", text)
        self.assertNotIn("T1RemoteBridge.spec", text)
        self.assertNotIn("V60PenBridge.spec", text)
        self.assertNotIn("WinSparkle", text)

    def test_xiaomi_settings_has_redistributable_remote_fallback(self) -> None:
        text = (
            SOURCE / "bridges" / "xiaomi" / "xiaomi_settings.py"
        ).read_text(encoding="utf-8")
        self.assertIn("def _draw_remote_silhouette", text)
        self.assertIn("self._draw_remote_silhouette()", text)
        self.assertIn("Xiaomi Remote Agent 2", text)
        self.assertIn('fill="#d7d9db"', text)
        self.assertIn('text="Xiaomi Remote Agent"', text)
        self.assertNotIn('text="xiaomi"', text)

    def test_xiaomi_settings_scrolls_on_short_windows_and_draws_silver_remote(self) -> None:
        text = (
            SOURCE / "bridges" / "xiaomi" / "xiaomi_settings.py"
        ).read_text(encoding="utf-8")
        self.assertIn('orient="vertical", command=page.yview', text)
        self.assertIn('self.root.bind("<MouseWheel>"', text)
        self.assertNotIn('self.root.minsize(1235, 900)', text)
        self.assertIn('fill="#d7d9db"', text)
        self.assertIn('text="Xiaomi Remote Agent"', text)
        self.assertIn('"PresetActive.TButton"', text)

    def test_side_specific_hotkeys_have_scan_code_sender(self) -> None:
        text = (SOURCE / "bridges" / "raw_input_bridge.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("KEYEVENTF_SCANCODE = 0x0008", text)
        self.assertIn("def send_scan_code_hotkey", text)
        self.assertIn("KEYBDINPUT(0, scan, flags, 0, 0)", text)

    def test_xiaomi_settings_offer_native_mouse_wheel_actions(self) -> None:
        settings = (
            SOURCE / "bridges" / "xiaomi" / "xiaomi_settings.py"
        ).read_text(encoding="utf-8")
        bridge = (SOURCE / "bridges" / "raw_input_bridge.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('text="滚轮向上"', settings)
        self.assertIn('text="滚轮向下"', settings)
        self.assertIn("def set_selected_to_mouse_wheel", settings)
        self.assertIn("MOUSEEVENTF_WHEEL = 0x0800", bridge)
        self.assertIn("def send_mouse_wheel", bridge)

    def test_xiaomi_voice_shortcut_uses_checked_scan_code_sender(self) -> None:
        text = (
            SOURCE / "bridges" / "xiaomi" / "atvv_live_bridge.py"
        ).read_text(encoding="utf-8")
        voice_shortcut = text.split("class VoiceShortcut:", 1)[1].split(
            "class VoicePcmStats:", 1
        )[0]

        self.assertIn("send_scan_code_vk", voice_shortcut)
        self.assertNotIn("keybd_event", voice_shortcut)

    def test_xiaomi_installer_does_not_change_global_microphone_or_privacy(self) -> None:
        text = (
            SETUP / "configure-xiaomi-audio.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertNotIn("Set-DefaultCableMicrophone", text)
        self.assertNotIn("CapabilityAccessManager\\ConsentStore\\microphone", text)
        self.assertIn(
            '"System default microphone: preserved when Windows allows restoration"',
            text,
        )
        self.assertIn('"Microphone privacy settings: unchanged"', text)
        self.assertIn("$exitCode = 1", text)
        self.assertIn("exit $exitCode", text)

    def test_xiaomi_voice_driver_uses_vendor_setup_and_does_not_block_app_install(self) -> None:
        text = (SETUP / "configure-xiaomi-audio.ps1").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn('"VBCABLE_Setup_x64.exe"', text)
        self.assertIn("Invoke-OfficialInstaller", text)
        self.assertNotIn("RootDeviceInstaller", text)
        install_body = text.split('"Install" {', 1)[1].split('"Finish" {', 1)[0]
        self.assertNotIn("Invoke-OfficialInstaller", install_body)
        self.assertIn("optional third-party audio driver", install_body)
        self.assertIn("Microsoft Windows Hardware Compatibility Publisher", text)
        self.assertIn("BUREL VINCENT", text)
        self.assertIn("function Get-Sha256", text)
        self.assertNotIn("Get-FileHash", text)
        self.assertIn("[IO.Compression.ZipFile]::ExtractToDirectory", text)
        self.assertNotIn("Expand-Archive", text)
        installer_body = text.split("function Invoke-OfficialInstaller", 1)[1].split(
            "function Wait-VBCable", 1
        )[0]
        self.assertIn("Start-Process -FilePath $setup -Verb RunAs", installer_body)
        self.assertNotIn("-PassThru", installer_body)
        self.assertNotIn("-Wait", installer_body)
        self.assertNotIn("ExitCode", installer_body)
        repair_body = text.split('"Repair" {', 1)[1].split('"Restore" {', 1)[0]
        self.assertIn("Wait-VBCable 180", repair_body)

    def test_xiaomi_package_declares_runtime_winrt_projections(self) -> None:
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        spec = next(SOURCE.glob("XiaomiRemote*.spec")).read_text(encoding="utf-8")
        build = (ROOT / "delivery" / "build-standalone-packages.ps1").read_text(
            encoding="utf-8-sig"
        )
        for projection in (
            "winrt-Windows.Foundation==3.2.1",
            "winrt-Windows.Foundation.Collections==3.2.1",
        ):
            self.assertIn(projection, requirements)
        for module in (
            "winrt.windows.foundation",
            "winrt.windows.foundation.collections",
        ):
            self.assertIn(module, spec)
            self.assertIn(module, build)

    def test_only_xiaomi_spec_remains(self) -> None:
        specs = list(SOURCE.glob("*.spec"))
        self.assertEqual(len(specs), 1)
        self.assertTrue(specs[0].name.startswith("XiaomiRemote"))

    def test_pyinstaller_spec_is_valid_python(self) -> None:
        for spec in SOURCE.glob("*.spec"):
            ast.parse(spec.read_text(encoding="utf-8"), filename=str(spec))

    def test_spec_excludes_licensing_and_protection_modules(self) -> None:
        for spec in SOURCE.glob("*.spec"):
            text = spec.read_text(encoding="utf-8")
            self.assertIn('"licensing"', text)
            self.assertIn('"customer_license"', text)

    @unittest.skipUnless(SETUP.is_dir(), "standalone installer sources are not staged")
    def test_only_xiaomi_installer_handles_vb_cable_without_bundling_it(self) -> None:
        common = (SETUP / "StandaloneBridgeSetup.common.iss").read_text(encoding="utf-8")
        self.assertNotIn("VBCABLE_Driver_Pack45.zip", common)
        audio_setup = (
            SETUP / "configure-xiaomi-audio.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertIn(
            "https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack45.zip",
            audio_setup,
        )
        self.assertIn("VB-CABLE download hash mismatch", audio_setup)
        self.assertIn("Local\\XiaomiRemoteAgentAudioSetup", audio_setup)
        self.assertIn("NewGuid().ToString('N')", audio_setup)
        self.assertIn("等待文件解除占用超时", audio_setup)
    @unittest.skipUnless(SETUP.is_dir(), "standalone installer sources are not staged")
    def test_customer_docs_explicitly_exclude_input_method_and_speech_recognition(self) -> None:
        for name in ("readme-xiaomi.txt",):
            text = (SETUP / name).read_text(encoding="utf-8")
            self.assertIn("不包含", text)
            self.assertIn("输入法", text)
            self.assertIn("语音识别", text)


if __name__ == "__main__":
    unittest.main()
