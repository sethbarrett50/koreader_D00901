"""Everything that touches the Kindle's USB volume."""

import ctypes
import logging
import os
import platform
import shutil
import subprocess
import sys
import time

from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from koreader_d00901.errors import DeviceError
from koreader_d00901.plan import KOREADER_TREES, KUAL_FILE

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

# K3 update packages are named Update_*.bin or Update-*.bin (the 2025 keystore uses a hyphen).
UPDATE_GLOB = 'Update[-_]*.bin'


LABEL = 'Kindle'
VOLUMES = Path('/Volumes')  # where macOS mounts removable drives


def _system() -> str:
    """platform.system(), behind a function so tests can simulate each operating system."""
    return platform.system()


def _run(argv: list[str], what: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise DeviceError(f'could not run {argv[0]} ({exc}); {what}') from exc
    log.debug('%s -> rc=%d stdout=%r stderr=%r', ' '.join(argv), result.returncode, result.stdout, result.stderr)
    return result


def _findmnt(*args: str) -> str:
    return _run(['findmnt', '-rn', *args], 'pass the mount point explicitly').stdout


def _windows_volumes() -> list[tuple[Path, str]]:
    """(root, label) for every drive letter, read with GetVolumeInformationW."""
    if sys.platform != 'win32':
        return []
    kernel32 = ctypes.windll.kernel32
    volumes = []
    mask = kernel32.GetLogicalDrives()
    # SEM_FAILCRITICALERRORS: an empty card reader fails quietly instead of opening a "no disk" dialog.
    previous = kernel32.SetErrorMode(0x0001)
    try:
        for i in range(26):
            if not mask & (1 << i):
                continue
            root = f'{chr(ord("A") + i)}:\\'
            label = ctypes.create_unicode_buffer(261)
            if kernel32.GetVolumeInformationW(root, label, len(label), None, None, None, None, 0):
                volumes.append((Path(root), label.value))
    finally:
        kernel32.SetErrorMode(previous)
    log.debug('windows volumes: %r', volumes)
    return volumes


def find_mount() -> Path | None:
    """Return where the volume labelled Kindle is mounted, or None.

    Linux asks findmnt for the label, macOS mounts volumes by label under /Volumes, and Windows
    gives each volume a drive letter whose label is read through the Win32 API.
    """
    system = _system()
    if system == 'Linux':
        try:
            targets = _findmnt('-S', f'LABEL={LABEL}', '-o', 'TARGET').split()
        except DeviceError as exc:
            log.warning('%s', exc)
            return None
        # findmnt -r escapes spaces in paths as \x20.
        return Path(targets[0].replace('\\x20', ' ')) if targets else None
    if system == 'Darwin':
        # A second volume with the same name is mounted as "Kindle 1".
        candidates = sorted(VOLUMES.glob(f'{LABEL}*'))
        return next((p for p in candidates if p.name == LABEL or p.name.startswith(f'{LABEL} ')), None)
    if system == 'Windows':
        return next((root for root, label in _windows_volumes() if label.casefold() == LABEL.casefold()), None)
    log.warning('finding the Kindle is not supported on %s; pass --mount PATH', system)
    return None


def require_mount(mount: Path | None) -> Path:
    """The given mount point, or the detected one; raise DeviceError if there is none."""
    if mount is None:
        mount = find_mount()
        if mount is None:
            raise DeviceError(
                'no mounted volume labelled Kindle found; connect the Kindle in USB drive mode or pass --mount PATH'
            )
        log.info('found the Kindle at %s', mount)
    if not mount.is_dir():
        raise DeviceError(f'mount point {mount} is not a directory')
    return mount


MANUAL_EJECT = 'eject the Kindle from your file manager'
WINDOWS_EJECT_WAIT = 10.0


def _eject_linux(mount: Path) -> str:
    source = _findmnt('-o', 'SOURCE', '--mountpoint', str(mount)).strip()
    if not source:
        raise DeviceError(f'nothing is mounted at {mount}')
    result = _run(['udisksctl', 'unmount', '-b', source], MANUAL_EJECT)
    if result.returncode != 0:
        raise DeviceError(result.stderr.strip() or f'udisksctl unmount -b {source} failed')
    return result.stdout.strip()


def _eject_macos(mount: Path) -> str:
    result = _run(['diskutil', 'eject', str(mount)], MANUAL_EJECT)
    if result.returncode != 0:
        raise DeviceError(result.stderr.strip() or f'diskutil eject {mount} failed; {MANUAL_EJECT}')
    return result.stdout.strip()


def _present(mount: Path) -> bool:
    return mount.exists()


def _eject_windows(mount: Path) -> str:
    windows_path = PureWindowsPath(mount)
    drive = windows_path.drive  # 'E:'
    if not drive or len(windows_path.parts) != 1:
        raise DeviceError(f'{mount} is not a drive root; eject the Kindle from File Explorer')
    # The Eject verb from the drive's right-click menu in File Explorer. It reports nothing (and the
    # verb name is localized), so success is judged by the drive going away.
    script = f"(New-Object -ComObject Shell.Application).Namespace(17).ParseName('{drive}').InvokeVerb('Eject')"
    _run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], 'eject the Kindle from File Explorer')
    deadline = time.monotonic() + WINDOWS_EJECT_WAIT
    while _present(mount):
        if time.monotonic() > deadline:
            raise DeviceError(f'{drive} is still there; eject the Kindle from File Explorer (Eject on the drive)')
        time.sleep(0.5)
    return f'Ejected {drive}.'


