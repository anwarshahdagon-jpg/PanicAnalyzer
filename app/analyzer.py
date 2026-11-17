"""Panic log parsing and diagnosis.

Works with:
  * iOS 15+ .ips panic files (a JSON header line followed by a JSON body with "panicString")
  * older .ips panic files (JSON header + JSON body with "description" or plain text)
  * plain text copies of a panic (e.g. copied out of 3uTools into a .txt file)
  * files with no extension
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional


def resource_path(name: str) -> str:
    """Path to a bundled file, both when run from source and from a PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def rules_path() -> str:
    """Prefer a rules.json next to the .exe (so the user can edit it), else the bundled one."""
    if getattr(sys, "frozen", False):
        beside_exe = os.path.join(os.path.dirname(sys.executable), "rules.json")
        if os.path.exists(beside_exe):
            return beside_exe
    return resource_path("rules.json")


_FALLBACK_MODELS = {
    "iPhone9,1": "iPhone 7", "iPhone9,3": "iPhone 7", "iPhone9,2": "iPhone 7 Plus", "iPhone9,4": "iPhone 7 Plus",
    "iPhone10,1": "iPhone 8", "iPhone10,4": "iPhone 8", "iPhone10,2": "iPhone 8 Plus", "iPhone10,5": "iPhone 8 Plus",
    "iPhone10,3": "iPhone X", "iPhone10,6": "iPhone X", "iPhone11,2": "iPhone XS", "iPhone11,4": "iPhone XS Max",
    "iPhone11,6": "iPhone XS Max", "iPhone11,8": "iPhone XR", "iPhone12,1": "iPhone 11", "iPhone12,3": "iPhone 11 Pro",
    "iPhone12,5": "iPhone 11 Pro Max", "iPhone12,8": "iPhone SE (2nd gen)", "iPhone13,1": "iPhone 12 mini",
    "iPhone13,2": "iPhone 12", "iPhone13,3": "iPhone 12 Pro", "iPhone13,4": "iPhone 12 Pro Max",
    "iPhone14,4": "iPhone 13 mini", "iPhone14,5": "iPhone 13", "iPhone14,2": "iPhone 13 Pro",
    "iPhone14,3": "iPhone 13 Pro Max", "iPhone14,6": "iPhone SE (3rd gen)", "iPhone14,7": "iPhone 14",
    "iPhone14,8": "iPhone 14 Plus", "iPhone15,2": "iPhone 14 Pro", "iPhone15,3": "iPhone 14 Pro Max",
    "iPhone15,4": "iPhone 15", "iPhone15,5": "iPhone 15 Plus", "iPhone16,1": "iPhone 15 Pro",
    "iPhone16,2": "iPhone 15 Pro Max", "iPhone17,3": "iPhone 16", "iPhone17,4": "iPhone 16 Plus",
    "iPhone17,1": "iPhone 16 Pro", "iPhone17,2": "iPhone 16 Pro Max", "iPhone17,5": "iPhone 16e",
}


def model_name(product: Optional[str]) -> str:
    if not product:
        return "Unknown model"
    try:
        from pymobiledevice3.irecv_devices import IRECV_DEVICES  # type: ignore
        for d in IRECV_DEVICES:
            if d.product_type == product:
                return d.display_name
    except Exception:
        pass
    return _FALLBACK_MODELS.get(product, product)


# --------------------------------------------------------------------------- parsing

@dataclass
class PanicLog:
    path: str
    raw: str
    panic_string: str
    product: Optional[str] = None
    os_version: Optional[str] = None
    timestamp: Optional[str] = None
    incident: Optional[str] = None
    kind: str = "panic-full"

    @property
    def model(self) -> str:
        return model_name(self.product)

    @property
    def headline(self) -> str:
        for line in self.panic_string.splitlines():
            line = line.strip()
            if line:
                return line[:300]
        return "(empty panic string)"


class NotAPanicLog(Exception):
    pass


_PANIC_MARKERS = re.compile(
    r"panic\(cpu \d+ caller|Debugger message: panic|\"bug_type\"\s*:\s*\"210\"|panicString|"
    r"Missing sensor\(s\)|userspace watchdog timeout|Unexpected SoC \(JTAG\) watchdog|AOP PANIC|SEP Panic",
    re.IGNORECASE,
)


def _json_objects(text: str) -> list[dict]:
    """Return every top-level JSON object found in the text (an .ips file holds two)."""
    objs = []
    dec = json.JSONDecoder()
    i = 0
    n = len(text)
    while i < n:
        j = text.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(text, j)
        except ValueError:
            i = j + 1
            # only try object starts at line beginnings after the first failure, to stay fast
            nl = text.find("\n", j)
            if nl < 0:
                break
            i = nl + 1
            continue
        if isinstance(obj, dict):
            objs.append(obj)
        i = end
    return objs


