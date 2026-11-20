"""Replay ATVV button and audio notifications without Bluetooth or real keyboard input."""

import asyncio
import sys
import unittest
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from bridges.xiaomi import atvv_live_bridge as bridge


def replay(events, mode="hold"):
    now = 0.0
    trace = []
    events = deque(events)
    stop = asyncio.Event()
    device = mock.Mock(connection_status=1)
    audio, control, tx = mock.Mock(), mock.Mock(), mock.Mock()
    for characteristic in (audio, control):
        characteristic.write_client_characteristic_configuration_descriptor_async = (
            mock.AsyncMock(return_value=0)
        )
    chars = {
        bridge.VOICE_AUDIO_UUID: audio,
        bridge.VOICE_CONTROL_UUID: control,
        bridge.VOICE_TX_UUID: tx,
    }

    def record(name):
        trace.append((name, round(now, 3)))

    keyboard = mock.Mock()

    def record_key(vk, up):
        key = "ctrl-" if vk == 0x11 else ""
        record(key + ("up" if up else "down"))

    keyboard.send_scan_code_vk.side_effect = record_key
    shortcut = bridge.VoiceShortcut("ctrl+d", keyboard=keyboard)
    output = mock.Mock(sent_packets=0, dropped_chunks=0, sample_rate=48000)
    output.clear.side_effect = lambda: record("clear")
    output.end_session.side_effect = lambda: record("end")
    output.push_16k.side_effect = lambda _: record("audio")
    notifications = {
        "press": (control, b"\x08"),
        "start": (control, b"\x04\x03\x02\x69"),
        "next_start": (control, b"\x04\x03\x02\x6a"),
        "release": (control, b"\x00\x02"),
        "limit": (control, b"\x00\x08"),
        "frame": (audio, bytes([0x12]) * 120),
    }

    async def wait_for(get_event, timeout):
        nonlocal now
        # Writes to the fake device finish immediately. Only the notification
        # queue advances the simulated clock.
        if get_event.cr_code is not asyncio.Queue.get.__code__:
            return await get_event
        at, action, *handled_at = events[0]
        if at > now + timeout:
            now += timeout
            get_event.close()
            raise asyncio.TimeoutError
        now = max(at, now)
        events.popleft()
        if action in ("disconnect", "exit"):
            if action == "disconnect":
                device.connection_status = 0
            else:
                stop.set()
            get_event.close()
            raise asyncio.TimeoutError
        char, data = notifications[action]
        callback = char.add_value_changed.call_args.args[0]
        callback(char, SimpleNamespace(characteristic_value=data))
        event = await get_event
        if handled_at:
            now = handled_at[0]
        return event

    async def drain(duration):
        nonlocal now
        now += duration

    with (
        mock.patch.object(bridge, "BluetoothLEDevice") as bluetooth,
        mock.patch.object(
            bridge,
            "discover_atvv",
            new_callable=mock.AsyncMock,
            return_value=(mock.Mock(), chars),
        ),
        mock.patch.object(bridge, "write_command", new_callable=mock.AsyncMock),
        mock.patch.object(bridge, "buffer_bytes", bytes),
        mock.patch.object(bridge, "VoiceShortcut", return_value=shortcut),
        mock.patch.object(bridge, "UdpPcmOutput", return_value=output),
        mock.patch.object(
            bridge, "time", SimpleNamespace(monotonic=lambda: now, sleep=lambda _: None)
        ),
        mock.patch.object(bridge.asyncio, "wait_for", side_effect=wait_for),
        mock.patch.object(bridge.asyncio, "sleep", side_effect=drain),
        mock.patch.object(
            bridge, "play_limit_warning", side_effect=lambda: record("beep")
        ),
        mock.patch.object(bridge, "VOICE_LIMIT_WARN_S", 55.0),
        mock.patch.object(bridge, "AUTO_CONTINUE_ENABLED", False),
        mock.patch("builtins.print"),
    ):
        bluetooth.from_bluetooth_address_async = mock.AsyncMock(return_value=device)
        try:
            asyncio.run(
                bridge.bridge_once(
                    "AA:BB:CC:DD:EE:FF", 0.0, True, "ctrl+d", mode, stop, None, None
                )
            )
        except ConnectionError:
            if device.connection_status != 0:
                raise
            record("disconnected")
    if events:
        raise AssertionError(f"unprocessed notifications: {events!r}")
    return trace