def eject(mount: Path) -> str:
    """Safely eject the Kindle mounted at mount and return a message for the user."""
    system = _system()
    if system == 'Linux':
        return _eject_linux(mount)
    if system == 'Darwin':
        return _eject_macos(mount)
    if system == 'Windows':
        return _eject_windows(mount)
    raise DeviceError(f'ejecting is not supported on {system}; {MANUAL_EJECT}')


def stage_update(mount: Path, bin_path: Path) -> None:
    """Leave bin_path as the only update package at the Kindle root, flushed to disk."""
    for old in mount.glob(UPDATE_GLOB):
        log.debug('removing old update package %s', old)
        old.unlink()
    shutil.copy2(bin_path, mount / bin_path.name)
    flush()
    log.info('staged %s', bin_path.name)


def update_pending(mount: Path, bin_path: Path) -> bool:
    """True when the staged package is still on the Kindle, which means the update did not run."""
    return (mount / bin_path.name).exists()


def install_kual(mount: Path, kual: Path) -> None:
    (mount / 'documents').mkdir(exist_ok=True)
    shutil.copy2(kual, mount / 'documents' / kual.name)
    log.info('copied %s to documents/', kual.name)


def koreader_pairs(ko_root: Path, mount: Path) -> list[tuple[Path, Path]]:
    """(src, dst) pairs for every KOReader file, merged into the mount root."""
    return [
        (f, mount / f.relative_to(ko_root))
        for tree in KOREADER_TREES
        if (ko_root / tree).is_dir()
        for f in sorted((ko_root / tree).rglob('*'))
        if f.is_file()
    ]


def copy_files(pairs: list[tuple[Path, Path]], on_progress: Callable[[int, int], None] | None = None) -> None:
    total = len(pairs)
    for i, (src, dst) in enumerate(pairs, 1):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        log.debug('copied %s', dst)
        if on_progress is not None:
            on_progress(i, total)


def flush() -> None:
    """Push written files to the Kindle before the user unplugs it.

    Windows has no os.sync. There every file is already closed, and Windows mounts USB drives for
    quick removal (no write cache) by default; ejecting first covers the rest.
    """
    sync = getattr(os, 'sync', None)
    if sync is None:
        log.debug('no os.sync on this system; relying on closed files and eject')
        return
    log.debug('syncing writes to disk')
    sync()


# Kept by --wipe-books: KUAL itself, and the Kindle's built-in dictionaries.
KEEP_IN_DOCUMENTS = frozenset({KUAL_FILE.lower(), 'dictionaries'})


def list_books(mount: Path) -> list[Path]:
    """Top-level entries of documents/ that --wipe-books would delete (books, .sdr sidecars, logs)."""
    docs = mount / 'documents'
    if not docs.is_dir():
        return []
    return sorted(p for p in docs.iterdir() if p.name.lower() not in KEEP_IN_DOCUMENTS)


def wipe_books(mount: Path, entries: list[Path]) -> int:
    """Delete the given entries of documents/; return how many were removed.

    Every entry is re-checked to sit directly inside documents/ and not be a kept name, so a
    stale or tampered list cannot delete anything else.
    """
    docs = (mount / 'documents').resolve()
    removed = 0
    for entry in entries:
        if entry.parent.resolve() != docs or entry.name.lower() in KEEP_IN_DOCUMENTS:
            raise DeviceError(f'refusing to delete {entry}: not a book entry in {docs}')
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        elif entry.is_dir():
            shutil.rmtree(entry)
        else:
            log.debug('already gone: %s', entry)
            continue
        log.debug('deleted %s', entry)
        removed += 1
    flush()
    log.info('wiped %d entries from %s', removed, docs)
    return removed
