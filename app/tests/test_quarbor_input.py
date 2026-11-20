from __future__ import annotations

import os
from pathlib import Path
import struct
import sys
import threading
import unittest
from unittest import mock
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "source"))
from bridges.xiaomi import quarbor_input as q


# Instance and expected name from the upstream SDK client hash test vector.
INSTANCE = (r"BTHLEDEVICE\{00001812-0000-1000-8000-00805F9B34FB}"
            r"_DEV_VID&012717_PID&32B8_REV&00A4_AABBCCDDEEFF\8&7CE84E7&0&0055")


def varint(n):
    data = bytearray()
    while n >= 128:
        data.append(128 | (n & 127))
        n >>= 7
    return bytes(data) + bytes([n])


def field(number, value):
    if isinstance(value, int):
        return varint(number * 8) + varint(value)
    return varint(number * 8 + 2) + varint(len(value)) + value


def message(body, payload, request=0):
    return (field(1, request) if request else b"") + field(body, payload)


HELLO = message(20, field(1, 2) + field(2, 66048))


def info(instance=INSTANCE, driver=q._DRIVER_NAME, request=1):
    return message(21, field(1, driver) + field(3, instance.encode()) + field(5, 65536), request)


def physical(sequence, data):
    return message(22, field(1, sequence) + b"\x11" + bytes(8) + field(3, data))


def slots(*usages):
    return struct.pack("<B3H", 1, *(list(usages) + [0] * (3 - len(usages))))


class FakePipe:
    def __init__(self, *frames):
        self.frames = iter(frames)
        self.queries = 0

    def frame(self, _limit, *, deadline=None):
        try:
            return next(self.frames)
        except StopIteration:
            raise EOFError from None

    def query_info(self):
        self.queries += 1


class QuarborTests(unittest.TestCase):
    def setUp(self):
        self.keys = mock.Mock()
        self.reset = mock.Mock()
        self.reader = q.QuarborInput(INSTANCE, self.keys, self.reset)
        self.reader._note = mock.Mock()

    def test_exact_device_and_sdk_hash(self):
        self.assertEqual(q.quarbor_remote_address(INSTANCE.lower()), "AA:BB:CC:DD:EE:FF")
        self.assertEqual(q._pipe_name(INSTANCE.lower()),
                         r"\\.\pipe\Quarbor.UniversalKeyboard.v1.802FE7812EA77168")
        for bad in [None, "", INSTANCE[:40], INSTANCE.replace("1812", "180F"),
                    INSTANCE.replace("32B8", "32B9"), INSTANCE.replace("AABB", "*ABB"),
                    INSTANCE + "\\child", INSTANCE + "\0", INSTANCE + "A" * 512]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                q.QuarborInput(bad, self.keys, self.reset)

    def test_all_physical_keys_have_down_and_up_and_holds_cannot_repeat(self):
        reports = []
        expected = []
        for usage, name in q._BUTTONS.items():
            for data in [slots(usage), slots(usage), slots()]:
                reports.append(physical(30 + len(reports), data))
            expected += [mock.call(name, True), mock.call(name, False)]
        self.assertEqual(len(expected), 26)
        pipe = FakePipe(HELLO, info(), *reports)
        with self.assertRaises(EOFError):
            self.reader._session(pipe)
        self.assertEqual(self.keys.call_args_list, expected)
        self.assertEqual(pipe.queries, 1)
        self.reset.assert_called_once_with()

    def test_drops_pre_handshake_snapshots_and_never_accepts_wrong_identity(self):
        before = physical(10, slots(0x28))
        for bad in [info(instance=INSTANCE.replace("AABB", "0ABB")), info(driver=b"other"),
                    info(request=99), message(24, b"", 1)]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.reader._session(FakePipe(HELLO, before, bad))
        self.keys.assert_not_called()
        with self.assertRaises(EOFError):
            self.reader._session(FakePipe(HELLO, before, message(25, b""), info(),
                                          message(25, b"", 4), physical(11, slots(0xF1))))
        self.keys.assert_called_once_with("back", True)
        self.reset.assert_called_once_with()

    def test_status_and_other_report_ids_do_not_release_a_held_key(self):
        reports = [physical(54, slots(0x80)), message(25, field(1, 1), 9),
                   physical(56, bytes.fromhex("02 00 00 00 00 00 00")),
                   physical(57, slots(0x80)), physical(58, slots(0xF1))]
        with self.assertRaises(EOFError):
            self.reader._session(FakePipe(HELLO, info(), *reports))
        self.assertEqual(self.keys.call_args_list, [
            mock.call("volume_up", True), mock.call("volume_up", False), mock.call("back", True),
        ])
        self.reset.assert_called_once_with()

    def test_rc003_report_layouts(self):
        for data in ["81 00 f1 00 00 00", "01 81 00 f1 00 00 00",
                     "01 00 00 81 00 f1 00 00 00", "01 81 00 f1 00 00 00 00 00",
                     "00 00 81 f1 00 00 00 00"]:
            self.assertEqual(q._rc003_keys(bytes.fromhex(data)), {0x81, 0xF1})
        self.assertIsNone(q._rc003_keys(bytes.fromhex("00 00 01 01 01 01 01 01")))
        self.assertIsNone(q._rc003_keys(bytes.fromhex("03 81 00")))
        self.assertEqual(q._rc003_keys(slots()), set())

    def test_invalid_wire_data_and_sequence_reset_the_session(self):
        for data in [b"\0", bytes([8, 128]), bytes([42, 128, 16]), bytes([255]) * 11]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                q._message(data)
        with self.assertRaises(ValueError):
            self.reader._session(FakePipe(HELLO, info(), physical(8, slots(0x81)),
                                          physical(7, slots(0xF1))))
        self.keys.assert_called_once_with("volume_down", True)
        self.reset.assert_called_once_with()

    @unittest.skipUnless(os.name == "nt", "Windows named pipes")
    def test_real_byte_pipe_query_framing_and_idle_cancellation(self):
        import _winapi

        # This isolated server uses a random test name and no device driver.
        path = r"\\.\pipe\XiaomiRemoteAgent-test-" + uuid.uuid4().hex
        flags = _winapi.PIPE_ACCESS_DUPLEX | _winapi.FILE_FLAG_OVERLAPPED
        server = _winapi.CreateNamedPipe(path, flags, 0, 1, 4096, 4096, 1000, 0)
        self.addCleanup(_winapi.CloseHandle, server)
        connect = _winapi.ConnectNamedPipe(server, overlapped=True)
        stop = threading.Event()
        pipe = q._Pipe(path, stop)
        self.addCleanup(pipe.close)
        self.assertEqual(connect.GetOverlappedResult(True)[1], 0)
        pipe.query_info()
        read, _ = _winapi.ReadFile(server, 8, True)
        self.assertEqual(read.GetOverlappedResult(True), (8, 0))
        self.assertEqual(read.getbuffer(), bytes.fromhex("04 00 00 00 08 01 52 00"))
        blob = len(HELLO).to_bytes(4, "little") + HELLO
        for piece in [blob[:2], blob[2:6], blob[6:]]:
            write, _ = _winapi.WriteFile(server, piece, True)
            self.assertEqual(write.GetOverlappedResult(True), (len(piece), 0))
        self.assertEqual(pipe.frame(66048), HELLO)
        timer = threading.Timer(0.05, stop.set)
        timer.start()
        self.addCleanup(timer.join)
        with self.assertRaises(InterruptedError):
            pipe.frame(66048)
