"""Everything that touches the Kindle's USB volume."""

import logging
import os
import shutil
import subprocess

from collections.abc import Callable
from pathlib import Path

from koreader_d00901.errors import DeviceError
from koreader_d00901.plan import KOREADER_TREES

log = logging.getLogger(__name__)

# K3 update packages are named Update_*.bin or Update-*.bin (the 2025 keystore uses a hyphen).
UPDATE_GLOB = 'Update[-_]*.bin'


def _findmnt(*args: str) -> str:
    try:
        result = subprocess.run(['findmnt', '-rn', *args], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise DeviceError(f'could not run findmnt ({exc}); pass the mount point explicitly') from exc
    log.debug('findmnt %s -> rc=%d stdout=%r', ' '.join(args), result.returncode, result.stdout)
    return result.stdout


def find_mount() -> Path | None:
    """Return the mount point of the volume labelled Kindle, or None."""
    targets = _findmnt('-S', 'LABEL=Kindle', '-o', 'TARGET').split()
    return Path(targets[0]) if targets else None


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


def eject(mount: Path) -> str:
    """Unmount the block device behind mount with udisksctl and return its message."""
    source = _findmnt('-o', 'SOURCE', '--mountpoint', str(mount)).strip()
    if not source:
        raise DeviceError(f'nothing is mounted at {mount}')
    try:
        result = subprocess.run(['udisksctl', 'unmount', '-b', source], capture_output=True, text=True, check=False)
    except OSError as exc:
        raise DeviceError(f'could not run udisksctl ({exc}); eject the Kindle from your file manager') from exc
    log.debug('udisksctl unmount -b %s -> rc=%d %r %r', source, result.returncode, result.stdout, result.stderr)
    if result.returncode != 0:
        raise DeviceError(result.stderr.strip() or f'udisksctl unmount -b {source} failed')
    return result.stdout.strip()


def stage_update(mount: Path, bin_path: Path) -> None:
    """Leave bin_path as the only update package at the Kindle root, flushed to disk."""
    for old in mount.glob(UPDATE_GLOB):
        log.debug('removing old update package %s', old)
        old.unlink()
    shutil.copy2(bin_path, mount / bin_path.name)
    os.sync()
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
    log.debug('syncing writes to disk')
    os.sync()
