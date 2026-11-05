"""device.py on each operating system, simulated through device._system and fake commands."""

import os
import subprocess

from pathlib import Path

import pytest

from koreader_d00901 import device
from koreader_d00901.errors import DeviceError

LINUX_ONLY = ('findmnt', 'udisksctl')


@pytest.fixture
def commands(monkeypatch):
    """Record every command device.py runs; answer from a {program: (rc, stdout, stderr)} table."""
    calls: list[list[str]] = []
    replies: dict[str, tuple[int, str, str]] = {}

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv[0] not in replies:
            raise FileNotFoundError(2, 'No such file or directory', argv[0])
        rc, out, err = replies[argv[0]]
        return subprocess.CompletedProcess(argv, rc, out, err)

    monkeypatch.setattr(device.subprocess, 'run', fake_run)
    return calls, replies


def _on(monkeypatch, system):
    monkeypatch.setattr(device, '_system', lambda: system)


def test_linux_finds_the_kindle_with_findmnt(monkeypatch, commands):
    calls, replies = commands
    _on(monkeypatch, 'Linux')
    replies['findmnt'] = (0, '/media/me/Kindle\\x20K3\n', '')
    assert device.find_mount() == Path('/media/me/Kindle K3')
    assert calls == [['findmnt', '-rn', '-S', 'LABEL=Kindle', '-o', 'TARGET']]


def test_linux_without_findmnt_finds_nothing(monkeypatch, commands):
    _on(monkeypatch, 'Linux')
    assert device.find_mount() is None


def test_macos_finds_the_kindle_under_volumes(monkeypatch, commands, tmp_path):
    calls, _ = commands
    _on(monkeypatch, 'Darwin')
    volumes = tmp_path / 'Volumes'
    for name in ('Kindlex', 'Kindle 1', 'Macintosh HD'):
        (volumes / name).mkdir(parents=True)
    monkeypatch.setattr(device, 'VOLUMES', volumes)
    assert device.find_mount() == volumes / 'Kindle 1'
    (volumes / 'Kindle').mkdir()
    assert device.find_mount() == volumes / 'Kindle'
    assert calls == []


def test_windows_finds_the_drive_labelled_kindle(monkeypatch, commands):
    calls, _ = commands
    _on(monkeypatch, 'Windows')
    drives = [(Path('C:/'), 'Windows'), (Path('E:/'), 'KINDLE'), (Path('F:/'), 'Kindle')]
    monkeypatch.setattr(device, '_windows_volumes', lambda: drives)
    assert device.find_mount() == Path('E:/')
    monkeypatch.setattr(device, '_windows_volumes', lambda: drives[:1])
    assert device.find_mount() is None
    assert calls == []


def test_unknown_system_finds_nothing(monkeypatch, commands):
    calls, _ = commands
    _on(monkeypatch, 'Haiku')
    assert device.find_mount() is None
    assert calls == []


def test_linux_ejects_with_udisksctl(monkeypatch, commands):
    calls, replies = commands
    _on(monkeypatch, 'Linux')
    replies['findmnt'] = (0, '/dev/sdb1\n', '')
    replies['udisksctl'] = (0, 'Unmounted /dev/sdb1.\n', '')
    assert device.eject(Path('/media/me/Kindle')) == 'Unmounted /dev/sdb1.'
    assert calls[-1] == ['udisksctl', 'unmount', '-b', '/dev/sdb1']


def test_linux_eject_without_udisksctl_says_use_the_file_manager(monkeypatch, commands):
    _, replies = commands
    _on(monkeypatch, 'Linux')
    replies['findmnt'] = (0, '/dev/sdb1\n', '')
    with pytest.raises(DeviceError, match='file manager'):
        device.eject(Path('/media/me/Kindle'))


def test_macos_ejects_with_diskutil(monkeypatch, commands):
    calls, replies = commands
    _on(monkeypatch, 'Darwin')
    replies['diskutil'] = (0, 'Disk /Volumes/Kindle ejected\n', '')
    assert device.eject(Path('/Volumes/Kindle')) == 'Disk /Volumes/Kindle ejected'
    assert calls == [['diskutil', 'eject', str(Path('/Volumes/Kindle'))]]


def test_macos_eject_failure_is_reported(monkeypatch, commands):
    _, replies = commands
    _on(monkeypatch, 'Darwin')
    replies['diskutil'] = (1, '', 'Volume Kindle failed to eject: in use\n')
    with pytest.raises(DeviceError, match='in use'):
        device.eject(Path('/Volumes/Kindle'))


def _drive_until(monkeypatch, calls, gone_after):
    """Drive E: stays present until PowerShell has run gone_after times."""
    monkeypatch.setattr(device, '_present', lambda mount: len(calls) < gone_after)
    return Path('E:/')


def test_windows_ejects_with_the_shell_verb(monkeypatch, commands):
    calls, replies = commands
    _on(monkeypatch, 'Windows')
    replies['powershell'] = (0, '', '')
    assert device.eject(_drive_until(monkeypatch, calls, 1)) == 'Ejected E:.'
    assert calls[0][0] == 'powershell'
    assert "ParseName('E:').InvokeVerb('Eject')" in calls[0][-1]
    assert not any(argv[0] in LINUX_ONLY for argv in calls)


def test_windows_eject_that_does_not_happen_says_use_explorer(monkeypatch, commands):
    calls, replies = commands
    _on(monkeypatch, 'Windows')
    replies['powershell'] = (0, '', '')
    monkeypatch.setattr(device, 'WINDOWS_EJECT_WAIT', 0)
    with pytest.raises(DeviceError, match='File Explorer'):
        device.eject(_drive_until(monkeypatch, calls, 99))


def test_windows_eject_needs_a_drive_root(monkeypatch, commands):
    _on(monkeypatch, 'Windows')
    with pytest.raises(DeviceError, match='not a drive root'):
        device.eject(Path('/some/folder'))


@pytest.mark.parametrize('system', ['Darwin', 'Windows', 'Haiku'])
def test_no_linux_tool_runs_elsewhere(monkeypatch, commands, tmp_path, system):
    calls, _ = commands
    _on(monkeypatch, system)
    monkeypatch.setattr(device, '_windows_volumes', list)
    monkeypatch.setattr(device, 'WINDOWS_EJECT_WAIT', 0)
    device.find_mount()
    with pytest.raises(DeviceError):
        device.eject(tmp_path)
    assert not any(argv[0] in LINUX_ONLY for argv in calls)


def test_flush_without_os_sync(monkeypatch, tmp_path):
    """Windows has no os.sync; staging and wiping must still work."""
    monkeypatch.delattr(os, 'sync', raising=False)
    bin_path = tmp_path / 'Update_new.bin'
    bin_path.write_bytes(b'new')
    mount = tmp_path / 'mount'
    (mount / 'documents').mkdir(parents=True)
    (mount / 'documents' / 'book.mobi').write_bytes(b'x')
    device.flush()
    device.stage_update(mount, bin_path)
    assert (mount / 'Update_new.bin').read_bytes() == b'new'
    assert device.wipe_books(mount, device.list_books(mount)) == 1


def test_flush_uses_os_sync_where_there_is_one(monkeypatch):
    synced = []
    monkeypatch.setattr(os, 'sync', lambda: synced.append(True), raising=False)
    device.flush()
    assert synced == [True]
