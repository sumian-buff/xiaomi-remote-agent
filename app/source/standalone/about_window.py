"""Native Tk About window with project attribution and GPL information."""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk
import webbrowser

from standalone.about_info import LICENSE_NOTICE, PROJECT_LINKS, UPSTREAM_NOTICE

BACKGROUND = "#f3f7fc"
TEXT = "#13213a"
MUTED = "#66758a"


def about_window_size(screen_width: int, screen_height: int) -> tuple[int, int]:
    """Fit the About window on small or scaled displays."""
    if screen_width <= 0 or screen_height <= 0:
        raise ValueError("screen dimensions must be positive")
    return min(640, max(320, screen_width - 48), screen_width), min(
        360, max(240, screen_height - 96), screen_height
    )


class AboutWindow:
    """Own a single, non-modal About window."""

    def __init__(
        self,
        owner: tk.Misc,
        app_name: str,
        app_version: str,
        logger: Callable[[str], None],
    ) -> None:
        self.owner = owner
        self.app_name = app_name
        self.app_version = app_version
        self.logger = logger
        self.window: tk.Toplevel | None = None

    def show(self) -> None:
        if self._window_exists():
            assert self.window is not None
            self.window.deiconify()
            self.window.lift()
            self.window.focus_force()
            return
        self._build()

    def close(self) -> None:
        window, self.window = self.window, None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _window_exists(self) -> bool:
        if self.window is None:
            return False
        try:
            return bool(self.window.winfo_exists())
        except tk.TclError:
            self.window = None
            return False

    def _build(self) -> None:
        window = tk.Toplevel(self.owner)
        self.window = window
        window.title(f"关于 {self.app_name}")
        window.configure(background=BACKGROUND)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda _event: self.close())
        window.bind("<Control-w>", lambda _event: self.close())
        window.bind("<Destroy>", self._on_destroy, add="+")
        screen_width, screen_height = window.winfo_screenwidth(), window.winfo_screenheight()
        width, height = about_window_size(screen_width, screen_height)
        window.geometry(
            f"{width}x{height}+{max(0, (screen_width - width) // 2)}"
            f"+{max(0, (screen_height - height) // 2)}"
        )
        window.minsize(min(320, width), min(240, height))
        content = tk.Frame(window, background=BACKGROUND, padx=24, pady=20)
        content.pack(fill="both", expand=True)
        for text, font, color in (
            (self.app_name, ("Microsoft YaHei UI", 18, "bold"), TEXT),
            (f"版本 {self.app_version}", ("Microsoft YaHei UI", 10), MUTED),
            (UPSTREAM_NOTICE, ("Microsoft YaHei UI", 10), TEXT),
            (LICENSE_NOTICE, ("Microsoft YaHei UI", 10), MUTED),
        ):
            label = tk.Label(
                content, text=text, font=font, foreground=color,
                background=BACKGROUND, wraplength=max(200, width - 64), justify="left",
            )
            label.pack(anchor="w", pady=(0, 12))
            content.bind(
                "<Configure>",
                lambda event, widget=label: widget.configure(wraplength=max(100, event.width - 48)),
                add="+",
            )
        footer = tk.Frame(content, background=BACKGROUND)
        footer.pack(fill="x", pady=(4, 0))
        for title, url in PROJECT_LINKS:
            ttk.Button(
                footer, text=title, command=lambda selected=url: self._open_link(selected)
            ).pack(side="left", padx=(0, 8))
        ttk.Button(footer, text="关闭", command=self.close).pack(side="right")
        window.after_idle(window.focus_force)

    def _open_link(self, url: str) -> None:
        try:
            if not webbrowser.open(url, new=2):
                self.logger(f"Could not open project link: {url}")
        except Exception as exc:
            self.logger(f"Could not open project link: {type(exc).__name__}: {exc}")

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self.window:
            self.window = None
