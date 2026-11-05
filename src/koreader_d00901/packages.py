"""Download, verify and unpack the pinned upstream packages. Nothing downloaded is ever executed."""

import hashlib
import json
import logging
import stat
import tarfile
import urllib.error
import urllib.request
import zipfile

from importlib.resources import files
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from koreader_d00901.errors import ChecksumError, PackageError, UnsafeArchiveError

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger(__name__)

Manifest = dict[str, dict[str, str]]


def load_manifest() -> Manifest:
    """The pinned packages (url, sha256, filename) shipped with this package."""
    return json.loads(files('koreader_d00901').joinpath('packages.json').read_text(encoding='utf-8'))


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _check_filename(name: str) -> None:
    if (
        '/' in name
        or '\\' in name
        or name in ('', '.', '..')
        or PurePosixPath(name).is_absolute()
        or Path(name).is_absolute()
    ):
        raise UnsafeArchiveError(f'unsafe package filename: {name!r}')


def fetch(pkg: dict[str, str], cache_dir: Path) -> Path:
    """Download pkg into cache_dir, accepting it only on an exact sha256 match."""
    name = pkg['filename']
    _check_filename(name)
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    final = cache_dir / name
    expected = pkg['sha256'].lower()
    if final.exists():
        if _sha256_of(final) == expected:
            log.debug('cache hit for %s', final)
            return final
        log.warning('cached %s does not match its pinned sha256; downloading it again', name)
        final.unlink()
    part = final.with_name(final.name + '.part')
    digest = hashlib.sha256()
    log.debug('downloading %s from %s', name, pkg['url'])
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
            raise ChecksumError(f'sha256 mismatch for {name}: expected {expected}, got {actual}')
        part.replace(final)
    except (urllib.error.URLError, TimeoutError) as exc:
        part.unlink(missing_ok=True)
        raise PackageError(f'could not download {name} from {pkg["url"]}: {exc}') from exc
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    log.debug('verified %s (sha256 %s)', name, actual)
    return final


def _check_member(name: str) -> None:
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
                _check_member(m.name)
                if m.issym() or m.islnk():
                    raise UnsafeArchiveError(f'link member not allowed: {m.name!r}')
                if not (m.isfile() or m.isdir()):
                    raise UnsafeArchiveError(f'special member not allowed: {m.name!r}')
            dest.mkdir(parents=True, exist_ok=True)
            tf.extractall(dest, members=members, filter='data')
            count = len(members)
    elif archive.name.endswith('.zip'):
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            for info in infos:
                _check_member(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise UnsafeArchiveError(f'link member not allowed: {info.filename!r}')
            dest.mkdir(parents=True, exist_ok=True)
            zf.extractall(dest, members=infos)
            count = len(infos)
    else:
        raise PackageError(f'unsupported archive type: {archive.name!r}')
    log.debug('extracted %d members of %s into %s', count, archive.name, dest)
    return dest


def fetch_packages(
    keys: list[str],
    cache: Path,
    on_package: Callable[[str], None] | None = None,
) -> dict[str, Path]:
    """Fetch and extract each manifest package; return its extracted root by key."""
    manifest = load_manifest()
    roots: dict[str, Path] = {}
    for key in keys:
        if key not in manifest:
            raise PackageError(f'package {key!r} is not pinned in packages.json')
        if on_package is not None:
            on_package(manifest[key]['filename'])
        roots[key] = extract(fetch(manifest[key], cache), cache / key)
    return roots


def member_path(root: Path, member: str | None) -> Path:
    """The extracted file for one install step, which must exist."""
    if member is None:
        raise PackageError('no archive member selected for this step')
    path = root / member
    if not path.is_file():
        raise PackageError(f'{member} not found in downloaded package {root}')
    return path
