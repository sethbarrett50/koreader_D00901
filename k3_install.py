# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Install KOReader on a Kindle Keyboard (K3)."""

import hashlib
import json
import stat
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

VARIANTS = {"B006": "k3g", "B008": "k3w", "B00A": "k3gb"}
FIRMWARE_RANGES = ("3.0-3.2", "3.3-3.4")


def load_manifest() -> dict[str, dict[str, str]]:
    return json.loads((Path(__file__).parent / "packages.json").read_text())


def select_files(fw: str, prefix: str, usbnet: bool) -> dict[str, str | None]:
    """Map a firmware range and serial prefix to the archive members to install."""
    prefix = prefix.upper()
    if prefix not in VARIANTS:
        raise ValueError(f"unsupported serial prefix: {prefix!r}")
    if fw not in FIRMWARE_RANGES:
        raise ValueError(f"unsupported firmware range: {fw!r}")
    variant = VARIANTS[prefix]
    suffix = "-3.0-to-3.2" if fw == "3.0-3.2" else ""
    return {
        "jailbreak": f"Jailbreak/Update_jailbreak_0.13.N_{variant}{suffix}_install.bin",
        "mkk": f"DevCerts/Update_mkk-20141129-{variant}-{prefix}_install.bin",
        "usbnet": f"Update_usbnetwork_0.57.N_{variant}_install.bin" if usbnet else None,
        "kual": "KUAL-KDK-1.0.azw2",
    }


class ChecksumError(ValueError):
    """Downloaded or cached bytes do not match the manifest sha256."""


class UnsafeArchiveError(ValueError):
    """Archive member would escape the destination or is a link."""


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(pkg: dict[str, str], cache_dir: Path) -> Path:
    """Download pkg into cache_dir, accepting it only on an exact sha256 match."""
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    final = cache_dir / pkg["filename"]
    expected = pkg["sha256"].lower()
    if final.exists():
        if _sha256_of(final) == expected:
            return final
        final.unlink()
    part = final.with_name(final.name + ".part")
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(pkg["url"]) as resp, part.open("wb") as out:
            while chunk := resp.read(1 << 20):
                digest.update(chunk)
                out.write(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise ChecksumError(
                f"sha256 mismatch for {pkg['filename']}: "
                f"expected {expected}, got {actual}"
            )
        part.replace(final)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return final


def _check_name(name: str) -> None:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or (len(name) > 1 and name[1] == ":"):
        raise UnsafeArchiveError(f"unsafe archive member path: {name!r}")


def extract(archive: Path, dest: Path) -> Path:
    """Unpack a .tar.xz or .zip into dest after vetting every member first."""
    archive, dest = Path(archive), Path(dest)
    if archive.name.endswith(".tar.xz"):
        with tarfile.open(archive, "r:xz") as tf:
            members = tf.getmembers()
            for m in members:
                _check_name(m.name)
                if m.issym() or m.islnk():
                    raise UnsafeArchiveError(f"link member not allowed: {m.name!r}")
                if not (m.isfile() or m.isdir()):
                    raise UnsafeArchiveError(f"special member not allowed: {m.name!r}")
            dest.mkdir(parents=True, exist_ok=True)
            tf.extractall(dest, members=members, filter="data")
    elif archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            for info in infos:
                _check_name(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise UnsafeArchiveError(
                        f"link member not allowed: {info.filename!r}"
                    )
            dest.mkdir(parents=True, exist_ok=True)
            zf.extractall(dest, members=infos)
    else:
        raise ValueError(f"unsupported archive type: {archive.name!r}")
    return dest
