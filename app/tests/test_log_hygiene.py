"""Log rotation, worker log handles and collapsed reconnect failures."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "source"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from bridges.xiaomi.atvv_live_bridge import ReconnectFailureLog  # noqa: E402
from standalone import xiaomi_main  # noqa: E402

GATT = "RuntimeError: GATT service discovery failed: 1"


class RotateLogTests(unittest.TestCase):
    def test_small_log_is_kept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.log"
            path.write_text("short\n", encoding="utf-8")
            xiaomi_main.rotate_log(path, max_bytes=100)
            self.assertEqual(path.read_text(encoding="utf-8"), "short\n")
            self.assertFalse(path.with_name("bridge.log.1").exists())

    def test_large_log_replaces_previous_backup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.log"
            backup = path.with_name("bridge.log.1")
            backup.write_text("old backup", encoding="utf-8")
            path.write_text("x" * 200, encoding="utf-8")
            xiaomi_main.rotate_log(path, max_bytes=100)
            self.assertFalse(path.exists())
            self.assertEqual(backup.read_text(encoding="utf-8"), "x" * 200)

    def test_missing_log_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            xiaomi_main.rotate_log(Path(directory) / "absent.log", max_bytes=1)

    def test_spawn_closes_parent_handle_and_rotates(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log_dir = Path(directory)
            path = log_dir / "bridge.log"
            path.write_text("x" * 200, encoding="utf-8")
            captured = {}

            def fake_popen(*args, **kwargs):
                captured["stdout"] = kwargs["stdout"]
                return mock.Mock(pid=1)

            with mock.patch.object(xiaomi_main, "LOG_DIR", log_dir), mock.patch.object(
                xiaomi_main, "LOG_MAX_BYTES", 100
            ), mock.patch.object(
                xiaomi_main.subprocess, "Popen", side_effect=fake_popen
            ):
                xiaomi_main.XiaomiWorkers._spawn("xiaomi-worker", [], path)

            self.assertTrue(captured["stdout"].closed)
            self.assertTrue(path.with_name("bridge.log.1").exists())


class ReconnectFailureLogTests(unittest.TestCase):
    def make(self) -> tuple[ReconnectFailureLog, list[str]]:
        lines: list[str] = []
        return ReconnectFailureLog(lines.append), lines

    def test_identical_failures_are_collapsed(self) -> None:
        failures, lines = self.make()
        self.assertTrue(failures.verbose)
        for _ in range(250):
            failures.record(GATT, 0.5)
        self.assertEqual(
            lines,
            [
                f"BRIDGE ERROR {GATT}",
                f"BRIDGE ERROR still failing after 100 attempts: {GATT}",
                f"BRIDGE ERROR still failing after 200 attempts: {GATT}",
            ],
        )

    def test_quiet_between_summaries(self) -> None:
        failures, _ = self.make()
        failures.record(GATT, 0.5)
        self.assertFalse(failures.verbose)
        for _ in range(99):
            failures.record(GATT, 0.5)
        self.assertTrue(failures.verbose)

    def test_new_error_summarises_previous_run(self) -> None:
        failures, lines = self.make()
        for _ in range(5):
            failures.record(GATT, 0.5)
        failures.record("RuntimeError: paired BLE device not found", 0.5)
        self.assertEqual(
            lines,
            [
                f"BRIDGE ERROR {GATT}",
                f"BRIDGE ERROR repeated 5 times: {GATT}",
                "BRIDGE ERROR RuntimeError: paired BLE device not found",
            ],
        )
        self.assertFalse(failures.verbose)

    def test_long_session_restarts_the_count(self) -> None:
        failures, lines = self.make()
        failures.record(GATT, 0.5)
        failures.record(GATT, 0.5)
        failures.record(GATT, ReconnectFailureLog.SESSION_SECONDS)
        self.assertEqual(
            lines,
            [
                f"BRIDGE ERROR {GATT}",
                f"BRIDGE ERROR repeated 2 times: {GATT}",
                f"BRIDGE ERROR {GATT}",
            ],
        )


if __name__ == "__main__":
    unittest.main()
