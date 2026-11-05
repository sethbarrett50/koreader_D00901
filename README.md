# KOReader installer for the Kindle Keyboard (K3)

Use this at your own risk: it modifies your Kindle's firmware and I am not responsible for a unit that stops working.

## What this does

`koreader-d00901` (the `koreader_D00901` Python package) downloads pinned, checksum-verified packages and stages them on a Kindle Keyboard (K3) that is mounted as a USB drive. It chains:

1. The jailbreak, which lets the Kindle install custom update packages.
2. MKK (the developer certificates the Kindle needs to run custom Kindlets such as KUAL).
   MKK's 2014 certificates expired in April 2025, so the installer then applies NiLuJe's 2025 developer keystore update, which adds the certificates current KUAL is signed with.
3. KUAL (the Kindle Unified Application Launcher), copied into `documents/`.
4. KOReader, merged into the Kindle's root.
5. Optionally, USBNetwork (`--usbnet`), for ssh access over USB.

## Before you start

- Charge the Kindle fully.
- Deregister it: Settings > Registration > Deregister.
- Turn wireless off.
- Find your firmware version at the bottom of the Settings page (for example 3.4.2).
- Find your serial prefix: the first four characters of the serial number (B006, B008 or B00A), listed under Device Info or on the back of the unit.

## Which files your Kindle needs

The installer picks the right files from your serial prefix and firmware range.

| Serial prefix | Variant |
| ------------- | ------- |
| B006          | k3g     |
| B008          | k3w     |
| B00A          | k3gb    |

Firmware 3.0-3.2 uses the jailbreak file marked `-3.0-to-3.2`. Firmware 3.3-3.4 uses the plain jailbreak file. The installer asks for the range as `3.0-3.2` or `3.3-3.4`.

## Running the installer

Clone the repo, then connect the Kindle in USB drive mode. The easiest way is the full-screen installer:

```
uv run koreader-d00901-tui
```

Pick the firmware range and serial prefix, press **Install**, and follow the on-screen steps. Between updates it shows what to do on the Kindle, has an **Eject Kindle** button, and waits for **Continue**. **Dry run** shows the plan without changing anything.

The same install also runs as a plain terminal script. Do a dry run first: it prints the plan and changes nothing.

```
uv run koreader-d00901 --dry-run
```

Then run it for real:

```
uv run koreader-d00901
```

Flags (both commands take the same ones, except that `--dry-run` is CLI-only):

- `--dry-run`: print the plan only.
- `--mount PATH`: the Kindle's USB mount point. Without it the installer looks for a volume labelled Kindle.
- `--fw RANGE`: firmware range, `3.0-3.2` or `3.3-3.4`. Asked interactively if omitted.
- `--prefix PREFIX`: serial prefix, `B006`, `B008` or `B00A`. Asked interactively if omitted.
- `--usbnet`: also install USBNetwork.
- `--wipe-books`: delete the existing books in `documents/` before installing, which is handy for second-hand units. It lists everything it will delete and asks you to type `wipe` (the TUI shows a confirmation dialog). It keeps `KUAL-KDK-1.0.azw2` and the `dictionaries` folder, and never touches anything outside `documents/`. With `--dry-run` it only lists what it would delete.
- `--cache DIR`: where downloads are kept (default `~/.cache/k3-koreader`).
- `--log-file FILE`: where the debug log goes (default `CACHE/install.log`).
- `-v`, `--verbose`: also print debug logging on the terminal (CLI only).
- `--version`: print the version.

Every run writes a debug log. If an install fails, check `~/.cache/k3-koreader/install.log` first.

Each download is checked against the sha256 in `packages.json` and rejected if it does not match.

## On the Kindle

For each update the installer stages one `.bin` file and pauses. Then:

1. Eject and unplug the Kindle (safely eject it first; the update cannot run in USB drive mode).
2. Press [HOME] > [MENU] > Settings > [MENU] > Update Your Kindle.
3. Wait for the reboot, reconnect in USB drive mode and press Enter in the installer.

The order is jailbreak, then MKK, then the 2025 keystore (then USBNetwork if requested). After the last step, eject the Kindle, open KUAL from the library and choose KOReader.

## If something goes wrong

- Update Your Kindle is greyed out: the wrong file was staged. Check your serial prefix and firmware range and run the installer again.
- Never force an update by rebooting the Kindle by hand.
- If the Kindle hangs, hold the power button for about 15 seconds for a hard reboot.
- Deregistering or an over-the-air (OTA) update can remove the developer certificates. Reinstall MKK when that happens.
- KUAL says the title is "not signed by a registered developer": the 2025 keystore update did not apply. Copy `Update-mkk-20250419-<variant>-<prefix>_keystore-install.bin` from `DevCerts-20250419-KeyStore.zip` to the Kindle root and run Update Your Kindle again.

## USBNetwork (optional)

After installing with `--usbnet`, enable it from the Kindle's search bar:

1. Type `;debugOn` and press Enter.
2. Type `~usbNetwork` and press Enter.
3. Type `;debugOff` and press Enter.

Then connect over USB. On Debian the Kindle appears as a USB network interface, often `usb0` (check with `ip link`). Assign the computer side its address:

```
sudo ip addr add 192.168.2.1/24 dev usb0
sudo ip link set usb0 up
```

(The older equivalent is `sudo ifconfig usb0 192.168.2.1`.) Then use `ssh root@192.168.2.2`. Login is passwordless only over USB with Wi-Fi mode off.

Before ejecting, bring the interface down with `sudo ip link set usb0 down`, and enter `~usbNetwork` again on the Kindle to switch back to USB drive mode.

## Pinned packages

| Package    | File                                     | sha256 (first 12) |
| ---------- | ---------------------------------------- | ----------------- |
| jailbreak  | kindle-jailbreak-0.13.N-r18833.tar.xz    | 8f5c8a78e3c4      |
| mkk        | kindle-mkk-20141129-r18833.tar.xz        | 3d7289f1ddcf      |
| keystore   | DevCerts-20250419-KeyStore.zip           | 48426add32e3      |
| kual       | KUAL-v2.7.37-gfcb45b5-20250419.tar.xz    | 40c4b6871221      |
| usbnet     | kindle-usbnetwork-0.57.N-k3.zip          | 7d210bc41619      |
| koreader   | koreader-kindle-legacy-v2026.07.1.zip    | 0ed8d5eec422      |

## Credits

- Jailbreak: https://www.mobileread.com/forums/showthread.php?t=225030
- 2025 developer keystore (NiLuJe, 2025-04-19): https://www.mobileread.com/forums/attachment.php?attachmentid=215127&d=1745098511
- KUAL: https://www.mobileread.com/forums/showthread.php?t=203326
- USBNetwork: https://www.mobileread.com/forums/showthread.php?t=88004
- KOReader: https://github.com/koreader/koreader

## Development

```
make sync       # uv sync --dev (ruff, ty, pytest)
make lint       # ruff format + ruff check --fix
make typecheck  # ty check
make test       # pytest
make ci         # everything CI runs, without fixes
```

The code lives in `src/koreader_d00901/`:

- `plan.py`: which files a given serial prefix and firmware range need.
- `packages.py`: downloading, verifying and unpacking the packages pinned in `packages.json`.
- `device.py`: everything that touches the Kindle's USB volume.
- `cli.py` / `tui.py`: the two front ends.
- `errors.py`: `InstallerError` and its subclasses, which are reported to the user as one line.
- `logs.py`: logging setup (a debug log file on every run).
