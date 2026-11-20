"""Read physical RC003 reports from one Quarbor Universal device pipe.

Wire contract: Axonkey v1.9.16, vendor/QuarborUniversalKeyboardDriverInstaller/
SDK/keyboard.proto and public/device-descriptors/rc003.svg. Only the metadata
query is written. Mappings and speech stay in the existing Xiaomi bridge.
"""

from __future__ import annotations

import re
import struct
import threading
import time
from collections.abc import Callable
from contextlib import closing


_INSTANCE = re.compile(
    r"BTHLEDEVICE\\\{00001812-0000-1000-8000-00805F9B34FB\}"
    r"_DEV_VID&012717_PID&32B8(?:_REV&[0-9A-F]{4})?_([0-9A-F]{12})"
    r"\\[A-Z0-9_&-]+", re.ASCII | re.IGNORECASE,
)
_DRIVER_NAME = b"QuarborUniversalKeyboardDriver"
_MAX_FRAME = 66_048
_MAX_REPORT = 65_536
# ClientMessage(request_id=1, query_basic_info={}), including its length.
_BASIC_QUERY = bytes.fromhex("04 00 00 00 08 01 52 00")
_BUTTONS = {
    0x28: "ok", 0x35: "tv", 0x3E: "voice", 0x4A: "home",
    0x4F: "right", 0x50: "left", 0x51: "down", 0x52: "up",
    0x65: "menu", 0x66: "power", 0x80: "volume_up", 0x81: "volume_down",
    0xF1: "back",
}


def quarbor_remote_address(device_instance: str) -> str:
    match = _INSTANCE.fullmatch(device_instance) if isinstance(device_instance, str) else None
    if not match or len(device_instance) > 511:
        raise ValueError("Select the RC003 Bluetooth HID device instance")
    return bytes.fromhex(match.group(1)).hex(":").upper()


