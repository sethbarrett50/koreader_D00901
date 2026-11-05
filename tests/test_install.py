import builtins
import shutil

import pytest

from conftest import FILES, FW, PREFIX

from koreader_d00901 import cli, device, packages
from koreader_d00901.cli import main
from koreader_d00901.packages import fetch


def _bin(key: str) -> str:
    member = FILES[key]
    assert member is not None
    return member.split('/')[-1]


@pytest.fixture
def env(kindle, monkeypatch):
    mount = kindle.mount
    seen = []

    def fake_input(prompt=''):
        seen.append(sorted(p.name for p in mount.glob(device.UPDATE_GLOB)))
        return ''

    monkeypatch.setattr(builtins, 'input', fake_input)

    def args(*extra):
        return [
            "--mount", str(mount), "--fw", FW, "--prefix", PREFIX,
            "--cache", str(kindle.cache), *extra,
        ]  # fmt: skip

    return mount, args, seen


def _snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() if p.is_file() else None for p in sorted(root.rglob('*'))}


def test_full_install_layout_and_single_bin(env, capsys):
    mount, args, seen = env
    assert main(args()) == 0
    out = capsys.readouterr().out
    assert 'Copying KUAL-KDK-1.0.azw2 to documents/' in out
    assert 'Copying KOReader (' in out
    n = sum(1 for t in ('koreader', 'extensions', 'launchpad') for f in (mount / t).rglob('*') if f.is_file())
    assert f'KOReader: {n}/{n} files' in out
    assert 'Flushing writes to the Kindle' in out
    assert seen == [[_bin('jailbreak')], [_bin('mkk')], [_bin('keystore')]]
    assert (mount / 'documents' / 'KUAL-KDK-1.0.azw2').read_bytes() == b'kual'
    assert (mount / 'documents' / 'keep.txt').read_text() == 'mine'
    assert (mount / 'koreader' / 'koreader.sh').is_file()
    assert (mount / 'extensions' / 'koreader' / 'menu.json').is_file()
    assert (mount / 'launchpad' / 'boot.sh').is_file()


def test_usbnet_adds_one_step(env):
    _mount, args, seen = env
    main(args('--usbnet'))
    assert len(seen) == 4
    assert all(len(s) <= 1 for s in seen)
    assert seen[3] == [_bin('usbnet')]


def test_device_steps_mention_eject():
    assert 'eject' in cli.DEVICE_STEPS.lower()


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
    assert len(prompts) == 4
    assert 'not mounted' in prompts[1]


def test_dry_run_changes_nothing_and_does_not_fetch(env, monkeypatch):
    mount, args, seen = env
    before = _snapshot(mount)

    def boom(*a, **k):
        raise AssertionError('fetch called')

    monkeypatch.setattr(packages, 'fetch', boom)
    assert main(args('--dry-run')) == 0
    assert _snapshot(mount) == before
    assert seen == []


def test_bad_prefix_exits_before_copying(env, capsys):
    mount, args, _seen = env
    before = _snapshot(mount)
    argv = args()
    argv[argv.index(PREFIX)] = 'ZZZZ'
    assert main(argv) == 1
    assert 'error: --prefix: unsupported serial prefix' in capsys.readouterr().err
    assert _snapshot(mount) == before


def test_missing_kindle_is_a_clean_error(kindle, monkeypatch, capsys):
    monkeypatch.setattr(device, 'find_mount', lambda: None)
    argv = ['--fw', FW, '--prefix', PREFIX, '--cache', str(kindle.cache)]
    assert main(argv) == 1
    assert 'no mounted volume labelled Kindle' in capsys.readouterr().err


def test_download_failure_is_a_clean_error_and_logged(env, kindle, capsys):
    _mount, args, _seen = env
    kindle.manifest['jailbreak']['url'] = (kindle.cache.parent / 'gone.tar.xz').as_uri()
    assert main(args()) == 1
    err = capsys.readouterr().err
    assert 'could not download' in err
    log_text = (kindle.cache / 'install.log').read_text()
    assert 'DEBUG' in log_text
    assert 'install failed' in log_text
    assert 'Traceback' in log_text


def test_verbose_logs_debug_to_console(env, capsys):
    _mount, args, _seen = env
    assert main(args('--dry-run', '--verbose')) == 0
    assert 'DEBUG: plan:' in capsys.readouterr().err


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


def test_only_usbnet_stages_just_usbnet(env, capsys):
    mount, args, seen = env
    assert main(args('--only', 'usbnet')) == 0
    assert seen == [[_bin('usbnet')]]
    assert not (mount / 'koreader').exists()
    assert not (mount / 'documents' / 'KUAL-KDK-1.0.azw2').exists()
    assert 'Done with the selected steps' in capsys.readouterr().out


def test_only_keystore_and_koreader(env):
    mount, args, seen = env
    assert main(args('--only', 'keystore', '--only', 'koreader')) == 0
    assert seen == [[_bin('keystore')]]
    assert (mount / 'koreader' / 'koreader.sh').is_file()
    assert not (mount / 'documents' / 'KUAL-KDK-1.0.azw2').exists()


def test_only_rejects_unknown_step(env):
    _mount, args, _seen = env
    with pytest.raises(SystemExit):
        main(args('--only', 'firmware'))
