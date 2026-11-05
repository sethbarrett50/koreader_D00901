import hashlib
import io
import tarfile
import zipfile

from types import SimpleNamespace

import pytest

from koreader_d00901 import packages, plan

FW, PREFIX = '3.3-3.4', 'B006'
FILES = plan.select_files(FW, PREFIX, True)


def _tar(path, members):
    with tarfile.open(path, 'w:xz') as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def _zip(path, members):
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in members.items():
            zf.writestr(name, data)


def _pkg(path):
    return {
        'url': path.as_uri(),
        'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'filename': path.name,
    }


@pytest.fixture
def kindle(tmp_path, monkeypatch):
    """A fake mounted Kindle plus file:// packages wired into load_manifest."""
    src = tmp_path / 'src'
    src.mkdir()
    _tar(src / 'jb.tar.xz', {FILES['jailbreak']: b'jb'})
    _tar(src / 'mkk.tar.xz', {FILES['mkk']: b'mkk'})
    _zip(src / 'keystore.zip', {FILES['keystore']: b'ks'})
    _tar(src / 'kual.tar.xz', {'KUAL-KDK-1.0.azw2': b'kual'})
    _zip(src / 'usb.zip', {FILES['usbnet']: b'usb'})
    _zip(
        src / 'koreader.zip',
        {
            'koreader/koreader.sh': b'sh',
            'extensions/koreader/menu.json': b'{}',
            'launchpad/boot.sh': b'b',
        },
    )
    manifest = {
        'jailbreak': _pkg(src / 'jb.tar.xz'),
        'mkk': _pkg(src / 'mkk.tar.xz'),
        'keystore': _pkg(src / 'keystore.zip'),
        'kual': _pkg(src / 'kual.tar.xz'),
        'usbnet': _pkg(src / 'usb.zip'),
        'koreader': _pkg(src / 'koreader.zip'),
    }
    monkeypatch.setattr(packages, 'load_manifest', lambda: manifest)
    mount = tmp_path / 'mount'
    (mount / 'documents').mkdir(parents=True)
    (mount / 'documents' / 'keep.txt').write_text('mine')
    (mount / 'Update_stale.bin').write_bytes(b'old')
    (mount / 'Update-stale.bin').write_bytes(b'old')
    return SimpleNamespace(mount=mount, cache=tmp_path / 'cache', manifest=manifest)
