# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Install KOReader on a Kindle Keyboard (K3)."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

from pathlib import Path, PurePosixPath

VARIANTS = {'B006': 'k3g', 'B008': 'k3w', 'B00A': 'k3gb'}
FIRMWARE_RANGES = ('3.0-3.2', '3.3-3.4')


def load_manifest() -> dict[str, dict[str, str]]:
    return json.loads((Path(__file__).parent / 'packages.json').read_text())


def select_files(fw: str, prefix: str, usbnet: bool) -> dict[str, str | None]:
    """Map a firmware range and serial prefix to the archive members to install."""
    prefix = prefix.upper()
    if prefix not in VARIANTS:
        raise ValueError(f'unsupported serial prefix: {prefix!r}')
    if fw not in FIRMWARE_RANGES:
        raise ValueError(f'unsupported firmware range: {fw!r}')
    variant = VARIANTS[prefix]
    suffix = '-3.0-to-3.2' if fw == '3.0-3.2' else ''
    return {
        'jailbreak': f'Jailbreak/Update_jailbreak_0.13.N_{variant}{suffix}_install.bin',
        'mkk': f'DevCerts/Update_mkk-20141129-{variant}-{prefix}_install.bin',
        'keystore': f'Update-mkk-20250419-{variant}-{prefix}_keystore-install.bin',
        'usbnet': f'Update_usbnetwork_0.57.N_{variant}_install.bin' if usbnet else None,
        'kual': 'KUAL-KDK-1.0.azw2',
    }


class ChecksumError(ValueError):
    """Downloaded or cached bytes do not match the manifest sha256."""


