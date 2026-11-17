"""Consistent hidden Windows child-process settings for every launch path."""

from __future__ import annotations

import os
import subprocess


CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def hidden_startupinfo():
    """Hide console windows, including when Windows Terminal is the default."""
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return startupinfo