def _pipe_name(instance: str) -> str:
    # The selected instance is restricted to ASCII by quarbor_remote_address.
    value = 0xCBF29CE484222325
    for byte in instance.upper().encode("utf-16-le"):
        value = ((value ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return rf"\\.\pipe\Quarbor.UniversalKeyboard.v1.{value:016X}"


def _rc003_keys(data: bytes) -> set[int] | None:
    """Decode a complete physical snapshot; ignore other report formats."""
    if len(data) == 6:
        usage_values = struct.unpack("<3H", data)
    elif len(data) == 7 and data[0] == 1:
        usage_values = struct.unpack_from("<3H", data, 1)
    elif len(data) == 9 and data[0] == 1:
        # Both header + three slots and ID + four slots have length nine.
        # In the first format the extra two zero header bytes decode as zero.
        usage_values = struct.unpack_from("<4H", data, 1)
    elif len(data) == 8:
        usage_values = tuple(data[2:])
        if any(1 <= value <= 3 for value in usage_values):
            return None  # HID keyboard rollover/error, not an empty report.
    else:
        return None
    return _BUTTONS.keys() & usage_values


def _varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for shift in range(0, 64, 7):
        if offset == len(data):
            break
        byte = data[offset]
        offset += 1
        if shift == 63 and byte > 1:
            break
        value |= (byte & 0x7F) << shift
        if byte < 128:
            return value, offset
    raise ValueError("Invalid protobuf varint")


def _fields(data: bytes) -> dict[int, int | bytes]:
    """Read proto3 wire fields used by the SDK, skipping fixed-size metadata."""
    fields = {}
    offset = 0
    while offset < len(data):
        tag, offset = _varint(data, offset)
        number, wire_type = divmod(tag, 8)
        if not 0 < number < (1 << 29):
            raise ValueError("Invalid protobuf field number")
        if wire_type == 0:
            fields[number], offset = _varint(data, offset)
            continue
        if wire_type == 2:
            length, offset = _varint(data, offset)
        elif wire_type in (1, 5):
            length = 8 if wire_type == 1 else 4
        else:
            raise ValueError("Unexpected protobuf wire type")
        end = offset + length
        if end > len(data):
            raise ValueError("Truncated protobuf field")
        if wire_type == 2:
            fields[number] = data[offset:end]
        offset = end
    return fields


def _message(frame: bytes) -> tuple[int, int, dict]:
    fields = _fields(frame)
    bodies = fields.keys() & {20, 21, 22, 24, 25, 26}
    if len(bodies) != 1:
        raise ValueError("Invalid Quarbor server envelope")
    body = bodies.pop()
    payload, request_id = fields[body], fields.get(1, 0)
    if not isinstance(payload, bytes) or not isinstance(request_id, int):
        raise ValueError("Invalid Quarbor server payload or request ID")
    return body, request_id, _fields(payload)


class _Pipe:
    """Cancellable byte-stream I/O using the Windows API shipped with CPython."""

    def __init__(self, path: str, stop_event: threading.Event):
        import _winapi

        self.api = _winapi
        self.stop_event = stop_event
        # FILE_WRITE_DATA is needed for the initial query. Limit server
        # impersonation to SECURITY_IDENTIFICATION, as in the official SDK.
        self.handle = _winapi.CreateFile(
            path, _winapi.GENERIC_READ | 0x0002, 0, 0, _winapi.OPEN_EXISTING,
            _winapi.FILE_FLAG_OVERLAPPED | 0x00110000, 0,
        )

    def close(self):
        self.api.CloseHandle(self.handle)

    def _complete(self, pending, error, deadline: float | None) -> int:
        api = self.api
        try:
            while error == api.ERROR_IO_PENDING:
                if self.stop_event.is_set():
                    raise InterruptedError("Stopped")
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("Quarbor frame timed out")
                if api.WaitForSingleObject(pending.event, 100) == api.WAIT_OBJECT_0:
                    break
        except BaseException:
            pending.cancel()
            pending.GetOverlappedResult(True)
            raise
        count, error = pending.GetOverlappedResult(True)
        if error:
            raise OSError(error, "Quarbor pipe I/O failed")
        if count == 0:
            raise EOFError("Quarbor pipe closed")
        return count

    def _read(self, length: int, deadline: float | None) -> bytes:
        result = bytearray()
        while len(result) < length:
            pending, error = self.api.ReadFile(self.handle, length - len(result), True)
            self._complete(pending, error, deadline)
            result.extend(pending.getbuffer())
            if deadline is None:
                deadline = time.monotonic() + 5
        return bytes(result)

    def frame(self, limit: int, *, deadline: float | None = None) -> bytes:
        size = int.from_bytes(self._read(4, deadline), "little")
        if not 1 <= size <= limit:
            raise ValueError("Invalid Quarbor frame length")
        return self._read(size, deadline if deadline is not None else time.monotonic() + 5)

    def query_info(self):
        buf = _BASIC_QUERY
        deadline = time.monotonic() + 5
        while buf:
            pending, error = self.api.WriteFile(self.handle, buf, True)
            buf = buf[self._complete(pending, error, deadline):]


class QuarborInput:
    def __init__(self, device_instance: str, on_key: Callable[[str, bool], None],
                 on_reset: Callable[[], None]):
        quarbor_remote_address(device_instance)
        self.instance = device_instance
        self.on_key = on_key
        self.on_reset = on_reset
        self._stop = threading.Event()
        self._worker = None
        self._lock = threading.Lock()
        self._status = None

    def _note(self, text: str):
        if self._status != text:
            self._status = text
            print(f"XIAOMI QUARBOR {text}", flush=True)

    def start(self) -> bool:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._stop.clear()
                self._worker = threading.Thread(target=self._run, name="rc003-quarbor", daemon=True)
                self._worker.start()
        return True

    def stop(self):
        with self._lock:
            self._stop.set()
            worker = self._worker
        if worker is not None and worker is not threading.current_thread():
            worker.join()

    def _session(self, pipe):
        deadline = time.monotonic() + 5
        kind, request_id, hello = _message(pipe.frame(_MAX_FRAME, deadline=deadline))
        if (kind, request_id) != (20, 0):
            raise ValueError("Missing Quarbor v2 hello")
        limit = hello.get(2, 0)
        if hello.get(1) != 2 or not isinstance(limit, int) or not 4 <= limit <= _MAX_FRAME:
            raise ValueError("Unsupported Quarbor protocol version or payload limit")
        pipe.query_info()
        while time.monotonic() < deadline:
            kind, request_id, info = _message(pipe.frame(limit, deadline=deadline))
            if (kind, request_id) == (21, 1):
                break
            if request_id == 0 and kind in (22, 25):
                continue  # Never deliver reports until the device confirms its identity.
            raise ValueError("Invalid Quarbor metadata response")
        else:
            raise TimeoutError("Quarbor device identity was not confirmed in time")
        expected = self.instance.upper().encode("ascii")
        actual = info.get(3)
        report_max = info.get(5, 0)
        if info.get(1) != _DRIVER_NAME or not isinstance(actual, bytes) or actual.upper() != expected:
            raise ValueError("Quarbor driver or device instance mismatch")
        if not isinstance(report_max, int) or not 6 <= report_max <= _MAX_REPORT:
            raise ValueError("Quarbor physical reports are unavailable")
        self._note("connected to selected RC003")
        previous = set()
        sequence = 0
        try:
            while not self._stop.is_set():
                kind, request_id, report = _message(pipe.frame(limit))
                if kind in (24, 25, 26):
                    continue  # Command/status notifications do not describe physical keys.
                if (kind, request_id) != (22, 0):
                    raise ValueError("Unexpected message in Quarbor report stream")
                number, data = report.get(1), report.get(3)
                if not isinstance(number, int) or number <= sequence:
                    raise ValueError("Invalid Quarbor physical report sequence")
                if not isinstance(data, bytes) or not 1 <= len(data) <= report_max:
                    raise ValueError("Invalid Quarbor physical report payload")
                sequence = number
                current = _rc003_keys(data)
                if current is None or self._stop.is_set():
                    continue
                for usage in sorted(previous - current):
                    self.on_key(_BUTTONS[usage], False)
                for usage in sorted(current - previous):
                    self.on_key(_BUTTONS[usage], True)
                previous = current
        finally:
            # An interrupted pipe cannot prove the user released a button.
            # Cancel repeats/gesture state, without generating release actions.
            self.on_reset()

    def _run(self):
        path = _pipe_name(self.instance)
        while not self._stop.is_set():
            try:
                with closing(_Pipe(path, self._stop)) as pipe:
                    self._session(pipe)
            except (OSError, EOFError, ValueError) as error:
                if not self._stop.is_set():
                    self._note(f"waiting for selected RC003: {error}")
            self._stop.wait(2)
