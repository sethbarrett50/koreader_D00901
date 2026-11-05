import builtins
import hashlib
import io
import shutil
import tarfile
import zipfile

import pytest

import k3_install

from k3_install import fetch, main, select_files

FW, PREFIX = '3.3-3.4', 'B006'
FILES = select_files(FW, PREFIX, True)


def _bin(key: str) -> str:
    member = FILES[key]
    assert member is not None
    return member.split('/')[-1]


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
def env(tmp_path, monkeypatch):
    src = tmp_path / 'src'
    src.mkdir()
    _tar(src / 'jb.tar.xz', {FILES['jailbreak']: b'jb'})
    _tar(src / 'mkk.tar.xz', {FILES['mkk']: b'mkk'})
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
        'kual': _pkg(src / 'kual.tar.xz'),
        'usbnet': _pkg(src / 'usb.zip'),
        'koreader': _pkg(src / 'koreader.zip'),
    }
    monkeypatch.setattr(k3_install, 'load_manifest', lambda: manifest)
    mount = tmp_path / 'mount'
    (mount / 'documents').mkdir(parents=True)
    (mount / 'documents' / 'keep.txt').write_text('mine')
    (mount / 'Update_stale.bin').write_bytes(b'old')
    seen = []

    def fake_input(prompt=''):
        seen.append(sorted(p.name for p in mount.glob('Update_*.bin')))
        return ''

    monkeypatch.setattr(builtins, 'input', fake_input)

    def args(*extra):
        return [
            "--mount", str(mount), "--fw", FW, "--prefix", PREFIX,
            "--cache", str(tmp_path / "cache"), *extra,
        ]  # fmt: skip

    return mount, args, seen


def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in sorted(root.rglob('*'))}


def test_full_install_layout_and_single_bin(env):
    mount, args, seen = env
    assert main(args()) == 0
    assert seen == [[_bin('jailbreak')], [_bin('mkk')]]
    assert (mount / 'documents' / 'KUAL-KDK-1.0.azw2').read_bytes() == b'kual'
    assert (mount / 'documents' / 'keep.txt').read_text() == 'mine'
    assert (mount / 'koreader' / 'koreader.sh').is_file()
    assert (mount / 'extensions' / 'koreader' / 'menu.json').is_file()
    assert (mount / 'launchpad' / 'boot.sh').is_file()


def test_usbnet_adds_one_step(env):
    _mount, args, seen = env
    main(args('--usbnet'))
    assert len(seen) == 3
    assert all(len(s) <= 1 for s in seen)
    assert seen[2] == [_bin('usbnet')]


def test_device_steps_mention_eject():
    assert 'eject' in k3_install.DEVICE_STEPS.lower()


def test_waits_for_remount(env, monkeypatch):
    mount, args, _seen = env
    prompts = []

    def fake_input(prompt=''):
        prompts.append(prompt)
        if len(prompts) == 1:
            shutil.move(mount, mount.parent / 'away')
        elif len(prompts) == 2:
            shutil.move(mount.parent / 'away', mount)
        return ''

    monkeypatch.setattr(builtins, 'input', fake_input)
    assert main(args()) == 0
    assert len(prompts) == 3
    assert 'not mounted' in prompts[1]


def test_dry_run_changes_nothing_and_does_not_fetch(env, monkeypatch):
    mount, args, seen = env
    before = _snapshot(mount)

    def boom(*a, **k):
        raise AssertionError('fetch called')

    monkeypatch.setattr(k3_install, 'fetch', boom)
    assert main(args('--dry-run')) == 0
    assert _snapshot(mount) == before
    assert seen == []


def test_bad_prefix_exits_before_copying(env):
    mount, args, _seen = env
    before = _snapshot(mount)
    argv = args()
    argv[argv.index(PREFIX)] = 'ZZZZ'
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code not in (0, None)
    assert _snapshot(mount) == before


def test_prompts_reprompt_on_bad_input(env, monkeypatch):
    mount, _args, _seen = env
    answers = iter(['9.9', FW, 'nope', PREFIX])
    monkeypatch.setattr(builtins, 'input', lambda prompt='': next(answers))
    argv = ['--mount', str(mount), '--cache', str(mount.parent / 'cache')]
    assert main(argv + ['--dry-run']) == 0


@pytest.mark.parametrize('name', ['a/b', 'a\\b', '.', '..', '/abs', '', 'C:\\x'])
def test_fetch_rejects_non_bare_filename(tmp_path, name):
    pkg = {'url': 'file:///nonexistent', 'sha256': '0' * 64, 'filename': name}
    cache = tmp_path / 'cache'
    with pytest.raises(ValueError):
        fetch(pkg, cache)
    assert not cache.exists()
