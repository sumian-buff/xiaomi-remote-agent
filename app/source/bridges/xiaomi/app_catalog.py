"""Resolve installed application identities without Start menu shortcuts."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from process_utils import CREATE_NO_WINDOW, hidden_startupinfo


CATALOG_ENV = "XIAOMI_REMOTE_AGENT_APP_IDS"


def helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "remote-helper.exe"
    return Path(__file__).resolve().parents[3] / "helper" / "remote-helper.exe"


def select_app_ids(entries: list[dict]) -> dict[str, str]:
    result: dict[str, str] = {}
    for entry in entries:
        name = str(entry.get("name", "")).casefold()
        app_id = str(entry.get("app_id", ""))
        folded = app_id.casefold()
        if name == "claude" and fnmatch.fnmatchcase(folded, "claude_*!claude"):
            result["claude"] = app_id
        elif fnmatch.fnmatchcase(folded, "openai.codex_*!app"):
            result["codex"] = app_id
        elif name in {"workbuddy", "wechat", "微信", "qwenwork", "千问办公"}:
            alias = {"微信": "wechat", "qwenwork": "qianwen", "千问办公": "qianwen"}.get(name, name)
            # Only AppIDs are allowed; never launch a shortcut returned by the shell.
            if app_id and not folded.endswith(".lnk"):
                result[alias] = app_id
    return result


def refresh_app_ids() -> dict[str, str]:
    """Called once at host startup; workers inherit the resulting catalog."""
    with tempfile.TemporaryDirectory(prefix="XiaomiRemoteAgent-apps-") as directory:
        output = Path(directory) / "apps.json"
        subprocess.run(
            [str(helper_path()), "apps", str(output)],
            check=True,
            timeout=20,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=hidden_startupinfo(),
        )
        entries = json.loads(output.read_text(encoding="utf-8-sig"))
    result = select_app_ids(entries)
    os.environ[CATALOG_ENV] = json.dumps(result)
    return result


def resolve_app_id(alias: str) -> str:
    # Also migrate saved presets containing an older package family example.
    folded = alias.casefold()
    if fnmatch.fnmatchcase(folded, "claude_*!claude"):
        alias = "claude"
    elif fnmatch.fnmatchcase(folded, "openai.codex_*!app"):
        alias = "codex"
    if alias not in {"claude", "codex", "workbuddy", "wechat", "qianwen"}:
        raise ValueError(f"未知应用：{alias}")
    catalog = json.loads(os.environ.get(CATALOG_ENV, "{}"))
    if alias not in catalog:
        catalog = refresh_app_ids()
    if not catalog.get(alias):
        raise ValueError(f"未在 Windows 应用列表中找到 {alias}，请安装应用后重启本程序")
    return catalog[alias]