class UnsafeArchiveError(ValueError):
    """Archive member would escape the destination or is a link."""


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(pkg: dict[str, str], cache_dir: Path) -> Path:
    """Download pkg into cache_dir, accepting it only on an exact sha256 match."""
    name = pkg['filename']
    if (
        '/' in name
        or '\\' in name
        or name in ('', '.', '..')
        or PurePosixPath(name).is_absolute()
        or Path(name).is_absolute()
    ):
        raise ValueError(f'unsafe package filename: {name!r}')
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    final = cache_dir / pkg['filename']
    expected = pkg['sha256'].lower()
    if final.exists():
        if _sha256_of(final) == expected:
            return final
        final.unlink()
    part = final.with_name(final.name + '.part')
    digest = hashlib.sha256()
    try:
        with (
            urllib.request.urlopen(pkg['url'], timeout=60) as resp,
            part.open('wb') as out,
        ):
            while chunk := resp.read(1 << 20):
                digest.update(chunk)
                out.write(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise ChecksumError(f'sha256 mismatch for {pkg["filename"]}: expected {expected}, got {actual}')
        part.replace(final)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return final


def _check_name(name: str) -> None:
    path = PurePosixPath(name.replace('\\', '/'))
    if path.is_absolute() or '..' in path.parts or (len(name) > 1 and name[1] == ':'):
        raise UnsafeArchiveError(f'unsafe archive member path: {name!r}')


def extract(archive: Path, dest: Path) -> Path:
    """Unpack a .tar.xz or .zip into dest after vetting every member first."""
    archive, dest = Path(archive), Path(dest)
    if archive.name.endswith('.tar.xz'):
        with tarfile.open(archive, 'r:xz') as tf:
            members = tf.getmembers()
            for m in members:
                _check_name(m.name)
                if m.issym() or m.islnk():
                    raise UnsafeArchiveError(f'link member not allowed: {m.name!r}')
                if not (m.isfile() or m.isdir()):
                    raise UnsafeArchiveError(f'special member not allowed: {m.name!r}')
            dest.mkdir(parents=True, exist_ok=True)
            tf.extractall(dest, members=members, filter='data')
    elif archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            for info in infos:
                _check_name(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise UnsafeArchiveError(f'link member not allowed: {info.filename!r}')
            dest.mkdir(parents=True, exist_ok=True)
            zf.extractall(dest, members=infos)
    else:
        raise ValueError(f'unsupported archive type: {archive.name!r}')
    return dest


UPDATE_STEPS = (
    ('jailbreak', 'jailbreak'),
    ('mkk', 'MKK (developer certificates)'),
    ('keystore', '2025 developer keystore (needed to launch KUAL)'),
    ('usbnet', 'USBNetwork'),
)
# K3 update packages are named Update_*.bin or Update-*.bin (the 2025 keystore uses a hyphen).
UPDATE_GLOB = 'Update[-_]*.bin'
DEVICE_STEPS = (
    '  First safely eject (unmount) the Kindle and unplug it from the computer;\n'
    '  the update cannot run while it is in USB drive mode.\n'
    '  Then on the Kindle: [HOME] > [MENU] > Settings > [MENU] > Update Your Kindle.\n'
    '  Never reboot the Kindle by hand to force the update.\n'
    "  If 'Update Your Kindle' is greyed out, the wrong file was staged."
)


def _default_mount() -> Path:
    try:
        out = subprocess.run(
            ['findmnt', '-rn', '-S', 'LABEL=Kindle', '-o', 'TARGET'],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        out = ''
    targets = out.split()
    if not targets:
        raise SystemExit(
            'error: no mounted volume labelled Kindle found; connect the Kindle in USB drive mode or pass --mount PATH'
        )
    return Path(targets[0])


def _ask_valid(prompt: str, value: str | None, check, flag: str) -> str:
    """Validate a flag value (fatal when bad) or prompt until one validates."""
    if value is not None:
        try:
            check(value)
        except ValueError as exc:
            raise SystemExit(f'error: {flag}: {exc}') from None
        return value
    while True:
        answer = input(prompt).strip()
        try:
            check(answer)
        except ValueError as exc:
            print(f'  {exc}')
            continue
        return answer


def _member(root: Path, member: str | None) -> Path:
    if member is None:
        raise ValueError('no archive member selected for this step')
    path = root / member
    if not path.is_file():
        raise SystemExit(f'error: {member} not found in downloaded package {root}')
    return path


def _copy_with_progress(pairs: list[tuple[Path, Path]], label: str) -> None:
    """Copy (src, dst) file pairs, printing a running count so slow USB writes don't look hung."""
    total = len(pairs)
    every = max(1, total // 100)
    for i, (src, dst) in enumerate(pairs, 1):
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if i % every == 0 or i == total:
            print(f'\r  {label}: {i}/{total} files', end='', flush=True)
    print()


def _update_step(mount: Path, bin_path: Path, label: str) -> None:
    for old in mount.glob(UPDATE_GLOB):
        old.unlink()
    shutil.copy2(bin_path, mount / bin_path.name)
    os.sync()
    print(f'\nStaged {bin_path.name} ({label}).')
    print(DEVICE_STEPS)
    input('Press Enter once the Kindle has rebooted and remounted... ')
    while not mount.is_dir():
        input(f'Kindle not mounted at {mount} yet; reconnect it in USB drive mode and press Enter... ')
    if (mount / bin_path.name).exists():
        print(f'warning: {bin_path.name} is still at the Kindle root; the update may not have applied.')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Install KOReader on a Kindle K3.')
    parser.add_argument('--mount', type=Path, help='Kindle USB mount point')
    parser.add_argument('--fw', help='firmware range: ' + ', '.join(FIRMWARE_RANGES))
    parser.add_argument('--prefix', help='serial prefix: ' + ', '.join(VARIANTS))
    parser.add_argument('--usbnet', action='store_true', help='also install USBNetwork')
    parser.add_argument('--cache', type=Path, default=Path('~/.cache/k3-koreader').expanduser())
    parser.add_argument('--dry-run', action='store_true', help='print the plan only')
    args = parser.parse_args(argv)

    fw = _ask_valid(
        f'Firmware range ({"/".join(FIRMWARE_RANGES)}): ',
        args.fw,
        lambda v: select_files(v, 'B006', False),
        '--fw',
    )
    prefix = _ask_valid(
        f'Serial prefix ({"/".join(VARIANTS)}): ',
        args.prefix,
        lambda v: select_files(fw, v, False),
        '--prefix',
    )
    files = select_files(fw, prefix, args.usbnet)
    mount = args.mount if args.mount is not None else _default_mount()
    if not mount.is_dir():
        raise SystemExit(f'error: mount point {mount} is not a directory')
    steps = [(k, label) for k, label in UPDATE_STEPS if files[k]]

    if args.dry_run:
        print(f'Dry run: mount={mount} firmware={fw} prefix={prefix.upper()}')
        for key, label in steps:
            print(f'  would stage {files[key]} ({label})')
        print('  would copy KUAL-KDK-1.0.azw2 into documents/')
        print('  would merge koreader/, extensions/, launchpad/ into the mount root')
        return 0

    manifest = load_manifest()
    roots: dict[str, Path] = {}
    needed = [k for k, _ in steps] + ['kual', 'koreader']
    print('Getting packages (cached after the first run):')
    for key in needed:
        print(f'  {manifest[key]["filename"]}', flush=True)
        archive = fetch(manifest[key], args.cache)
        roots[key] = extract(archive, args.cache / key)

    bins = [(_member(roots[k], files[k]), label) for k, label in steps]
    kual = _member(roots['kual'], files['kual'])
    for bin_path, label in bins:
        _update_step(mount, bin_path, label)

    print(f'\nCopying {kual.name} to documents/')
    (mount / 'documents').mkdir(exist_ok=True)
    shutil.copy2(kual, mount / 'documents' / kual.name)

    ko_root = roots['koreader']
    pairs = [
        (f, mount / f.relative_to(ko_root))
        for tree in ('koreader', 'extensions', 'launchpad')
        if (ko_root / tree).is_dir()
        for f in sorted((ko_root / tree).rglob('*'))
        if f.is_file()
    ]
    size_mb = sum(src.stat().st_size for src, _ in pairs) / 1e6
    print(
        f'Copying KOReader ({len(pairs)} files, {size_mb:.0f} MB). '
        'This takes several minutes on a K3; leave it plugged in.'
    )
    _copy_with_progress(pairs, 'KOReader')
    print('Flushing writes to the Kindle...', flush=True)
    os.sync()
    print('\nDone. Eject the Kindle, then on the device open the KUAL book in your library and choose KOReader.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
