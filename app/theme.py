"""Dark "workbench" theme for the Tkinter UI: deep slate surfaces with a cyan accent,
high-contrast text and clear status colours that read well on a bench monitor."""
from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk

from analyzer import resource_path

C = {
    "bg": "#0d1117",          # window
    "surface": "#151b23",     # lists, text areas
    "panel": "#1b2330",       # header, tabs
    "raised": "#232d3c",      # buttons
    "hover": "#2c3849",
    "border": "#2d3a4d",
    "text": "#e6edf3",
    "muted": "#8b98a9",
    "accent": "#22d3ee",
    "accent_hover": "#67e8f9",
    "accent_dim": "#0e5566",
    "on_accent": "#04131a",
    "ok": "#3fb950",
    "bad": "#f85149",
    "warn": "#f0a33a",
    "code_bg": "#0a0f16",
    "code_fg": "#a5f3fc",
    "banner": "#0f2633", "banner_fg": "#bdeaf7",
    "banner_hot": "#3a2410", "banner_hot_fg": "#ffc078",
    "High": "#e5484d", "Medium": "#d97706", "Low": "#4b5a70",
}

FONT = "Segoe UI" if sys.platform.startswith("win") else "TkDefaultFont"
MONO = "Consolas" if sys.platform.startswith("win") else "TkFixedFont"


def apply(root: tk.Tk) -> None:
    root.configure(bg=C["bg"])
    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=C["bg"], foreground=C["text"], fieldbackground=C["surface"],
                bordercolor=C["border"], lightcolor=C["bg"], darkcolor=C["bg"], troughcolor=C["surface"],
                focuscolor=C["accent"], selectbackground=C["accent_dim"], selectforeground=C["text"],
                insertcolor=C["text"], font=(FONT, 10))
    s.configure("TFrame", background=C["bg"])
    s.configure("TLabel", background=C["bg"], foreground=C["text"])
    s.configure("Muted.TLabel", foreground=C["muted"])
    s.configure("Section.TLabel", foreground=C["muted"], font=(FONT, 9, "bold"))
    s.configure("Header.TFrame", background=C["panel"])
    s.configure("Header.TLabel", background=C["panel"], foreground=C["text"])
    s.configure("Title.TLabel", background=C["panel"], foreground=C["text"], font=(FONT, 15, "bold"))
    s.configure("Subtitle.TLabel", background=C["panel"], foreground=C["muted"], font=(FONT, 9))
    s.configure("Version.TLabel", background=C["accent_dim"], foreground=C["accent_hover"],
                font=(FONT, 8, "bold"), padding=(6, 1))

    s.configure("TButton", background=C["raised"], foreground=C["text"], bordercolor=C["border"],
                lightcolor=C["raised"], darkcolor=C["raised"], focusthickness=0, padding=(12, 6))
    s.map("TButton",
          background=[("disabled", C["panel"]), ("pressed", C["accent_dim"]), ("active", C["hover"])],
          lightcolor=[("pressed", C["accent_dim"]), ("active", C["hover"])],
          darkcolor=[("pressed", C["accent_dim"]), ("active", C["hover"])],
          bordercolor=[("focus", C["accent"]), ("active", C["accent_dim"])],
          foreground=[("disabled", C["muted"])])
    s.configure("Accent.TButton", background=C["accent"], foreground=C["on_accent"], bordercolor=C["accent"],
                lightcolor=C["accent"], darkcolor=C["accent"], font=(FONT, 10, "bold"))
    s.map("Accent.TButton",
          background=[("disabled", C["panel"]), ("pressed", C["accent_dim"]), ("active", C["accent_hover"])],
          lightcolor=[("active", C["accent_hover"])], darkcolor=[("active", C["accent_hover"])],
          foreground=[("disabled", C["muted"])])
    s.configure("Header.TButton", background=C["panel"], bordercolor=C["border"],
                lightcolor=C["panel"], darkcolor=C["panel"], padding=(10, 4))

    s.configure("Treeview", background=C["surface"], fieldbackground=C["surface"], foreground=C["text"],
                bordercolor=C["border"], lightcolor=C["surface"], darkcolor=C["surface"], rowheight=28,
                font=(FONT, 10))
    s.map("Treeview", background=[("selected", C["accent_dim"])], foreground=[("selected", "#ffffff")])
    s.configure("Treeview.Heading", background=C["panel"], foreground=C["muted"], bordercolor=C["border"],
                lightcolor=C["panel"], darkcolor=C["panel"], relief="flat", font=(FONT, 9, "bold"), padding=(6, 5))
    s.map("Treeview.Heading", background=[("active", C["raised"])], foreground=[("active", C["text"])])

    s.configure("TNotebook", background=C["bg"], bordercolor=C["border"], lightcolor=C["bg"], darkcolor=C["bg"],
                tabmargins=(0, 0, 0, 0))
    s.configure("TNotebook.Tab", background=C["panel"], foreground=C["muted"], bordercolor=C["border"],
                lightcolor=C["panel"], darkcolor=C["panel"], padding=(16, 7), font=(FONT, 10, "bold"))
    s.map("TNotebook.Tab",
          background=[("selected", C["surface"]), ("active", C["raised"])],
          lightcolor=[("selected", C["accent"])],
          foreground=[("selected", C["accent"]), ("active", C["text"])])

    for orient in ("Vertical", "Horizontal"):
        s.configure(f"{orient}.TScrollbar", background=C["raised"], troughcolor=C["surface"],
                    bordercolor=C["surface"], lightcolor=C["raised"], darkcolor=C["raised"],
                    arrowcolor=C["muted"], gripcount=0, arrowsize=12)
        s.map(f"{orient}.TScrollbar", background=[("active", C["hover"])])
    s.configure("Horizontal.TProgressbar", background=C["accent"], troughcolor=C["surface"],
                bordercolor=C["border"], lightcolor=C["accent"], darkcolor=C["accent"])
    s.configure("TPanedwindow", background=C["bg"])
    s.configure("Sash", sashthickness=8, background=C["bg"], lightcolor=C["bg"], bordercolor=C["bg"])


def style_text(widget: tk.Text) -> None:
    widget.configure(bg=C["surface"], fg=C["text"], insertbackground=C["text"],
                     selectbackground=C["accent_dim"], selectforeground="#ffffff",
                     highlightthickness=0, borderwidth=0)


def dark_title_bar(win: tk.Misc) -> None:
    """Ask Windows 10/11 to draw this window's title bar dark (ignored elsewhere)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        on = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old Windows 10 builds)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
    except Exception:
        pass


def set_app_icon(root: tk.Tk) -> "tk.PhotoImage | None":
    """Window/taskbar icon. Returns the small logo image for the header (keep a reference)."""
    ico = resource_path(os.path.join("assets", "icon.ico"))
    if sys.platform.startswith("win") and os.path.exists(ico):
        try:
            root.iconbitmap(default=ico)
        except tk.TclError:
            pass
    try:
        big = tk.PhotoImage(master=root, file=resource_path(os.path.join("assets", "icon.png")))
        root.iconphoto(True, big)
        root._icon_ref = big  # type: ignore[attr-defined]
        return tk.PhotoImage(master=root, file=resource_path(os.path.join("assets", "icon-64.png"))).subsample(2)
    except tk.TclError:
        return None
