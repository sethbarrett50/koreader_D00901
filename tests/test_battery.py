import subprocess

from datetime import UTC, datetime, timedelta

import pytest

from koreader_d00901 import battery
from koreader_d00901.errors import DeviceError

T0 = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
SYSFS = """sys.battery_capacity=87
sys.battery_voltage=4012
charging=0
lipc.battLevel=
lipc.isCharging=
gasgauge.c=
serial=B006A0A0B0C0D0E0
uptime=1234.5
"""


def test_parse_prefers_sysfs():
    r = battery.parse(SYSFS, now=T0)
    assert (r.serial, r.capacity, r.charging, r.source) == ('B006A0A0B0C0D0E0', 87, False, 'sys.battery_capacity')
    assert r.raw['sys.battery_voltage'] == '4012'


def test_parse_falls_back_to_lipc_then_gasgauge():
    lipc = battery.parse('lipc.battLevel=55\nlipc.isCharging=1\ngasgauge.c=54%\nserial=X\n', now=T0)
    assert (lipc.capacity, lipc.source, lipc.charging) == (55, 'lipc.battLevel', True)
    gauge = battery.parse('gasgauge.c=54%\n', now=T0)
    assert (gauge.capacity, gauge.source, gauge.serial, gauge.charging) == (54, 'gasgauge.c', 'unknown', None)


def test_read_battery_without_any_source_is_an_error():
    with pytest.raises(DeviceError, match='no battery reading'):
        battery.read_battery(lambda script: 'charging=1\n')


def test_remote_script_reads_the_k3_sources():
    for path in (battery.BATTERY_DIR, battery.CHARGING_FILE, 'battLevel', 'gasgauge-info -c', '/proc/usid'):
        assert path in battery.REMOTE_SCRIPT


def test_log_and_drain(tmp_path):
    log = tmp_path / 'battery.csv'
    first = battery.parse(SYSFS, now=T0, note='start')
    battery.append(log, first)
    assert battery.previous(log, 'someone else') is None
    later = battery.parse(SYSFS.replace('=87', '=75'), now=T0 + timedelta(hours=24))
    before = battery.previous(log, later.serial)
    assert before == (T0, 87)
    assert battery.drain(before, later) == '-12% over 24.0 h since 2026-11-05 12:00 UTC (0.50%/h, about 12% per day)'
    battery.append(log, later)
    text = log.read_text()
    assert text.startswith('time,serial,capacity,charging,source,note,raw')
    assert 'start' in text
    assert 'sys.battery_voltage=4012' in text


def test_main_prints_and_logs(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(battery, 'ssh_runner', lambda host, user: lambda script: SYSFS)
    monkeypatch.setattr(battery, 'setup_logging', lambda *a, **k: None)
    log = tmp_path / 'b.csv'
    assert battery.main(['--log', str(log), '--raw', '--note', 'unit 1']) == 0
    out = capsys.readouterr().out
    assert 'B006A0A0B0C0D0E0: 87% (not charging; from sys.battery_capacity)' in out
    assert 'sys.battery_voltage = 4012' in out
    assert battery.main(['--log', str(log)]) == 0
    assert '+0% over' in capsys.readouterr().out


def test_main_reports_ssh_failure(tmp_path, monkeypatch, capsys):
    def fake_run(argv, **kwargs):
        assert argv[0] == 'ssh'
        assert 'root@192.168.2.2' in argv
        return subprocess.CompletedProcess(argv, 255, '', 'ssh: connect to host 192.168.2.2: No route to host')

    monkeypatch.setattr(battery.subprocess, 'run', fake_run)
    monkeypatch.setattr(battery, 'setup_logging', lambda *a, **k: None)
    assert battery.main(['--log', str(tmp_path / 'b.csv')]) == 1
    err = capsys.readouterr().err
    assert 'No route to host' in err
    assert 'USBNetwork' in err
    assert not (tmp_path / 'b.csv').exists()
