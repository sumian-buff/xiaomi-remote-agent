from __future__ import annotations

import ctypes
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).resolve().parents[1] / "source"
sys.path.insert(0, str(SOURCE))

from standalone import default_microphone as microphone


class FakePolicy:
    def __init__(self):
        self.defaults = {0: "console-mic", 1: "media-mic", 2: "call-headset"}
        self.cable = "cable-output"
        self.reads = []
        self.writes = []
        self.fail_next_role = None
        self.ignore_next_role = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def cable_endpoint(self):
        return self.cable

    def get_default(self, role):
        self.reads.append(role)
        return self.defaults[role]

    def set_default(self, endpoint_id, role):
        self.writes.append((endpoint_id, role))
        if role == self.fail_next_role:
            self.fail_next_role = None
            raise OSError("device disappeared")
        if role == self.ignore_next_role:
            self.ignore_next_role = None
            return
        self.defaults[role] = endpoint_id


class DefaultMicrophoneTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "default-microphone.json"
        self.backend = FakePolicy()
        self.service = microphone.DefaultMicrophone(self.path, lambda: self.backend)

    def tearDown(self):
        self.assertNotIn(2, self.backend.reads)
        self.assertNotIn(2, [role for _, role in self.backend.writes])
        self.assertEqual(self.backend.defaults[2], "call-headset")

    def test_set_persists_each_original_role_before_first_change(self):
        original_set = self.backend.set_default

        def checked_set(endpoint, role):
            self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {
                "version": 1, "defaults": {"0": "console-mic", "1": "media-mic"},
            })
            original_set(endpoint, role)

        with mock.patch.object(self.backend, "set_default", side_effect=checked_set):
            self.service.set_cable()
        self.assertEqual(self.backend.defaults[0], "cable-output")
        self.assertEqual(self.backend.defaults[1], "cable-output")

    def test_repeated_set_preserves_original_backup_and_restores_each_role(self):
        self.service.set_cable()
        saved = self.path.read_bytes()
        self.service.set_cable()
        self.backend.defaults[0] = "another-mic"
        self.service.set_cable()
        self.assertEqual(self.path.read_bytes(), saved)
        self.service.restore()
        self.assertEqual(self.backend.defaults[0], "console-mic")
        self.assertEqual(self.backend.defaults[1], "media-mic")
        self.assertFalse(self.path.exists())

    def test_missing_cable_changes_nothing_and_creates_no_backup(self):
        self.backend.cable = None
        with self.assertRaisesRegex(RuntimeError, "CABLE Output"):
            self.service.set_cable()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.backend.writes, [])

    def test_persistence_failure_prevents_system_changes(self):
        with mock.patch.object(self.service, "_save_backup", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.service.set_cable()
        self.assertEqual(self.backend.writes, [])

    def test_partial_set_failure_rolls_back_and_retains_backup(self):
        self.backend.fail_next_role = 1
        with self.assertRaisesRegex(RuntimeError, "device disappeared"):
            self.service.set_cable()
        self.assertEqual(self.backend.defaults[0], "console-mic")
        self.assertEqual(self.backend.defaults[1], "media-mic")
        self.assertTrue(self.path.exists())

    def test_failed_readback_rolls_back_and_retains_backup(self):
        self.backend.ignore_next_role = 1
        with self.assertRaisesRegex(RuntimeError, "读回"):
            self.service.set_cable()
        self.assertEqual(self.backend.defaults[0], "console-mic")
        self.assertEqual(self.backend.defaults[1], "media-mic")
        self.assertTrue(self.path.exists())

    def test_restore_failure_rolls_back_to_cable_and_retains_backup(self):
        self.service.set_cable()
        self.backend.fail_next_role = 1
        with self.assertRaises(RuntimeError):
            self.service.restore()
        self.assertEqual(self.backend.defaults[0], "cable-output")
        self.assertEqual(self.backend.defaults[1], "cable-output")
        self.assertTrue(self.path.exists())
        self.service.restore()
        self.assertFalse(self.path.exists())

    def test_status_is_read_only_and_reports_restore_availability(self):
        status = self.service.status()
        self.assertFalse(status["is_cable"])
        self.assertFalse(status["can_restore"])
        self.assertEqual(self.backend.writes, [])
        self.assertFalse(self.path.exists())
        self.service.set_cable()
        status = self.service.status()
        self.assertTrue(status["is_cable"])
        self.assertTrue(status["can_restore"])

    def test_already_cable_does_not_invent_original_microphone(self):
        self.backend.defaults.update({0: "cable-output", 1: "cable-output"})
        self.service.set_cable()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.backend.writes, [])

    def test_invalid_backup_blocks_changes_including_communications_role(self):
        for value in ([], {"version": 1, "defaults": {"0": "a", "1": "b", "2": "c"}}):
            self.path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(ValueError):
                self.service.set_cable()
            self.assertEqual(self.backend.writes, [])


class AudioPolicyAbiTests(unittest.TestCase):
    def test_set_default_uses_policy_vtable_slot_13_and_requested_role(self):
        policy = microphone.WindowsAudioPolicy()
        policy.policy = ctypes.c_void_p(42)
        with mock.patch.object(microphone, "_vcall", return_value=0) as call:
            policy.set_default("endpoint-id", 1)
        self.assertEqual(call.call_args.args[1], 13)
        self.assertEqual(call.call_args.args[-2:], ("endpoint-id", 1))

    def test_get_default_uses_capture_and_releases_com_allocations(self):
        policy = microphone.WindowsAudioPolicy()
        policy.enumerator = ctypes.c_void_p(41)
        policy.ole32 = mock.Mock()
        buffer = ctypes.create_unicode_buffer("original-device")

        def vcall(pointer, index, argtypes, *args):
            if index == 4:
                self.assertEqual(args[:2], (1, 0))
                ctypes.cast(args[-1], ctypes.POINTER(ctypes.c_void_p))[0] = 42
            elif index == 5:
                ctypes.cast(args[-1], ctypes.POINTER(ctypes.c_void_p))[0] = ctypes.addressof(buffer)
            return 0

        with mock.patch.object(microphone, "_vcall", side_effect=vcall) as call:
            self.assertEqual(policy.get_default(0), "original-device")
        self.assertEqual([args.args[1] for args in call.call_args_list], [4, 5, 2])
        policy.ole32.CoTaskMemFree.assert_called_once()

    def test_backend_rejects_communications_role_before_com_access(self):
        policy = microphone.WindowsAudioPolicy()
        with self.assertRaises(ValueError):
            policy.get_default(2)
        with self.assertRaises(ValueError):
            policy.set_default("anything", 2)


if __name__ == "__main__":
    unittest.main()
