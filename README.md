<p align="center"><img src="logo.png" width="128" alt="iPhone Panic Analyzer logo"></p>

# iPhone Panic Analyzer

A Windows desktop app for phone repair technicians. Plug in an iPhone that keeps rebooting: the app copies its panic logs to the PC, points to the part that is most likely at fault, quotes the line from the log that proves it, and lists repair steps from cheapest to most involved.

## What it does

- **Checks the Apple drivers on start.** If they are missing, it offers iTunes (Microsoft Store), the Apple Devices app (Windows 11) or a one-click 3uTools download and install.
- **Tells you to trust the PC.** A banner asks you to unlock the iPhone and tap *Trust This Computer*, and turns orange when the phone is waiting for you.
- **Detects the iPhone automatically** and copies every panic log (`panic-full-*.ips`, including the `Retired` folder) to `Documents\iPhone Panic Logs\<model> - <name> - <serial>`. It copies the newest log first because a panicking phone reboots about every 3 minutes. When the phone comes back after a reboot it is read again and only new logs are copied.
- **Shows the newest panic** with:
  - the most likely faulty part,
  - **proof**: the exact line from the log and what it means (for example `Missing sensor(s): PRS0` means the barometer, which sits on the charging port flex),
  - **repair steps** in order (for example: fit a good-quality charging flex, then clean the connector, then check the connector in diode mode, then check the interposer).
- **Opens a panic file by hand**: `.ips`, `.txt` or a file with no extension. If the file is not a panic log (such as an app crash report or any other text), it says so.
- **Saves a text report** to give to a customer or keep with the job.
- **Updates itself.** On start it checks GitHub for a newer release. If there is one, it shows what is new and offers *Update now*, *Later* or *Skip this version*. *Update now* downloads the new exe, checks it, closes the app, swaps the exe and opens the new version. Your own `rules.json` edits are kept, and new codes from the update are added to them. You can also click *Check for updates* at the top right at any time.

## What you need

| Need | Why |
|---|---|
| Windows 10 or 11 | The app is built for Windows. |
| **One** of: iTunes (Microsoft Store), Apple Devices (Microsoft Store) or 3uTools | These install *Apple Mobile Device Service*, which is the driver the app uses to talk to the iPhone. The app checks this and helps you install one. |
| A data USB cable | Charge-only cables will not show the phone. |
| The iPhone's passcode | Needed once to tap *Trust* on the phone. |

If you run the `.exe`, you need nothing else. Only to run from source do you also need Python 3.12 or newer.

## Getting the .exe

**Easiest:** open the repository's **Releases** page and download `iPhonePanicAnalyzer-<version>-windows.zip`, which holds the exe, `rules.json` and this README.

**To make a new release** (this is what the in-app updater picks up), either:

- push a version tag: `git tag v1.2` then `git push origin v1.2`, or
- on GitHub go to *Releases*, click *Draft a new release*, create a tag such as `v1.2`, and click *Publish release*.

GitHub Actions builds the exe with that version number, creates the release (with notes listing the changes) and attaches `iPhonePanicAnalyzer.exe` and the zip after about 3 minutes. Every copy of the app sees the update the next time it starts. Use a higher number each time (`v1.2`, `v1.3`, ... `v2.0`).

**Every push** also builds the exe: open the **Actions** tab, open the latest **Build Windows exe** run and download **iPhonePanicAnalyzer** under *Artifacts*.

Windows SmartScreen may warn about an unknown app the first time, because the app is not code-signed. Click *More info* and then *Run anyway*.

## Adding your own panic codes

All fault knowledge is in `rules.json`, which you can edit in Notepad:

- `sensors`: codes from the `Missing sensor(s):` line (PRS0, mic1, TG0B, and so on), with the part's name, where it is, and repair steps. You can give a different location for some models with `locations` and ProductType prefixes (`"iPhone12,"` = iPhone 11 series).
- `watchdog_daemons`: what it means when a given service stops checking in (`thermalmonitord`, `wifid`, `CommCenter`, and so on).
- `rules`: regular-expression patterns for everything else (i2c bus stuck, baseband, NAND, Face ID, and so on). `{g1}` in the text is filled in with the first captured value, for example the i2c bus number.

Restart the app after editing.

> The diagnosis is a guide based on codes that are known in the repair trade. Always confirm with measurements before you replace parts. Sensor locations differ between models, so check the schematic when in doubt.

## Run from source

Double-click `run.bat`. The first run sets up a Python environment.

## Project layout

```
app/main.py       window and user interface (Tkinter)
app/device.py     detects the iPhone, handles the Trust prompt and copies panic logs (pymobiledevice3)
app/drivers.py    checks the Apple drivers; iTunes, Apple Devices and 3uTools links and download
app/analyzer.py   reads .ips, .txt and extensionless panic files and matches them against rules.json
app/updater.py    checks GitHub Releases for a newer version, downloads and installs it
app/theme.py      dark theme, colours and app icon
app/version.py    app version (set from the git tag when GitHub builds a release)
app/assets/       app icon (icon.ico, icon.png); tools/make_icon.py draws it
app/rules.json    fault knowledge base (editable)
samples/          example panic logs used by the tests
tests/            unit tests (run by GitHub Actions)
```
