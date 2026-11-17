"""Checks for Apple's iPhone drivers on Windows and helps the user install them.

The app talks to iPhones through "Apple Mobile Device Service" (usbmuxd), which listens on
127.0.0.1:27015. It is installed by iTunes (Microsoft Store), the Apple Devices app, or 3uTools.
"""
from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

USBMUXD_ADDR = ("127.0.0.1", 27015)
SERVICE_NAME = "Apple Mobile Device Service"

ITUNES_STORE_URI = "ms-windows-store://pdp/?productid=9PB2MZ1ZMB1S"
ITUNES_STORE_WEB = "https://apps.microsoft.com/detail/9pb2mz1zmb1s"
APPLE_DEVICES_STORE_URI = "ms-windows-store://pdp/?productid=9NP83LWLPZ9K"
THREEU_HOME = "https://www.3u.com/"
# Fallback if the 3u.com page can't be read. The app looks up the newest link first.
THREEU_FALLBACK_X64 = "https://dl.3u.com/update/v900/dl/3uTools_v9.13.013_Setup_x64.exe"
THREEU_FALLBACK_X86 = "https://dl.3u.com/update/v900/dl/3uTools_v9.13.013_Setup_x86.exe"

IS_WINDOWS = sys.platform.startswith("win")
_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW


@dataclass
class DriverStatus:
    service_running: bool     # usbmuxd reachable: everything works
    service_installed: bool   # the Windows service exists (may be stopped)
    itunes_store: bool
    apple_devices: bool
    threeu: bool

    @property
    def ok(self) -> bool:
        return self.service_running

    def summary(self) -> str:
        if self.service_running:
            src = [n for n, v in (("iTunes", self.itunes_store), ("Apple Devices", self.apple_devices),
                                  ("3uTools", self.threeu)) if v]
            return "Apple drivers OK" + (f" ({', '.join(src)})" if src else "")
        if self.service_installed:
            return "Apple Mobile Device Service is installed but not running"
        return "Apple drivers are not installed"


def usbmuxd_reachable(timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection(USBMUXD_ADDR, timeout=timeout):
            return True
    except OSError:
        return False


def _run(cmd: list[str], timeout: float = 8) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=_NO_WINDOW)
        return (out.stdout or "") + (out.stderr or "")
    except Exception:
        return ""


def _service_installed() -> bool:
    if not IS_WINDOWS:
        return False
    out = _run(["sc", "query", SERVICE_NAME])
    return "SERVICE_NAME" in out or "STATE" in out


def _appx_installed(pattern: str) -> bool:
    if not IS_WINDOWS:
        return False
    out = _run(["powershell", "-NoProfile", "-Command",
                f"Get-AppxPackage -Name '{pattern}' | Select-Object -ExpandProperty Name"], timeout=15)
    return bool(out.strip())


def _threeu_installed() -> bool:
    if not IS_WINDOWS:
        return False
    candidates = [
        os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), "3uTools"),
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "3uTools"),
        r"C:\3uTools",
    ]
    if any(os.path.isdir(p) for p in candidates):
        return True
    out = _run(["reg", "query", r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "/s", "/f", "3uTools"])
    return "3uTools" in out


def check() -> DriverStatus:
    running = usbmuxd_reachable()
    return DriverStatus(
        service_running=running,
        service_installed=running or _service_installed(),
        itunes_store=_appx_installed("AppleInc.iTunes"),
        apple_devices=_appx_installed("AppleInc.AppleDevices"),
        threeu=_threeu_installed(),
    )


def start_service() -> bool:
    """Try to start the Apple service (asks for admin rights through UAC)."""
    if not IS_WINDOWS:
        return False
    _run(["powershell", "-NoProfile", "-Command",
          f"Start-Process sc.exe -ArgumentList 'start \"{SERVICE_NAME}\"' -Verb RunAs -WindowStyle Hidden"], timeout=30)
    return usbmuxd_reachable(3)


def open_uri(uri: str) -> None:
    if IS_WINDOWS:
        os.startfile(uri)  # type: ignore[attr-defined]
    else:
        import webbrowser
        webbrowser.open(uri)


def open_itunes_store() -> None:
    try:
        open_uri(ITUNES_STORE_URI)
    except Exception:
        open_uri(ITUNES_STORE_WEB)


def open_apple_devices_store() -> None:
    open_uri(APPLE_DEVICES_STORE_URI)


def _is_64bit_windows() -> bool:
    return os.environ.get("PROCESSOR_ARCHITECTURE", "").endswith("64") or \
        os.environ.get("PROCESSOR_ARCHITEW6432", "").endswith("64") or sys.maxsize > 2 ** 32


def find_3utools_url() -> str:
    """Read 3u.com to find the newest installer link; fall back to a known one."""
    want = "x64" if _is_64bit_windows() else "x86"
    try:
        req = urllib.request.Request(THREEU_HOME, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "replace")
        links = re.findall(r"https?://dl\.3u\.com/[^\"'\s<>]+?Setup_" + want + r"\.exe", html)
        if links:
            return links[0]
    except Exception:
        pass
    return THREEU_FALLBACK_X64 if want == "x64" else THREEU_FALLBACK_X86


def download_3utools(progress: Callable[[int, int], None], cancelled: Callable[[], bool] = lambda: False) -> str:
    """Download the 3uTools installer to the temp folder and return its path."""
    url = find_3utools_url()
    dest = os.path.join(tempfile.gettempdir(), os.path.basename(url.split("?")[0]) or "3uTools_Setup.exe")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r, open(dest + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancelled():
                raise RuntimeError("Download cancelled")
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            progress(done, total)
    if os.path.exists(dest):
        os.remove(dest)
    os.replace(dest + ".part", dest)
    return dest


def run_installer(path: str) -> None:
    open_uri(path)