class VoiceContinuationTests(unittest.TestCase):
    def test_two_represses_after_beeps_keep_one_dictation_and_all_three_audio_segments(
        self,
    ):
        events = [
            (0, "press"),
            (0.1, "start"),
            (0.2, "frame"),
            (55.5, "release"),
            (55.55, "release"),
            (55.6, "frame"),
            (56.3, "press"),
            (56.8, "start"),
            (56.9, "frame"),
            (112, "limit"),
            (112.05, "release"),
            (112.5, "press"),
            (112.6, "start"),
            (112.7, "frame"),
            (114, "release"),
            (116, "exit"),
        ]
        for mode in ("hold", "toggle"):
            with self.subTest(mode=mode):
                trace = replay(events, mode)
                self.assertEqual(
                    [t for name, t in trace if name == "audio"], [0.2, 56.9, 112.7]
                )
                self.assertEqual([t for name, t in trace if name == "clear"], [0.1])
                self.assertEqual(sum(name == "beep" for name, _ in trace), 2)
                finishes = [t for name, t in trace if name == "end"]
                self.assertEqual(len(finishes), 1)
                self.assertLessEqual(114, finishes[0])
                self.assertLess(finishes[0], 114.5)
                edges = [(name, t) for name, t in trace if name in ("down", "up")]
                expected_edges = [("down", 0.1), ("up", finishes[0])]
                if mode == "toggle":
                    expected_edges = [
                        ("down", 0.1),
                        ("up", 0.1),
                        ("down", finishes[0]),
                        ("up", finishes[0]),
                    ]
                self.assertEqual(edges, expected_edges)
                modifier_edges = [
                    (name.removeprefix("ctrl-"), t)
                    for name, t in trace
                    if name.startswith("ctrl-")
                ]
                self.assertEqual(modifier_edges, expected_edges)

    def test_short_press_ends_promptly_and_stale_stop_cannot_toggle_again(self):
        trace = replay(
            [
                (0, "release"),
                (1, "press"),
                (1.1, "start"),
                (2, "release"),
                (2.3, "release"),
                (4, "exit"),
            ],
            "toggle",
        )
        self.assertNotIn("beep", [name for name, _ in trace])
        taps = [t for name, t in trace if name == "down"]
        self.assertEqual(len(taps), 2)
        self.assertEqual(taps[0], 1.1)
        self.assertLess(taps[1], 2.5)
        self.assertEqual([t for name, t in trace if name == "end"], [taps[1]])

    def test_release_and_late_repress_finish_first_dictation_before_starting_second(
        self,
    ):
        trace = replay(
            [
                (0, "start"),
                (55.2, "release"),
                (57, "press"),
                (57.1, "start"),
                (58, "release"),
                (60, "exit"),
            ]
        )
        edges = [(name, t) for name, t in trace if name in ("down", "up")]
        self.assertEqual([name for name, _ in edges], ["down", "up", "down", "up"])
        self.assertGreaterEqual(edges[1][1], 56.2)
        self.assertLess(edges[1][1], 57)
        self.assertEqual(edges[2], ("down", 57.1))

    def test_repress_without_audio_start_cannot_leave_shortcut_held(self):
        for early_frame in ([], [(55.9, "frame")]):
            with self.subTest(early_frame=bool(early_frame)):
                trace = replay(
                    [
                        (0, "start"),
                        (55.2, "release"),
                        (55.8, "press"),
                        *early_frame,
                        (62, "exit"),
                    ]
                )
                self.assertEqual(
                    [name for name, _ in trace if name in ("down", "up")],
                    ["down", "up"],
                )
                ends = [t for name, t in trace if name == "end"]
                self.assertEqual(len(ends), 1)
                self.assertGreater(ends[0], 56.2)
                self.assertLess(ends[0], 60)

    def test_new_session_id_can_resume_without_press_notification(self):
        trace = replay(
            [
                (0, "start"),
                (0.1, "frame"),
                (55.3, "release"),
                (55.4, "start"),
                (55.5, "frame"),  # duplicate old START and stale audio
                # The callback arrived in time but processing missed the deadline.
                (55.6, "next_start", 56.5),
                (56.6, "frame"),
                (57, "release"),
                (58, "exit"),
            ]
        )
        self.assertEqual([t for name, t in trace if name == "audio"], [0.1, 56.6])
        self.assertEqual([t for name, t in trace if name == "down"], [0])
        self.assertEqual([t for name, t in trace if name == "clear"], [0])
        self.assertEqual(sum(name == "end" for name, _ in trace), 1)

    def test_audio_arriving_before_start_on_repress_stays_in_same_session(self):
        trace = replay(
            [
                (0, "start"),
                (0.1, "frame"),
                (55.3, "release"),
                (55.6, "press"),
                (55.7, "frame"),
                (55.8, "start"),
                (55.9, "frame"),
                (57, "release"),
                (59, "exit"),
            ]
        )
        self.assertEqual([t for name, t in trace if name == "audio"], [0.1, 55.7, 55.9])
        self.assertEqual([t for name, t in trace if name == "down"], [0])
        self.assertEqual([t for name, t in trace if name == "clear"], [0])
        self.assertEqual(sum(name == "end" for name, _ in trace), 1)

    def test_disconnect_or_exit_while_waiting_finishes_toggle_once(self):
        for cause in ("disconnect", "exit"):
            with self.subTest(cause=cause):
                trace = replay(
                    [(0, "start"), (55.2, "release"), (55.4, cause)], "toggle"
                )
                self.assertEqual(sum(name == "down" for name, _ in trace), 2)
                self.assertEqual(sum(name == "up" for name, _ in trace), 2)
                ends = [t for name, t in trace if name == "end"]
                self.assertEqual(len(ends), 1)
                self.assertGreaterEqual(ends[0], 55.4)
                if cause == "disconnect":
                    self.assertIn("disconnected", [name for name, _ in trace])
