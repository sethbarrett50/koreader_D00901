# Battery health and drain (issue #2)

All six K3s arrived on the Empty Battery screen after years in storage, so some cells may be worn.
This page is the procedure and the record. Fill in the table as each unit is measured.

## What the K3 reports

KOReader reads a Kindle 3's battery from these sources (KOReader v2026.07.1,
`frontend/device/kindle/device.lua` `Kindle3:init` and `powerd.lua` `getCapacityHW`):

| What | Where |
| ---- | ----- |
| Charge, percent | `/sys/devices/system/luigi_battery/luigi_battery0/battery_capacity` |
| Charging (1/0) | `/sys/devices/platform/fsl-usb2-udc/charging` |
| Fallbacks | `lipc-get-prop com.lab126.powerd battLevel`, `gasgauge-info -c` |

`koreader-d00901-battery` reads all of these and also dumps every other file in the
`luigi_battery0` directory. Which of those exist on firmware 3.4.2 (voltage, current, temperature,
or a full-charge capacity that would give a real health figure) is **not yet verified**. The
first `--raw` reading from unit 1 settles it, and this page will be updated with what it shows.

## Taking a reading

1. Install USBNetwork on the unit if it does not have it yet. This runs only that step:
   `koreader-d00901 --only usbnet`. See [usbnetwork.md](usbnetwork.md) for the details.
2. On the Kindle's search bar: `;debugOn`, `~usbNetwork`, `;debugOff`.
3. On the computer: `sudo ip addr add 192.168.2.1/24 dev usb0 && sudo ip link set usb0 up`.
4. `koreader-d00901-battery --note "unit 1" --raw`

Each reading is appended to `~/.cache/k3-koreader/battery.csv`, keyed by the device serial
(`/proc/usid`). When a unit already has a reading, the command prints the change since then.

## 24-hour idle drain

USB charges the Kindle, so drain can only be measured **unplugged**:

1. Charge to 100%. Take a reading with the note `start, KOReader idle, Wi-Fi off`.
2. Unplug. Leave the unit idle in KOReader with Wi-Fi off for about 24 hours.
3. Plug back in, enable USBNetwork, and read **immediately**, before charging adds much back.
   The printed line gives `%/h` and an estimated `% per day`.
4. Repeat with Wi-Fi on if the unit will run the Grafana dashboard (#4) or fetch feeds (#5).

## Units

| Unit | Serial prefix | Firmware | Charged to | 24 h idle drain (Wi-Fi off) | Notes | Verdict |
| ---- | ------------- | -------- | ---------- | --------------------------- | ----- | ------- |
| 1    | B006          | 3.4.2    |            |                             |       |         |
| 2    |               |          |            |                             |       |         |
| 3    |               |          |            |                             |       |         |
| 4    |               |          |            |                             |       |         |
| 5    |               |          |            |                             |       |         |
| 6    |               |          |            |                             |       |         |

Verdict is keep, re-cell, or parts. Until a full-charge capacity field turns up, these
working thresholds apply: a healthy K3 on stock firmware is rated for weeks of standby, so
**keep** a unit that loses under about 5% per day idle with Wi-Fi off, consider a **re-cell**
above about 15% per day or when it will not charge past 90%, and mark **parts** a unit that
will not hold a charge or will not boot. These thresholds are judgment, not measurement;
revise them once the first units are measured.