def parse_text(text: str, path: str = "") -> PanicLog:
    text = text.lstrip("﻿")
    if not _PANIC_MARKERS.search(text):
        raise NotAPanicLog("This file does not look like a panic log.")

    product = os_version = timestamp = incident = None
    panic_string = None
    bug_type = None
    kind = "panic-full"

    for obj in _json_objects(text):
        bug_type = bug_type or obj.get("bug_type")
        product = product or obj.get("product")
        timestamp = timestamp or obj.get("timestamp") or obj.get("date")
        incident = incident or obj.get("incident_id") or obj.get("incident")
        osv = obj.get("os_version") or obj.get("build")
        if osv and not os_version:
            os_version = osv
        ps = obj.get("panicString") or obj.get("description")
        if isinstance(ps, str) and ps.strip() and not panic_string:
            panic_string = ps
        if obj.get("panicFlags") is not None or "macOSPanicString" in obj:
            kind = "panic-full"

    if bug_type is not None and str(bug_type) not in ("210", "288", "409") and not panic_string:
        # 210 = panic-full, 288/409 = stackshot style panic reports
        if not re.search(r"panic\(cpu \d+", text):
            raise NotAPanicLog(f"This is a crash report of type {bug_type}, not a panic log.")

    if not panic_string:
        # plain text panic, or something JSON could not decode: use the text from "panic(" on
        m = re.search(r"panic\(cpu \d+ caller", text)
        panic_string = text[m.start():] if m else text
        # undo JSON escaping if the text was copied from inside a JSON string
        if "\\n" in panic_string and panic_string.count("\n") < 3:
            panic_string = panic_string.replace("\\n", "\n").replace('\\"', '"').replace("\\t", "\t")

    if not product:
        m = re.search(r"\b((?:iPhone|iPad|iPod)\d+,\d+)\b", text)
        product = m.group(1) if m else None
    if not os_version:
        m = re.search(r"(?:iPhone OS|iOS)\s*[\d.]+\s*\(\w+\)", text) or re.search(r"OS version:\s*(\w+)", panic_string)
        os_version = m.group(0) if m else None
    if not timestamp:
        m = re.search(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", text)
        timestamp = m.group(0) if m else None

    if path and os.path.basename(path).lower().startswith("panic-base"):
        kind = "panic-base"
    return PanicLog(path=path, raw=text, panic_string=panic_string, product=product,
                    os_version=os_version, timestamp=timestamp, incident=incident, kind=kind)


def parse_file(path: str) -> PanicLog:
    size = os.path.getsize(path)
    if size == 0:
        raise NotAPanicLog("The file is empty.")
    if size > 50 * 1024 * 1024:
        raise NotAPanicLog("The file is too large to be a panic log.")
    with open(path, "rb") as f:
        data = f.read()
    if b"\x00" in data[:4096] and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise NotAPanicLog("This is a binary file, not a panic log.")
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    return parse_text(text, path)


# --------------------------------------------------------------------------- diagnosis

@dataclass
class Finding:
    title: str
    component: str
    confidence: str  # High / Medium / Low
    evidence: str     # the exact text from the log
    why: str          # explanation of why this points at the part
    steps: list[str] = field(default_factory=list)

    @property
    def rank(self) -> int:
        return {"High": 0, "Medium": 1, "Low": 2}.get(self.confidence, 3)


class Analyzer:
    def __init__(self, rules_file: Optional[str] = None):
        with open(rules_file or rules_path(), "r", encoding="utf-8") as f:
            self.kb = json.load(f)
        self.sensors = {k.upper(): v for k, v in self.kb.get("sensors", {}).items()}
        self._rules = []
        for r in self.kb.get("rules", []):
            pats = [re.compile(p, re.IGNORECASE) for p in r.get("patterns", [])]
            self._rules.append((r, pats))

    # ---- helpers
    @staticmethod
    def _line_of(text: str, start: int, end: int) -> str:
        ls = text.rfind("\n", 0, start) + 1
        le = text.find("\n", end)
        line = text[ls: le if le >= 0 else len(text)].strip()
        return line if len(line) <= 400 else line[:400] + "..."

    def _sensor_location(self, info: dict, product: Optional[str]) -> str:
        for loc in info.get("locations", []):
            if product and any(product.startswith(m) for m in loc.get("models", [])):
                return loc["location"]
        return info.get("location", "")

    # ---- main entry
    def analyze(self, log: PanicLog) -> list[Finding]:
        ps = log.panic_string
        findings: list[Finding] = []

        # 1. Missing sensors: the most useful line in most iPhone panics
        missing: list[tuple[str, str]] = []
        for m in re.finditer(r"Missing sensor\(s\):\s*([A-Za-z0-9_ ,]+)", ps):
            for code in re.split(r"[\s,]+", m.group(1).strip()):
                if code and code.upper() not in [c for c, _ in missing]:
                    missing.append((code.upper(), self._line_of(ps, m.start(), m.end())))
        for code, line in missing:
            info = self.sensors.get(code)
            known = info is not None
            info = info or self.kb.get("unknown_sensor", {})
            loc = self._sensor_location(info, log.product)
            name = info.get("name", "Sensor")
            why = (f"The log says sensor {code} is missing. {code} = {name}. "
                   f"Location: {loc}. iOS cannot read this sensor, so the thermal monitor stops "
                   f"checking in and the phone reboots about every 3 minutes.")
            if not known:
                why = (f"The log says sensor {code} is missing. This code is not in the rules file yet. "
                       f"{loc}")
            findings.append(Finding(
                title=f"Missing sensor {code}: {name}",
                component=loc.split("(")[0].strip() or name,
                confidence="High" if known else "Medium",
                evidence=line, why=why, steps=list(info.get("steps", [])),
            ))
        if len(missing) >= 3:
            findings.append(Finding(
                title="Several sensors missing at once",
                component="Board-level (shared power / data line, interposer)",
                confidence="Medium",
                evidence=", ".join(c for c, _ in missing),
                why="When several sensors on different flexes go missing together, the cause is often a shared "
                    "power rail or data line on the board (or the interposer on stacked boards) rather than each flex.",
                steps=["Check the shared power rails that feed these sensors.",
                       "On stacked boards check the interposer.",
                       "Then replace flexes only if the board checks out."],
            ))

        # 2. Userspace watchdog (which daemon stopped checking in)
        for m in re.finditer(r"no successful checkins from ([\w.\-]+)", ps):
            daemon = m.group(1)
            short = daemon.split(".")[-1]
            info = self.kb.get("watchdog_daemons", {}).get(daemon) or self.kb.get("watchdog_daemons", {}).get(short)
            line = self._line_of(ps, m.start(), m.end())
            if info:
                if short == "thermalmonitord" and missing:
                    continue  # already explained by the missing sensor finding
                findings.append(Finding(
                    title=f"Watchdog timeout: {short} stopped responding",
                    component=info["component"], confidence="Medium", evidence=line,
                    why=info["why"], steps=list(info["steps"])))
            else:
                findings.append(Finding(
                    title=f"Watchdog timeout: {short} stopped responding",
                    component="Unknown (service: " + daemon + ")", confidence="Low", evidence=line,
                    why=f"The system service {daemon} stopped responding and the watchdog rebooted the phone. "
                        "This service is not in the rules file yet.",
                    steps=["Restore iOS to rule out software.",
                           "Look up what hardware this service talks to and test that part."]))

        # 3. Pattern rules
        for rule, pats in self._rules:
            for p in pats:
                m = p.search(ps)
                if not m:
                    continue
                groups = {f"g{i}": (g or "") for i, g in enumerate(m.groups(), start=1)}
                fmt = lambda s: _safe_format(s, groups)  # noqa: E731
                findings.append(Finding(
                    title=fmt(rule.get("title", rule.get("id", "Rule"))),
                    component=fmt(rule.get("component", "")),
                    confidence=rule.get("confidence", "Low"),
                    evidence=self._line_of(ps, m.start(), m.end()),
                    why=fmt(rule.get("why", "")),
                    steps=[fmt(s) for s in rule.get("steps", [])]))
                break

        if not findings:
            findings.append(Finding(
                title="No known hardware pattern found",
                component="Unknown",
                confidence="Low",
                evidence=log.headline,
                why="None of the known codes in the rules file matched this panic. It may be software, or a code "
                    "that is not in the rules file yet.",
                steps=["Update iOS, or back up and restore the phone.",
                       "If it keeps panicking, compare several panic logs to find a repeating line.",
                       "Add the repeating code to rules.json so the app recognises it next time."]))

        findings.sort(key=lambda f: f.rank)
        return findings


def _safe_format(s: str, groups: dict) -> str:
    for k, v in groups.items():
        s = s.replace("{" + k + "}", v)
    return s


def looks_like_panic_filename(name: str) -> bool:
    n = name.lower()
    return "panic" in n and not n.endswith((".synced", ".plist"))
