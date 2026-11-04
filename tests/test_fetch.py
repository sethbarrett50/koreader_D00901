import hashlib
import io
import tarfile
import zipfile

import pytest

from k3_install import ChecksumError, UnsafeArchiveError, extract, fetch


def make_pkg(tmp_path, data=b"payload", sha=None):
    src = tmp_path / "src.bin"
    src.write_bytes(data)
    return {
        "url": src.as_uri(),
        "sha256": sha or hashlib.sha256(data).hexdigest(),
        "filename": "pkg.bin",
    }


def test_fetch_downloads_and_verifies(tmp_path):
    pkg = make_pkg(tmp_path)
    cache = tmp_path / "cache"
    out = fetch(pkg, cache)
    assert out == cache / "pkg.bin"
    assert out.read_bytes() == b"payload"
    assert not (cache / "pkg.bin.part").exists()


def test_fetch_mismatch_raises_and_cleans_up(tmp_path):
    pkg = make_pkg(tmp_path, sha="0" * 64)
    cache = tmp_path / "cache"
    with pytest.raises(ChecksumError) as exc:
        fetch(pkg, cache)
    assert "0" * 64 in str(exc.value)
    assert hashlib.sha256(b"payload").hexdigest() in str(exc.value)
    assert list(cache.iterdir()) == []


def test_fetch_cached_file_skips_network(tmp_path):
    pkg = make_pkg(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "pkg.bin").write_bytes(b"payload")
    pkg["url"] = (tmp_path / "missing.bin").as_uri()
    assert fetch(pkg, cache).read_bytes() == b"payload"


def test_fetch_bad_cache_is_redownloaded(tmp_path):
    pkg = make_pkg(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "pkg.bin").write_bytes(b"corrupt")
    assert fetch(pkg, cache).read_bytes() == b"payload"


def build_tar(path, entries):
    with tarfile.open(path, "w:xz") as tf:
        for name, kind, payload in entries:
            info = tarfile.TarInfo(name)
            if kind == "file":
                info.size = len(payload)
                tf.addfile(info, io.BytesIO(payload))
            else:
                info.type = tarfile.SYMTYPE if kind == "sym" else tarfile.LNKTYPE
                info.linkname = payload.decode()
                tf.addfile(info)


def build_zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, kind, payload in entries:
            info = zipfile.ZipInfo(name)
            if kind == "sym":
                info.external_attr = 0o120777 << 16
            zf.writestr(info, payload)


BUILDERS = [("a.tar.xz", build_tar), ("a.zip", build_zip)]


@pytest.mark.parametrize(("name", "build"), BUILDERS)
def test_extract_normal(tmp_path, name, build):
    arc = tmp_path / name
    build(arc, [("dir/hello.txt", "file", b"hi")])
    dest = tmp_path / "out"
    assert extract(arc, dest) == dest
    assert (dest / "dir" / "hello.txt").read_bytes() == b"hi"


@pytest.mark.parametrize(("name", "build"), BUILDERS)
@pytest.mark.parametrize(
    ("member", "kind", "payload"),
    [
        ("/etc/evil", "file", b"x"),
        ("a/../../evil", "file", b"x"),
        ("link", "sym", b"/etc/passwd"),
    ],
)
def test_extract_rejects_unsafe(tmp_path, name, build, member, kind, payload):
    arc = tmp_path / name
    build(arc, [("ok.txt", "file", b"ok"), (member, kind, payload)])
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(UnsafeArchiveError):
        extract(arc, dest)
    assert list(dest.iterdir()) == []


def test_extract_rejects_tar_hardlink(tmp_path):
    arc = tmp_path / "a.tar.xz"
    build_tar(arc, [("ok.txt", "file", b"ok"), ("hl", "hard", b"ok.txt")])
    dest = tmp_path / "out"
    dest.mkdir()
    with pytest.raises(UnsafeArchiveError):
        extract(arc, dest)
    assert list(dest.iterdir()) == []
