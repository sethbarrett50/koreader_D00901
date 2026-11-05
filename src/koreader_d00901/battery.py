"""Read a K3's battery over USBNetwork SSH and log readings per unit, to track health and drain (#2).

Sources, in the order KOReader itself uses them on a Kindle 3 (frontend/device/kindle/device.lua
Kindle3:init and powerd.lua getCapacityHW, KOReader v2026.07.1):

- /sys/devices/system/luigi_battery/luigi_battery0/battery_capacity, the charge in percent
- /sys/devices/platform/fsl-usb2-udc/charging, 1 while charging
- lipc-get-prop com.lab126.powerd battLevel, then gasgauge-info -c, as fallbacks

Every other file in the luigi_battery0 directory (voltage, current, temperature, and so on, where the
firmware has them) is captured raw, so the first real reading shows what a K3 exposes.
"""

import argparse
import csv
import logging
import subprocess
import sys

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from koreader_d00901 import __version__
from koreader_d00901.errors import DeviceError, InstallerError
from koreader_d00901.logs import DEFAULT_CACHE, setup_logging

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

DEFAULT_HOST = '192.168.2.2'  # USBNetwork's fixed address for the Kindle side
BATTERY_DIR = '/sys/devices/system/luigi_battery/luigi_battery0'
CHARGING_FILE = '/sys/devices/platform/fsl-usb2-udc/charging'

# One round trip; every line is key=value, and missing sources print an empty value.
REMOTE_SCRIPT = f"""
for f in {BATTERY_DIR}/*; do [ -f "$f" ] && echo "sys.$(basename "$f")=$(cat "$f" 2>/dev/null)"; done
echo "charging=$(cat {CHARGING_FILE} 2>/dev/null)"
echo "lipc.battLevel=$(lipc-get-prop com.lab126.powerd battLevel 2>/dev/null)"
echo "lipc.isCharging=$(lipc-get-prop com.lab126.powerd isCharging 2>/dev/null)"
echo "gasgauge.c=$(gasgauge-info -c 2>/dev/null)"
echo "serial=$(cat /proc/usid 2>/dev/null)"
echo "uptime=$(cut -d' ' -f1 /proc/uptime 2>/dev/null)"
"""

CSV_FIELDS = ('time', 'serial', 'capacity', 'charging', 'source', 'note', 'raw')

type Runner = Callable[[str], str]


@dataclass(frozen=True)
class Reading:
    time: datetime
    serial: str
    capacity: int | None
    charging: bool | None
    source: str
    raw: dict[str, str] = field(default_factory=dict)
    note: str = ''


def ssh_runner(host: str, user: str = 'root', timeout: int = 15) -> Runner:
    """Run a shell script on the Kindle over SSH and return its stdout."""

    def run(script: str) -> str:
        # USBNetwork always uses 192.168.2.2, so all six units share one address with different host
        # keys. Host-key checking is off for this point-to-point USB link only.
        argv = [
            'ssh', '-o', 'BatchMode=yes', '-o', f'ConnectTimeout={timeout}',
            '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR',
            f'{user}@{host}', 'sh -s',
        ]  # fmt: skip
        log.debug('running %s', ' '.join(argv))
        try:
            result = subprocess.run(argv, input=script, capture_output=True, text=True, timeout=timeout * 2)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeviceError(f'could not reach the Kindle at {host}: {exc}') from exc
        log.debug('ssh rc=%d stdout=%r stderr=%r', result.returncode, result.stdout, result.stderr)
        if result.returncode != 0:
            raise DeviceError(
                f'ssh {user}@{host} failed: {result.stderr.strip() or f"exit {result.returncode}"}. '
                'Is USBNetwork on (;debugOn, ~usbNetwork) and usb0 at 192.168.2.1?'
            )
        return result.stdout

    return run


def _int(value: str | None) -> int | None:
    try:
        return int(value.strip().rstrip('%')) if value else None
    except ValueError:
        return None


