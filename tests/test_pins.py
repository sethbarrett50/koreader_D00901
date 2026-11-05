import pytest

from conftest import _pkg, _tar, _zip

from koreader_d00901 import pins, plan

ARCHIVES = {'jailbreak': ('jb.tar.xz', _tar), 'mkk': ('mkk.tar.xz', _tar), 'keystore': ('keystore.zip', _zip)}
ARCHIVES['usbnet'] = ('usb.zip', _zip)


@pytest.fixture
def full_kindle(kindle):
    """Rebuild the fake update packages with the members of every prefix and firmware range."""
    src = kindle.cache.parent / 'src'
    for key, (name, build) in ARCHIVES.items():
        members = {
            member: key.encode()
            for prefix in plan.VARIANTS
            for fw in plan.FIRMWARE_RANGES
            if (member := plan.select_files(fw, prefix, True)[key])
        }
        build(src / name, members)
        kindle.manifest[key].update(_pkg(src / name))
    return kindle


def test_all_pins_ok(full_kindle, capsys):
    assert pins.check_pins(full_kindle.cache) == []
    assert 'keystore: downloaded and verified' in capsys.readouterr().out


def test_missing_variant_member_is_reported(kindle):
    # The plain conftest packages only hold the B006 / 3.3-3.4 members.
    problems = pins.check_pins(kindle.cache)
    assert any(p.startswith('jailbreak:') and 'prefix B008' in p for p in problems)
    assert not any('prefix B006, firmware 3.3-3.4' in p for p in problems)


def test_checksum_drift_is_reported(full_kindle):
    full_kindle.manifest['kual']['sha256'] = '0' * 64
    problems = pins.check_pins(full_kindle.cache)
    assert len(problems) == 1
    assert problems[0].startswith('kual: sha256 mismatch')


def test_dead_url_fails_main(full_kindle, capsys):
    full_kindle.manifest['koreader']['url'] = (full_kindle.cache.parent / 'gone.zip').as_uri()
    assert pins.main(['--cache', str(full_kindle.cache)]) == 1
    err = capsys.readouterr().err
    assert '1 pin problem(s)' in err
    assert 'koreader: could not download' in err


def test_main_ok(full_kindle, capsys):
    assert pins.main(['--cache', str(full_kindle.cache)]) == 0
    assert 'All pinned packages' in capsys.readouterr().out
