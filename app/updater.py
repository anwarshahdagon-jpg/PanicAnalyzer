"""Checks GitHub Releases for a newer version and installs it.

How a release reaches users:
  1. Push a tag such as v1.2 (or publish a release on GitHub).
  2. GitHub Actions builds iPhonePanicAnalyzer.exe and attaches it to the release.
  3. On start, the app asks GitHub for the latest release. If its version is newer,
     the user is offered the update; the new exe is downloaded, checked and swapped in
     by a small helper script after the app closes, then the app starts again.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

REPO = "anwarshahdagon-jpg/PanicAnalyzer"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
EXE_ASSET = "iPhonePanicAnalyzer.exe"
USER_AGENT = "iPhonePanicAnalyzer-updater"


@dataclass
class Release:
    version: str          # "1.2"
    tag: str              # "v1.2"
    notes: str
    page_url: str
    exe_url: Optional[str]
    exe_size: int = 0
    exe_sha256: Optional[str] = None


def parse_version(text: str) -> tuple[int, ...]:
    """'v1.2.3' -> (1, 2, 3). Anything after the numbers (e.g. '-beta') is ignored."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", text or "")
    if not m:
        return (0,)
    parts = [int(p) for p in m.group(1).split(".")]
    while len(parts) > 1 and parts[-1] == 0:   # 1.2.0 == 1.2
        parts.pop()
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def release_from_json(data: dict) -> Release:
    tag = data.get("tag_name", "")
    exe = next((a for a in data.get("assets", []) if a.get("name", "").lower() == EXE_ASSET.lower()), None)
    sha = None
    if exe and str(exe.get("digest", "")).startswith("sha256:"):
        sha = exe["digest"].split(":", 1)[1].lower()
    return Release(
        version=".".join(str(p) for p in parse_version(tag)),
        tag=tag,
        notes=(data.get("body") or "").strip(),
        page_url=data.get("html_url") or RELEASES_PAGE,
        exe_url=exe.get("browser_download_url") if exe else None,
        exe_size=int(exe.get("size") or 0) if exe else 0,
        exe_sha256=sha,
    )


def fetch_latest(timeout: float = 8) -> Release:
    req = urllib.request.Request(LATEST_URL, headers={"User-Agent": USER_AGENT,
                                                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return release_from_json(json.load(r))


def check(current: str) -> Optional[Release]:
    """Return the latest release if it is newer than `current`, else None. Raises on network errors."""
    rel = fetch_latest()
    return rel if is_newer(rel.tag, current) else None


# --------------------------------------------------------------------------- settings (skip a version)

def _settings_file() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "iPhonePanicAnalyzer", "settings.json")


def load_settings() -> dict:
    try:
        with open(_settings_file(), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    path = _settings_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


# --------------------------------------------------------------------------- download + install

def can_self_update() -> bool:
    """Only the packaged Windows exe can replace itself; from source we just open the releases page."""
    return bool(getattr(sys, "frozen", False)) and sys.platform.startswith("win")


def download(rel: Release, progress: Callable[[int, int], None],
             cancelled: Callable[[], bool] = lambda: False) -> str:
    """Download the release exe to the temp folder, verify it, and return its path."""
    if not rel.exe_url:
        raise RuntimeError(f"Release {rel.tag} has no {EXE_ASSET} attached yet. Try again in a few minutes.")
    dest = os.path.join(tempfile.gettempdir(), f"iPhonePanicAnalyzer-{rel.version}.exe")
    req = urllib.request.Request(rel.exe_url, headers={"User-Agent": USER_AGENT})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=30) as r, open(dest + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or rel.exe_size or 0)
        done = 0
        while True:
            if cancelled():
                raise RuntimeError("Cancelled")
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            progress(done, total)
    if rel.exe_size and done != rel.exe_size:
        os.remove(dest + ".part")
        raise RuntimeError(f"Download incomplete ({done} of {rel.exe_size} bytes). Please try again.")
    if rel.exe_sha256 and h.hexdigest() != rel.exe_sha256:
        os.remove(dest + ".part")
        raise RuntimeError("The downloaded file failed its checksum. Please try again.")
    with open(dest + ".part", "rb") as f:
        if f.read(2) != b"MZ":
            os.remove(dest + ".part")
            raise RuntimeError("The downloaded file is not a Windows program.")
    os.replace(dest + ".part", dest)
    return dest


_SWAP_SCRIPT = r"""@echo off
REM Waits for iPhone Panic Analyzer to close, swaps in the new exe, and starts it again.
set "PID={pid}"
set "NEW={new}"
set "TARGET={target}"
:wait
tasklist /FI "PID eq %PID%" 2>nul | find "%PID%" >nul && (timeout /t 1 /nobreak >nul & goto wait)
set /a tries=0
:copy
copy /y "%NEW%" "%TARGET%" >nul 2>nul && goto done
set /a tries+=1
if %tries% geq 20 goto failed
timeout /t 1 /nobreak >nul
goto copy
:done
del "%NEW%" >nul 2>nul
start "" "%TARGET%"
(goto) 2>nul & del "%~f0"
:failed
start "" "%TARGET%"
(goto) 2>nul & del "%~f0"
"""


def install_and_restart(new_exe: str) -> None:
    """Start the helper that replaces this exe once the app exits. The caller must then quit the app."""
    target = sys.executable
    script = os.path.join(tempfile.gettempdir(), "iPhonePanicAnalyzer-update.bat")
    with open(script, "w", encoding="ascii", errors="replace") as f:
        f.write(_SWAP_SCRIPT.format(pid=os.getpid(), new=new_exe, target=target))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(["cmd.exe", "/c", script], creationflags=flags, close_fds=True)