def parse(output: str, now: datetime | None = None, note: str = '') -> Reading:
    raw = {}
    for line in output.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            raw[key.strip()] = value.strip()
    capacity, source = None, 'none'
    for key in ('sys.battery_capacity', 'lipc.battLevel', 'gasgauge.c'):
        if (value := _int(raw.get(key))) is not None:
            capacity, source = value, key
            break
    charging_value = _int(raw.get('charging'))
    if charging_value is None:
        charging_value = _int(raw.get('lipc.isCharging'))
    return Reading(
        time=now or datetime.now(UTC),
        serial=raw.get('serial') or 'unknown',
        capacity=capacity,
        charging=None if charging_value is None else charging_value != 0,
        source=source,
        raw=raw,
        note=note,
    )


def read_battery(run: Runner, note: str = '') -> Reading:
    reading = parse(run(REMOTE_SCRIPT), note=note)
    if reading.capacity is None:
        raise DeviceError(f'no battery reading found; raw output: {reading.raw}')
    return reading


def append(log_path: Path, reading: Reading) -> None:
    new = not log_path.exists()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', newline='') as f:
        writer = csv.DictWriter(f, CSV_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow({
            'time': reading.time.isoformat(timespec='seconds'),
            'serial': reading.serial,
            'capacity': reading.capacity,
            'charging': '' if reading.charging is None else int(reading.charging),
            'source': reading.source,
            'note': reading.note,
            'raw': ';'.join(f'{k}={v}' for k, v in sorted(reading.raw.items())),
        })


def previous(log_path: Path, serial: str) -> tuple[datetime, int] | None:
    """The last logged (time, capacity) for this serial, if any."""
    if not log_path.exists():
        return None
    last = None
    with log_path.open(newline='') as f:
        for row in csv.DictReader(f):
            if row['serial'] == serial and (cap := _int(row['capacity'])) is not None:
                last = (datetime.fromisoformat(row['time']), cap)
    return last


def drain(before: tuple[datetime, int], reading: Reading) -> str:
    then, cap = before
    hours = (reading.time - then).total_seconds() / 3600
    assert reading.capacity is not None
    delta = reading.capacity - cap
    if hours <= 0:
        return 'previous reading is not older than this one'
    line = f'{delta:+d}% over {hours:.1f} h since {then:%Y-%m-%d %H:%M} UTC'
    if delta < 0:
        line += f' ({-delta / hours:.2f}%/h, about {-delta / hours * 24:.0f}% per day)'
    return line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='koreader-d00901-battery',
        description='Read a K3 battery over USBNetwork and log it per serial number.',
    )
    parser.add_argument('--host', default=DEFAULT_HOST, help=f'Kindle address (default {DEFAULT_HOST})')
    parser.add_argument('--user', default='root', help='ssh user (default root)')
    parser.add_argument(
        '--log', type=Path, default=DEFAULT_CACHE / 'battery.csv', help='CSV log (default CACHE/battery.csv)'
    )
    parser.add_argument('--note', default='', help="free text stored with the reading, e.g. 'unit 3, after 24h idle'")
    parser.add_argument('--raw', action='store_true', help='print every field the Kindle reported')
    parser.add_argument('-v', '--verbose', action='store_true', help='show debug logging')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    args = parser.parse_args(argv)
    setup_logging(DEFAULT_CACHE / 'battery-debug.log', verbose=args.verbose)

    try:
        reading = read_battery(ssh_runner(args.host, args.user), note=args.note)
    except InstallerError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    before = previous(args.log, reading.serial)
    append(args.log, reading)

    state = {True: 'charging', False: 'not charging', None: 'charging state unknown'}[reading.charging]
    print(f'{reading.serial}: {reading.capacity}% ({state}; from {reading.source})')
    if before is not None:
        print(f'  {drain(before, reading)}')
    if args.raw:
        for key, value in sorted(reading.raw.items()):
            print(f'  {key} = {value}')
    print(f'Logged to {args.log}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
