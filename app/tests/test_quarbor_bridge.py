import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from bridges.xiaomi import atvv_live_bridge as bridge
from bridges.xiaomi import hid_report_tap, xiaomi_config


INSTANCE = (
    r"BTHLEDEVICE\{00001812-0000-1000-8000-00805F9B34FB}_DEV_VID&012717_PID&32B8"
    r"_REV&00A4_AABBCCDDEEFF\8&1234567&0&0055"
)


class QuarborBridgeTests(unittest.TestCase):
    def test_config_migration_retains_explicit_backend(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "xiaomi.json"
            path.write_text('{"hid_report_tap_enabled": false}', encoding="utf-8")
            config = xiaomi_config.load_config(path)
            self.assertEqual(config["input_backend"], "legacy")
            self.assertFalse(config["hid_report_tap_enabled"])
            config.update(input_backend="quarbor", quarbor_device_instance=INSTANCE)
            path.write_text(json.dumps(config), encoding="utf-8")
            reloaded = xiaomi_config.load_config(path)
            self.assertEqual(reloaded["input_backend"], "quarbor")
            self.assertEqual(reloaded["quarbor_device_instance"], INSTANCE)

    def test_main_uses_only_pinned_source_and_voice_address(self):
        from bridges.xiaomi import quarbor_input

        config = xiaomi_config.default_config()
        config.update(input_backend="quarbor", quarbor_device_instance=INSTANCE)
        config.update(hid_report_tap_enabled=True, hid_tap_compatible=True)
        with (
            mock.patch.object(bridge, "configure_pythonw_logging"),
            mock.patch.object(bridge, "acquire_single_instance", return_value=True),
            mock.patch.object(bridge, "load_config", return_value=config),
            mock.patch.object(
                bridge,
                "load_keys_config",
                return_value=xiaomi_config.default_keys_config(),
            ),
            mock.patch.object(bridge, "discover_and_apply_xiaomi_identity") as discover,
            mock.patch.object(bridge, "XiaomiSpecialKeyHook") as hook,
            mock.patch.object(bridge, "start_raw_mapping_thread") as raw,
            mock.patch.object(hid_report_tap, "XiaomiHidReportTap") as tap,
            mock.patch.object(quarbor_input, "QuarborInput") as driver,
            mock.patch.object(
                bridge, "run", new_callable=mock.AsyncMock, return_value=0
            ) as voice,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(bridge.main([]), 0)
        keys = hook.return_value
        driver.assert_called_once_with(
            INSTANCE, keys.handle_driver_key, keys.reset_direct_hid_state
        )
        driver.return_value.start.assert_called_once()
        driver.return_value.stop.assert_called_once()
        keys.start.assert_not_called()
        keys.stop.assert_called_once()
        raw.assert_not_called()
        tap.assert_not_called()
        discover.assert_not_called()
        args, _gate, legacy_hid = voice.await_args.args
        self.assertEqual(args.address, "AA:BB:CC:DD:EE:FF")
        self.assertIsNone(legacy_hid)

    def test_driver_edges_share_mapping_and_cancel_held_keys_on_disconnect(self):
        gate = bridge.XiaomiTvActionGate(0)
        keys = bridge.XiaomiSpecialKeyHook(gate, enabled=False)
        with (
            mock.patch("builtins.print"),
            mock.patch.object(
                keys, "_send_button_action", return_value=True
            ) as dispatch,
            mock.patch.object(keys, "_start_back_repeat") as repeat_back,
            mock.patch.object(keys, "_start_volume_repeat") as repeat_volume,
        ):
            gate.mark_ready()
            for key in ("back", "volume_up", "volume_down", "ok", "up", "home", "tv"):
                keys.handle_driver_key(key, True)
                keys.handle_driver_key(key, True)
                keys.handle_driver_key(key, False)
            for key in ("voice", "mic"):
                keys.handle_driver_key(key, True)
                keys.handle_driver_key(key, False)
            keys.handle_driver_key("back", True)
            generation = keys.back_repeat_generation
            keys.reset_direct_hid_state()
            self.assertFalse(keys.direct_active_usages)
            self.assertGreater(keys.back_repeat_generation, generation)
            keys.handle_driver_key("back", True)
            keys.stop()
            keys.handle_driver_key("menu", True)
        self.assertEqual(
            [item.args[0] for item in dispatch.call_args_list],
            [
                "back",
                "volume_up",
                "volume_down",
                "ok",
                "up",
                "home",
                "tv",
                "back",
                "back",
            ],
        )
        self.assertEqual(repeat_back.call_count, 3)
        self.assertEqual(
            repeat_volume.call_args_list,
            [mock.call(0x80, "volume_up"), mock.call(0x81, "volume_down")],
        )

    def test_driver_voice_bridge_subscribes_to_atvv_only(self):
        device = mock.Mock()
        audio, control = mock.Mock(), mock.Mock()
        for characteristic in (audio, control):
            characteristic.write_client_characteristic_configuration_descriptor_async = mock.AsyncMock(
                return_value=0
            )
        tx = mock.Mock()
        services = {
            bridge.VOICE_TX_UUID: tx,
            bridge.VOICE_AUDIO_UUID: audio,
            bridge.VOICE_CONTROL_UUID: control,
        }
        stop = asyncio.Event()
        stop.set()
        with (
            mock.patch.object(bridge, "BluetoothLEDevice") as bluetooth,
            mock.patch.object(
                bridge,
                "discover_atvv",
                new_callable=mock.AsyncMock,
                return_value=(mock.Mock(), services),
            ),
            mock.patch.object(bridge.XiaomiGattHidSession, "open") as hid_open,
            mock.patch.object(bridge, "VoiceShortcut") as shortcut,
            mock.patch.object(bridge, "UdpPcmOutput"),
            mock.patch.object(
                bridge, "write_command", new_callable=mock.AsyncMock
            ) as write,
            mock.patch("builtins.print"),
        ):
            bluetooth.from_bluetooth_address_async = mock.AsyncMock(return_value=device)
            asyncio.run(
                bridge.bridge_once(
                    "AA:BB:CC:DD:EE:FF", 4, True, "ctrl+d", "hold", stop, None, None
                )
            )
        hid_open.assert_not_called()
        audio.add_value_changed.assert_called_once()
        control.add_value_changed.assert_called_once()
        write.assert_awaited_once_with(tx, bridge.GET_CAPS_V10, "GET_CAPS")
        shortcut.return_value.release.assert_called_once()
