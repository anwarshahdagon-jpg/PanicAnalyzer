"""iPhone Panic Analyzer: desktop app (Windows) for repair technicians.

Run from source:  python main.py
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import drivers  # noqa: E402
from analyzer import Analyzer, NotAPanicLog, PanicLog, parse_file, looks_like_panic_filename  # noqa: E402
from device import DeviceWatcher, default_save_root  # noqa: E402

APP_NAME = "iPhone Panic Analyzer"
APP_VERSION = "1.0"

COLORS = {
    "bg": "#f5f6f8", "ok": "#1e8e3e", "bad": "#d93025", "warn": "#e37400", "muted": "#5f6368",
    "banner": "#fff4ce", "banner_hot": "#ffd6a5", "High": "#d93025", "Medium": "#e37400", "Low": "#5f6368",
}


def _enable_dpi_awareness() -> None:
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


class DriverDialog(tk.Toplevel):
    """Shown when Apple's drivers are missing. Offers iTunes / Apple Devices / 3uTools."""

    def __init__(self, app: "App", status: drivers.DriverStatus):
        super().__init__(app.root)
        self.app = app
        self.title("Apple drivers needed")
        self.transient(app.root)
        self.resizable(False, False)
        self._cancel = False
        pad = {"padx": 14, "pady": 4}

        ttk.Label(self, text="iPhone drivers check", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=14, pady=(14, 2))
        self.status_lbl = ttk.Label(self, text=status.summary(), foreground=COLORS["ok"] if status.ok else COLORS["bad"])
        self.status_lbl.pack(anchor="w", **pad)
        ttk.Label(self, wraplength=520, justify="left", text=(
            "This app talks to the iPhone through Apple's driver (Apple Mobile Device Service). "
            "Install ONE of these, then click 'Check again':")).pack(anchor="w", **pad)

        box = ttk.Frame(self)
        box.pack(fill="x", padx=14, pady=6)
        ttk.Button(box, text="1. Get iTunes (Microsoft Store)  [recommended]",
                   command=drivers.open_itunes_store).pack(fill="x", pady=2)
        ttk.Button(box, text="2. Get Apple Devices app (Microsoft Store, Windows 11)",
                   command=drivers.open_apple_devices_store).pack(fill="x", pady=2)
        self.dl_btn = ttk.Button(box, text="3. Download and install 3uTools (includes the drivers)",
                                 command=self._download_3u)
        self.dl_btn.pack(fill="x", pady=2)
        if status.service_installed and not status.service_running:
            ttk.Button(box, text="Start the Apple Mobile Device Service (needs admin)",
                       command=self._start_service).pack(fill="x", pady=2)

        self.progress = ttk.Progressbar(self, mode="determinate", length=520)
        self.progress_lbl = ttk.Label(self, text="", foreground=COLORS["muted"])

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=14, pady=(8, 14))
        ttk.Button(bottom, text="Check again", command=self._recheck).pack(side="left")
        ttk.Button(bottom, text="Continue (open files only)", command=self._close).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.update_idletasks()
        x = app.root.winfo_rootx() + (app.root.winfo_width() - self.winfo_width()) // 2
        y = app.root.winfo_rooty() + (app.root.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()

    def _close(self):
        self._cancel = True
        self.grab_release()
        self.destroy()

    def _recheck(self):
        self.status_lbl.config(text="Checking...", foreground=COLORS["muted"])

        def work():
            st = drivers.check()
            self.app.ui(lambda: self._show(st))
        threading.Thread(target=work, daemon=True).start()

    def _show(self, st: drivers.DriverStatus):
        if not self.winfo_exists():
            return
        self.status_lbl.config(text=st.summary(), foreground=COLORS["ok"] if st.ok else COLORS["bad"])
        self.app.set_driver_status(st)
        if st.ok:
            messagebox.showinfo(APP_NAME, "Apple drivers are working. You can plug in the iPhone now.", parent=self)
            self._close()

    def _start_service(self):
        ok = drivers.start_service()
        self._recheck()
        if not ok:
            messagebox.showwarning(APP_NAME, "The service did not start. Restart the PC or reinstall iTunes.", parent=self)

    def _download_3u(self):
        self.dl_btn.config(state="disabled")
        self.progress.pack(padx=14, pady=(4, 0))
        self.progress_lbl.pack(anchor="w", padx=14)
        self.progress_lbl.config(text="Finding the latest 3uTools...")

        def prog(done, total):
            def upd():
                if not self.winfo_exists():
                    return
                if total:
                    self.progress.config(maximum=total, value=done)
                    self.progress_lbl.config(text=f"Downloading 3uTools: {done / 1e6:.1f} / {total / 1e6:.1f} MB")
                else:
                    self.progress_lbl.config(text=f"Downloading 3uTools: {done / 1e6:.1f} MB")
            self.app.ui(upd)

        def work():
            try:
                path = drivers.download_3utools(prog, lambda: self._cancel)
            except Exception as e:
                def fail():
                    if self.winfo_exists():
                        self.dl_btn.config(state="normal")
                        self.progress_lbl.config(text=f"Download failed: {e}")
                    if messagebox.askyesno(APP_NAME, f"Download failed ({e}).\n\nOpen the 3uTools website instead?"):
                        drivers.open_uri(drivers.THREEU_HOME)
                self.app.ui(fail)
                return

            def done():
                if self.winfo_exists():
                    self.progress_lbl.config(text="Download complete. Starting the installer... "
                                                  "After it finishes, click 'Check again'.")
                try:
                    drivers.run_installer(path)
                except Exception as e:
                    messagebox.showerror(APP_NAME, f"Could not start the installer: {e}\n\nIt was saved to:\n{path}")
            self.app.ui(done)
        threading.Thread(target=work, daemon=True).start()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: "queue.Queue[tuple[str, dict]]" = queue.Queue()
        self._ui_calls: "queue.Queue" = queue.Queue()
        self.save_root = default_save_root()
        os.makedirs(self.save_root, exist_ok=True)
        try:
            self.analyzer = Analyzer()
        except Exception as e:
            messagebox.showerror(APP_NAME, f"Could not load rules.json: {e}")
            raise
        self.logs: dict[str, PanicLog] = {}       # tree item id -> parsed log
        self.devices: dict[str, dict] = {}        # serial -> info
        self.current: PanicLog | None = None
        self.current_report = ""

        root.title(f"{APP_NAME} {APP_VERSION}")
        root.geometry("1220x780")
        root.minsize(900, 560)
        self._build_ui()
        self._load_saved_logs()

        self.watcher = DeviceWatcher(self.events, self.save_root)
        self.watcher.start()
        root.after(100, self._pump)
        root.after(300, self._startup_driver_check)
        root.protocol("WM_DELETE_WINDOW", self._quit)

    # ------------------------------------------------------------------ helpers
    def ui(self, fn):
        """Run fn on the Tk thread (safe to call from worker threads)."""
        self._ui_calls.put(fn)

    def _pump(self):
        try:
            while True:
                self._ui_calls.get_nowait()()
        except queue.Empty:
            pass
        try:
            while True:
                name, payload = self.events.get_nowait()
                self._on_event(name, payload)
        except queue.Empty:
            pass
        self.root.after(100, self._pump)

    def _quit(self):
        self.watcher.stop()
        self.root.destroy()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        style = ttk.Style()
        try:
            style.theme_use("vista" if sys.platform.startswith("win") else "clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Treeview", rowheight=24)

        top = ttk.Frame(self.root, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text=APP_NAME, style="Title.TLabel").pack(side="left")
        self.device_lbl = ttk.Label(top, text="No iPhone connected", foreground=COLORS["muted"], font=("Segoe UI", 10))
        self.device_lbl.pack(side="right", padx=(16, 0))
        self.driver_lbl = ttk.Label(top, text="Checking Apple drivers...", foreground=COLORS["muted"], font=("Segoe UI", 10))
        self.driver_lbl.pack(side="right")

        self.banner = tk.Label(
            self.root, anchor="w", justify="left", bg=COLORS["banner"], padx=12, pady=8, font=("Segoe UI", 10),
            text="Before you plug in: unlock the iPhone. When it asks \"Trust This Computer?\", tap Trust and enter the "
                 "passcode. Panic logs are copied automatically as soon as the iPhone is detected (it may reboot "
                 "every ~3 minutes, so plug it in right after it boots).")
        self.banner.pack(fill="x", padx=12, pady=(2, 6))
        self.banner.bind("<Configure>", lambda e: self.banner.config(wraplength=e.width - 30))

        bar = ttk.Frame(self.root, padding=(12, 0, 12, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="Open panic log file...", command=self.open_file).pack(side="left")
        ttk.Button(bar, text="Re-read iPhone", command=self._refresh_device).pack(side="left", padx=6)
        ttk.Button(bar, text="Open saved logs folder", command=lambda: drivers.open_uri(self.save_root)).pack(side="left")
        ttk.Button(bar, text="Save report...", command=self._save_report).pack(side="left", padx=6)
        ttk.Button(bar, text="Driver setup...", command=self._driver_dialog).pack(side="right")

        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        left = ttk.Frame(paned)
        ttk.Label(left, text="Panic logs (newest first)", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 4))
        self.tree = ttk.Treeview(left, columns=("date", "device", "file"), show="headings", selectmode="browse")
        for col, w, txt in (("date", 140, "Date"), ("device", 130, "Device"), ("file", 200, "File")):
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=w, anchor="w")
        ysb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="left", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(left, weight=1)

        right = ttk.Notebook(paned)
        self.report = self._make_text(right, wrap="word", font=("Segoe UI", 10))
        self.raw = self._make_text(right, wrap="none", font=("Consolas", 9))
        right.add(self.report.master, text="  Diagnosis  ")
        right.add(self.raw.master, text="  Raw panic log  ")
        paned.add(right, weight=3)

        t = self.report
        t.tag_configure("h1", font=("Segoe UI", 14, "bold"), spacing3=6)
        t.tag_configure("h2", font=("Segoe UI", 12, "bold"), spacing1=12, spacing3=4)
        t.tag_configure("meta", foreground=COLORS["muted"])
        t.tag_configure("label", font=("Segoe UI", 10, "bold"))
        t.tag_configure("code", font=("Consolas", 9), background="#eef1f5", lmargin1=20, lmargin2=20, spacing1=2, spacing3=2)
        t.tag_configure("indent", lmargin1=20, lmargin2=38)
        for lvl in ("High", "Medium", "Low"):
            t.tag_configure(lvl, foreground="white", background=COLORS[lvl], font=("Segoe UI", 9, "bold"))

        self.statusbar = ttk.Label(self.root, text=f"Saved logs folder: {self.save_root}", foreground=COLORS["muted"],
                                   padding=(12, 2, 12, 6))
        self.statusbar.pack(fill="x")
        self._show_welcome()

    def _make_text(self, parent, **kw) -> tk.Text:
        frame = ttk.Frame(parent)
        text = tk.Text(frame, relief="flat", padx=14, pady=10, borderwidth=0, **kw)
        ys = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=ys.set)
        if kw.get("wrap") == "none":
            xs = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
            text.configure(xscrollcommand=xs.set)
            xs.pack(side="bottom", fill="x")
        ys.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)
        text.configure(state="disabled")
        return text

    def _write(self, widget: tk.Text, chunks):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for text, *tags in chunks:
            widget.insert("end", text, tuple(tags))
        widget.configure(state="disabled")
        widget.yview_moveto(0)

    def _show_welcome(self):
        self._write(self.report, [
            ("How to use\n", "h1"),
            ("1. Make sure the Apple drivers show as OK at the top right.\n", "indent"),
            ("2. Unlock the iPhone and plug it in with a good cable. Tap Trust on the iPhone when asked.\n", "indent"),
            ("3. The app copies every panic log to your PC and shows the newest one here.\n", "indent"),
            ("4. Or click 'Open panic log file...' to check a .ips / .txt file you already have.\n\n", "indent"),
            ("Saved logs go to:\n", "label"), (self.save_root + "\n", "code"),
        ])

    # ------------------------------------------------------------------ drivers
    def _startup_driver_check(self):
        def work():
            st = drivers.check()
            self.ui(lambda: self._after_driver_check(st))
        threading.Thread(target=work, daemon=True).start()

    def _after_driver_check(self, st: drivers.DriverStatus):
        self.set_driver_status(st)
        if not st.ok:
            DriverDialog(self, st)

    def set_driver_status(self, st: drivers.DriverStatus):
        self.driver_lbl.config(text=("● " if st.ok else "● ") + st.summary(),
                               foreground=COLORS["ok"] if st.ok else COLORS["bad"])

    def _driver_dialog(self):
        def work():
            st = drivers.check()
            self.ui(lambda: (self.set_driver_status(st), DriverDialog(self, st)))
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ device events
    def _on_event(self, name: str, p: dict):
        if name == "fatal":
            messagebox.showerror(APP_NAME, p["message"])
        elif name == "mux":
            if p["ok"]:
                self.driver_lbl.config(text="● Apple drivers OK", foreground=COLORS["ok"])
            else:
                self.driver_lbl.config(text="● Apple drivers not running", foreground=COLORS["bad"])
                self.device_lbl.config(text="No iPhone connected", foreground=COLORS["muted"])
        elif name == "attached":
            self.devices[p["serial"]] = {}
            self.device_lbl.config(text="iPhone detected, connecting...", foreground=COLORS["warn"])
            self._banner("iPhone detected. Unlock it and tap \"Trust\" if it asks.", hot=False)
        elif name == "trust_needed":
            self.device_lbl.config(text="Waiting for Trust on the iPhone", foreground=COLORS["warn"])
            self._banner("ACTION NEEDED: unlock the iPhone, tap \"Trust This Computer\" and enter the passcode.", hot=True)
        elif name == "unlock_needed":
            self.device_lbl.config(text="Unlock the iPhone", foreground=COLORS["warn"])
            self._banner("ACTION NEEDED: the iPhone is locked. Unlock it with the passcode, then tap \"Trust\" if asked.",
                         hot=True)
        elif name == "trusted":
            self.devices[p["serial"]] = p
            self.device_lbl.config(text=f"● {p['model']} • iOS {p['ios']} • {p['name']}", foreground=COLORS["ok"])
            self._banner("iPhone trusted. Copying panic logs...", hot=False)
        elif name == "pulling":
            self.statusbar.config(text=f"Copying panic logs to {p['folder']} ...")
        elif name == "logs":
            for f in p["files"]:
                self._add_log(f, select=False)
            if p["files"]:
                newest = max(p["files"], key=lambda f: os.path.basename(f))
                self._select_path(newest)
            if not p["partial"]:
                n, total = len(p["new"]), len(p["files"])
                msg = (f"Copied {n} new panic log(s), {total} in total, to {p['folder']}" if total
                       else "No panic logs found on this iPhone.")
                self.statusbar.config(text=msg)
                self._banner(msg + (" The newest one is shown below." if total else
                                    " If it is rebooting, wait for it to reboot once and click 'Re-read iPhone'."),
                             hot=False)
        elif name == "device_error":
            self.statusbar.config(text=p["message"])
            self._banner(p["message"], hot=True)
        elif name == "detached":
            self.devices.pop(p["serial"], None)
            if not self.devices:
                self.device_lbl.config(text="No iPhone connected", foreground=COLORS["muted"])

    def _banner(self, text: str, hot: bool):
        self.banner.config(text=text, bg=COLORS["banner_hot" if hot else "banner"],
                           font=("Segoe UI", 10, "bold" if hot else "normal"))

    def _refresh_device(self):
        if not self.devices:
            messagebox.showinfo(APP_NAME, "No iPhone is connected.")
            return
        self.watcher.refresh()
        self.statusbar.config(text="Reading the iPhone again...")

    # ------------------------------------------------------------------ logs list
    def _load_saved_logs(self):
        if not os.path.isdir(self.save_root):
            return
        for dirpath, _, files in os.walk(self.save_root):
            for fn in files:
                if looks_like_panic_filename(fn) and not fn.endswith(".part"):
                    self._add_log(os.path.join(dirpath, fn), select=False, quiet=True)

    def _item_for(self, path: str):
        for iid, log in self.logs.items():
            if os.path.normcase(os.path.abspath(log.path)) == os.path.normcase(os.path.abspath(path)):
                return iid
        return None

    def _add_log(self, path: str, select: bool = True, quiet: bool = False) -> bool:
        existing = self._item_for(path)
        if existing:
            if select:
                self.tree.selection_set(existing)
                self.tree.see(existing)
            return True
        try:
            log = parse_file(path)
        except NotAPanicLog as e:
            if not quiet:
                messagebox.showwarning(APP_NAME, f"Not a panic log.\n\n{os.path.basename(path)}\n\n{e}")
            return False
        except Exception as e:
            if not quiet:
                messagebox.showerror(APP_NAME, f"Could not read the file:\n{e}")
            return False
        date = (log.timestamp or datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"))[:19]
        # keep the list sorted newest first
        index = 0
        for i, iid in enumerate(self.tree.get_children()):
            if date >= self.tree.set(iid, "date"):
                index = i
                break
            index = i + 1
        iid = self.tree.insert("", index, values=(date, log.model, os.path.basename(path)))
        self.logs[iid] = log
        if select:
            self.tree.selection_set(iid)
            self.tree.see(iid)
        return True

    def _select_path(self, path: str):
        iid = self._item_for(path)
        if iid:
            self.tree.selection_set(iid)
            self.tree.see(iid)

    def _on_select(self, _evt=None):
        sel = self.tree.selection()
        if sel and sel[0] in self.logs:
            self.show(self.logs[sel[0]])

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open a panic log",
            filetypes=[("Panic logs", "*.ips *.txt *.log *.panic"), ("All files", "*.*")])
        if path:
            self._add_log(path, select=True)

    # ------------------------------------------------------------------ report
    def show(self, log: PanicLog):
        self.current = log
        findings = self.analyzer.analyze(log)
        chunks = [
            (f"{log.model}" + (f"  ({log.product})" if log.product and log.product != log.model else "") + "\n", "h1"),
            (f"iOS: {log.os_version or 'unknown'}    Date: {log.timestamp or 'unknown'}\n", "meta"),
            (f"File: {log.path}\n", "meta"),
            ("Panic: ", "label"), (log.headline + "\n", "code"),
        ]
        top = findings[0]
        chunks += [("\nMost likely: ", "h2"), (top.title + "\n", "h2"),
                   ("Part to check first: ", "label"), (top.component + "\n", "")]

        report_lines = [f"{APP_NAME} report", f"Model: {log.model} ({log.product})", f"iOS: {log.os_version}",
                        f"Date: {log.timestamp}", f"File: {log.path}", f"Panic: {log.headline}", ""]

        for n, f in enumerate(findings, 1):
            chunks += [
                (f"\n{n}. ", "h2"), (f" {f.confidence} ", f.confidence), (f"  {f.title}\n", "h2"),
                ("Part: ", "label"), (f.component + "\n", ""),
                ("Proof from the log:\n", "label"), (f.evidence + "\n", "code"),
                ("Why: ", "label"), (f.why + "\n", ""),
                ("Repair steps (in this order):\n", "label"),
            ]
            for i, s in enumerate(f.steps, 1):
                chunks.append((f"{i}. {s}\n", "indent"))
            report_lines += [f"{n}. [{f.confidence}] {f.title}", f"   Part: {f.component}", f"   Proof: {f.evidence}",
                             f"   Why: {f.why}", "   Steps:"] + [f"     {i}. {s}" for i, s in enumerate(f.steps, 1)] + [""]

        chunks.append(("\nThese are likely causes based on the codes in the log. Always confirm with measurements "
                       "before replacing parts.\n", "meta"))
        self._write(self.report, chunks)
        self._write(self.raw, [(log.panic_string + "\n\n" + "-" * 80 + "\nFull file:\n" + log.raw,)])
        self.current_report = "\n".join(report_lines)

    def _save_report(self):
        if not self.current:
            messagebox.showinfo(APP_NAME, "Open or select a panic log first.")
            return
        base = os.path.splitext(os.path.basename(self.current.path))[0]
        path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=f"{base}-report.txt",
                                            filetypes=[("Text", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self.current_report + "\n\n----- Panic -----\n" + self.current.panic_string)
            self.statusbar.config(text=f"Report saved to {path}")


def main():
    _enable_dpi_awareness()
    root = tk.Tk()
    app = App(root)
    # allow "Open with" / dragging a file onto the .exe
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        root.after(500, lambda: app._add_log(sys.argv[1], select=True))
    root.mainloop()


if __name__ == "__main__":
    main()
