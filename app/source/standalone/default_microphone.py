"""Opt-in default capture switching for console and multimedia roles only."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import threading
import uuid
import winreg


ROLES = (0, 1)  # eConsole, eMultimedia; never eCommunications (2).
HRESULT = ctypes.c_int32
CAPTURE_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Capture"
FRIENDLY_NAME = "{a45c254e-df1c-4efd-8020-67d146a850e0},2"


class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, value: str) -> GUID:
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


def _check_hr(result: int, operation: str) -> None:
    if result < 0:
        raise OSError(f"{operation} failed (HRESULT 0x{result & 0xffffffff:08X})")


def _vcall(pointer, index: int, argtypes: tuple, *args):
    table = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    method = ctypes.WINFUNCTYPE(HRESULT, ctypes.c_void_p, *argtypes)(table[index])
    return method(pointer, *args)


class WindowsAudioPolicy:
    """Small COM adapter; no device access occurs until entered explicitly."""

    def __enter__(self):
        self.enumerator = ctypes.c_void_p()
        self.policy = ctypes.c_void_p()
        self._uninitialize = False
        self.ole32 = ctypes.WinDLL("ole32", use_last_error=True)
        self.ole32.CoInitializeEx.argtypes = (ctypes.c_void_p, wintypes.DWORD)
        self.ole32.CoInitializeEx.restype = HRESULT
        self.ole32.CoUninitialize.argtypes = ()
        self.ole32.CoUninitialize.restype = None
        self.ole32.CoCreateInstance.argtypes = (
            ctypes.POINTER(GUID), ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p),
        )
        self.ole32.CoCreateInstance.restype = HRESULT
        self.ole32.CoTaskMemFree.argtypes = (ctypes.c_void_p,)
        self.ole32.CoTaskMemFree.restype = None
        result = self.ole32.CoInitializeEx(None, 2)
        # A thread already initialized in the other apartment may still use COM.
        if result & 0xffffffff != 0x80010106:  # RPC_E_CHANGED_MODE
            _check_hr(result, "CoInitializeEx")
            self._uninitialize = True
        try:
            self.enumerator = self._create(
                "BCDE0395-E52F-467C-8E3D-C4579291692E",
                "A95664D2-9614-4F35-A746-DE8DB63617E6",
            )
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_args):
        for pointer in (self.policy, self.enumerator):
            if pointer:
                _vcall(pointer, 2, ())  # IUnknown.Release
        if self._uninitialize:
            self.ole32.CoUninitialize()

    def _create(self, class_id: str, interface_id: str):
        clsid, iid = GUID.parse(class_id), GUID.parse(interface_id)
        pointer = ctypes.c_void_p()
        _check_hr(self.ole32.CoCreateInstance(
            ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(pointer),
        ), "CoCreateInstance")
        return pointer

    def get_default(self, role: int) -> str:
        if role not in ROLES:
            raise ValueError("Only console and multimedia roles are supported")
        device = ctypes.c_void_p()
        endpoint = ctypes.c_void_p()
        try:
            # IMMDeviceEnumerator.GetDefaultAudioEndpoint(eCapture=1, role).
            _check_hr(_vcall(self.enumerator, 4,
                (ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)),
                1, role, ctypes.byref(device)), "GetDefaultAudioEndpoint")
            # IMMDevice.GetId returns CoTaskMem-allocated UTF-16.
            _check_hr(_vcall(device, 5, (ctypes.POINTER(ctypes.c_void_p),),
                ctypes.byref(endpoint)), "IMMDevice.GetId")
            if not endpoint:
                raise OSError("Default recording endpoint has no ID")
            return ctypes.wstring_at(endpoint)
        finally:
            if endpoint:
                self.ole32.CoTaskMemFree(endpoint)
            if device:
                _vcall(device, 2, ())

    def set_default(self, endpoint_id: str, role: int) -> None:
        if role not in ROLES:
            raise ValueError("Only console and multimedia roles are supported")
        if not self.policy:
            self.policy = self._create(
                "870AF99C-171D-4F9E-AF0D-E63DF40C2BC9",
                "F8679F50-850A-41CF-9C72-430F290290C8",
            )
        # IPolicyConfig: IUnknown(3) + ten methods before SetDefaultEndpoint.
        _check_hr(_vcall(self.policy, 13, (wintypes.LPCWSTR, ctypes.c_int),
            endpoint_id, role), "IPolicyConfig.SetDefaultEndpoint")

    def cable_endpoint(self) -> str | None:
        candidates = []
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, CAPTURE_KEY) as root:
            index = 0
            while True:
                try:
                    name = winreg.EnumKey(root, index)
                except OSError as exc:
                    if exc.winerror == 259:  # ERROR_NO_MORE_ITEMS
                        break
                    raise
                index += 1
                try:
                    with winreg.OpenKey(root, name) as device:
                        if winreg.QueryValueEx(device, "DeviceState")[0] != 1:
                            continue
                        with winreg.OpenKey(device, "Properties") as properties:
                            label = str(winreg.QueryValueEx(properties, FRIENDLY_NAME)[0])
                    if label.casefold().startswith("cable output"):
                        candidates.append("{0.0.1.00000000}." + name)
                except FileNotFoundError:
                    # A device may disappear while enumerating; it is not a candidate.
                    continue
        if len(candidates) > 1:
            raise RuntimeError("检测到多个 CABLE Output，请先在 Windows 声音设置中确认设备。")
        return candidates[0] if candidates else None


class DefaultMicrophone:
    def __init__(self, backup_path: Path, backend_factory=WindowsAudioPolicy):
        self.backup_path = Path(backup_path)
        self.backend_factory = backend_factory
        self._lock = threading.RLock()

    def _backup(self) -> dict[int, str] | None:
        if not self.backup_path.exists():
            return None
        data = json.loads(self.backup_path.read_text(encoding="utf-8"))
        defaults = data.get("defaults", {}) if isinstance(data, dict) else {}
        if (not isinstance(data, dict) or data.get("version") != 1
                or not isinstance(defaults, dict) or set(defaults) != {"0", "1"}
                or any(not isinstance(value, str) or not value for value in defaults.values())):
            raise ValueError("默认录音设备备份损坏，请保留备份文件并检查日志。")
        return {int(role): value for role, value in defaults.items()}

    def _save_backup(self, defaults: dict[int, str]) -> None:
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.backup_path.with_suffix(self.backup_path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                json.dump({"version": 1, "defaults": defaults}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.backup_path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _defaults(backend) -> dict[int, str]:
        return {role: backend.get_default(role) for role in ROLES}

    @classmethod
    def _apply(cls, backend, desired: dict[int, str], before: dict[int, str]) -> None:
        try:
            for role in ROLES:
                backend.set_default(desired[role], role)
            if cls._defaults(backend) != desired:
                raise RuntimeError("Windows 默认录音设备读回结果不一致。")
        except Exception as exc:
            rollback_errors = []
            for role in ROLES:
                try:
                    backend.set_default(before[role], role)
                except Exception as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            detail = "; ".join(rollback_errors)
            suffix = f"；回滚也失败：{detail}" if detail else "；已尝试恢复操作前设备"
            raise RuntimeError(f"设置默认录音设备失败：{exc}{suffix}。原设备备份已保留。") from exc

    def status(self) -> dict:
        with self._lock, self.backend_factory() as backend:
            backup = self._backup()
            defaults = self._defaults(backend)
            cable = backend.cable_endpoint()
            return {"is_cable": bool(cable) and all(value == cable for value in defaults.values()),
                    "can_restore": backup is not None, "defaults": defaults, "cable_endpoint": cable}

    def set_cable(self) -> None:
        with self._lock, self.backend_factory() as backend:
            cable = backend.cable_endpoint()
            if not cable:
                raise RuntimeError("未找到启用的 CABLE Output，请先安装 VB-CABLE。")
            backup = self._backup()
            before = self._defaults(backend)
            desired = {role: cable for role in ROLES}
            if before == desired:
                return
            if backup is None:
                self._save_backup(before)
            self._apply(backend, desired, before)

    def restore(self) -> None:
        with self._lock, self.backend_factory() as backend:
            backup = self._backup()
            if backup is None:
                raise RuntimeError("没有可恢复的默认录音设备备份。")
            before = self._defaults(backend)
            self._apply(backend, backup, before)
            self.backup_path.unlink()
