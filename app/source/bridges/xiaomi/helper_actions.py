"""Build argument vectors for the bundled helper; never invoke a shell."""

from __future__ import annotations

from .app_catalog import helper_path, resolve_app_id


def parse_helper_args(action: dict) -> list[str]:
    args = action.get("args")
    if not isinstance(args, list) or not args or any(
        not isinstance(value, str) or not value or "\0" in value for value in args
    ):
        raise ValueError("helper 动作需要非空字符串参数列表")
    command, *values = args
    if command == "ok" and not values:
        return list(args)
    if command == "arrow" and values in (["up"], ["down"]):
        return list(args)
    if command == "session" and values in (["prev"], ["next"]):
        return list(args)
    if command == "scroll" and len(values) == 1:
        delta = int(values[0])
        if delta and abs(delta) <= 32767:
            return [command, str(delta)]
    if command == "activate" and len(values) == 1:
        return [command, resolve_app_id(values[0])]
    raise ValueError(f"无效的 helper 动作参数：{args!r}")


def helper_command(action: dict) -> list[str]:
    return [str(helper_path()), *parse_helper_args(action)]
