"""Background worker that watches for iPhones over USB and pulls their panic logs.

Runs an asyncio loop in a separate thread and reports to the GUI through a queue.Queue of
(event_name, payload_dict) tuples, so the GUI never blocks.
"""
from __future__ import annotations

import asyncio
import os
import queue
import re
import threading
import traceback
from typing import Optional

from analyzer import looks_like_panic_filename, model_name

try:
    from pymobiledevice3 import usbmux
    from pymobiledevice3.exceptions import (
        ConnectionFailedToUsbmuxdError, PairingDialogResponsePendingError, PasswordRequiredError,
        UserDeniedPairingError, NotTrustedError, PasscodeRequiredError,
    )
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.crash_reports import CrashReportsManager
    PMD3_ERROR = None
except Exception as e:  # pragma: no cover - shown in the GUI
    PMD3_ERROR = f"pymobiledevice3 could not be loaded: {e}"

POLL_SECONDS = 1.5
TRUST_WAIT_SECONDS = 180


def default_save_root() -> str:
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "iPhone Panic Logs")


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .") or "device"


class DeviceWatcher:
    def __init__(self, events: "queue.Queue[tuple[str, dict]]", save_root: Optional[str] = None):
        self.events = events
        self.save_root = save_root or default_save_root()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop = False
        self._known: set[str] = set()        # serials currently attached
        self._busy: set[str] = set()         # serials being processed
        self._refresh: set[str] = set()      # serials the user asked to re-read

    # ---- public API (called from the GUI thread)
    def start(self) -> None:
        if PMD3_ERROR:
            self._emit("fatal", message=PMD3_ERROR)
            return
        self._thread = threading.Thread(target=self._run, name="DeviceWatcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True

    def refresh(self) -> None:
        """Pull logs again from every connected device."""
        self._refresh.update(self._known)

    # ---- internals
    def _emit(self, _event: str, **payload) -> None:
        self.events.put((_event, payload))

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._main())
        except Exception as e:
            self._emit("fatal", message=f"Device watcher stopped: {e}")

    async def _main(self) -> None:
        mux_ok: Optional[bool] = None
        while not self._stop:
            try:
                devices = await usbmux.list_devices()
                if mux_ok is not True:
                    mux_ok = True
                    self._emit("mux", ok=True)
            except Exception:
                if mux_ok is not False:
                    mux_ok = False
                    self._emit("mux", ok=False)
                self._known.clear()
                await asyncio.sleep(3)
                continue

            usb = {d.serial for d in devices if getattr(d, "is_usb", True)}
            for serial in sorted(usb - self._known):
                self._known.add(serial)
                self._emit("attached", serial=serial)
                self._spawn(serial)
            for serial in sorted(self._known - usb):
                self._known.discard(serial)
                self._emit("detached", serial=serial)
            for serial in list(self._refresh):
                self._refresh.discard(serial)
                if serial in self._known:
                    self._spawn(serial)
            await asyncio.sleep(POLL_SECONDS)

    def _spawn(self, serial: str) -> None:
        if serial in self._busy:
            return
        self._busy.add(serial)
        asyncio.get_running_loop().create_task(self._handle(serial))

    async def _connect(self, serial: str):
        """Connect to lockdown, walking the user through 'Trust This Computer' if needed."""
        try:
            return await create_using_usbmux(serial=serial, autopair=True, pair_timeout=0)
        except PairingDialogResponsePendingError:
            self._emit("trust_needed", serial=serial)
        except PasswordRequiredError:
            self._emit("unlock_needed", serial=serial)
        # wait for the user to unlock and tap Trust
        deadline = asyncio.get_running_loop().time() + TRUST_WAIT_SECONDS
        while asyncio.get_running_loop().time() < deadline and serial in self._known and not self._stop:
            try:
                return await create_using_usbmux(serial=serial, autopair=True, pair_timeout=3)
            except PairingDialogResponsePendingError:
                self._emit("trust_needed", serial=serial)
            except PasswordRequiredError:
                self._emit("unlock_needed", serial=serial)
            await asyncio.sleep(1)
        raise TimeoutError("The iPhone was not trusted in time. Unplug and plug it in again.")

    async def _handle(self, serial: str) -> None:
        lockdown = None
        try:
            lockdown = await self._connect(serial)
            v = lockdown.all_values or {}
            product = v.get("ProductType") or lockdown.product_type
            info = {
                "serial": serial,
                "name": v.get("DeviceName") or "iPhone",
                "product": product,
                "model": model_name(product),
                "ios": v.get("ProductVersion"),
                "build": v.get("BuildVersion"),
                "sn": v.get("SerialNumber"),
            }
            self._emit("trusted", **info)

            folder = os.path.join(self.save_root, _safe(f"{info['model']} - {info['name']} - {(info['sn'] or serial)[-6:]}"))
            os.makedirs(folder, exist_ok=True)
            self._emit("pulling", serial=serial, folder=folder)

            saved, new = [], []
            async with CrashReportsManager(lockdown) as crm:
                try:
                    await asyncio.wait_for(crm.flush(), timeout=8)
                except Exception:
                    pass  # flushing is a nice-to-have
                entries = await crm.ls("/", depth=2)
                panics = [p for p in entries if looks_like_panic_filename(os.path.basename(p))]
                # newest first: the phone may reboot in ~3 minutes, so grab the latest ones first
                panics.sort(key=lambda p: os.path.basename(p), reverse=True)
                for i, remote in enumerate(panics):
                    local = os.path.join(folder, os.path.basename(remote))
                    if not os.path.exists(local):
                        try:
                            data = await crm.afc.get_file_contents(remote)
                        except Exception:
                            continue  # a folder or unreadable entry
                        with open(local + ".part", "wb") as f:
                            f.write(data)
                        os.replace(local + ".part", local)
                        new.append(local)
                        if i == 0:
                            # show the newest log right away, before the rest finish copying
                            self._emit("logs", serial=serial, folder=folder, files=[local], new=[local], partial=True)
                    saved.append(local)
            self._emit("logs", serial=serial, folder=folder, files=saved, new=new, partial=False)
        except TimeoutError as e:
            self._emit("device_error", serial=serial, message=str(e))
        except UserDeniedPairingError:
            self._emit("device_error", serial=serial,
                       message="You tapped 'Don't Trust' on the iPhone. Unplug it, plug it back in and tap 'Trust'.")
        except (NotTrustedError, PasscodeRequiredError):
            self._emit("device_error", serial=serial,
                       message="The iPhone does not trust this PC yet. Unlock it and tap 'Trust'.")
        except ConnectionFailedToUsbmuxdError:
            self._emit("mux", ok=False)
        except Exception as e:
            if serial in self._known:
                self._emit("device_error", serial=serial,
                           message=f"Could not read the iPhone: {type(e).__name__}: {e}",
                           detail=traceback.format_exc())
            # if the device rebooted mid-copy it will be read again when it comes back
        finally:
            self._busy.discard(serial)
            if lockdown is not None:
                try:
                    await lockdown.close()
                except Exception:
                    pass
