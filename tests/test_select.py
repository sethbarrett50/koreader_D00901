import json

from pathlib import Path

import pytest

from koreader_d00901 import packages, plan
from koreader_d00901.errors import ConfigError

VARIANTS = {'B006': 'k3g', 'B008': 'k3w', 'B00A': 'k3gb'}


@pytest.mark.parametrize('prefix,variant', VARIANTS.items())
@pytest.mark.parametrize('fw', ['3.3-3.4', '3.0-3.2'])
@pytest.mark.parametrize('usbnet', [True, False])
def test_select_files(prefix, variant, fw, usbnet):
    suffix = '-3.0-to-3.2' if fw == '3.0-3.2' else ''
    got = plan.select_files(fw, prefix, usbnet)
    assert got == {
        'jailbreak': f'Jailbreak/Update_jailbreak_0.13.N_{variant}{suffix}_install.bin',
        'mkk': f'DevCerts/Update_mkk-20141129-{variant}-{prefix}_install.bin',
        'keystore': f'Update-mkk-20250419-{variant}-{prefix}_keystore-install.bin',
        'usbnet': f'Update_usbnetwork_0.57.N_{variant}_install.bin' if usbnet else None,
        'kual': 'KUAL-KDK-1.0.azw2',
    }


def test_prefix_case_insensitive():
    assert plan.select_files('3.3-3.4', 'b00a', False) == plan.select_files('3.3-3.4', 'B00A', False)


@pytest.mark.parametrize('prefix', ['B009', '', 'B0', 'B006X'])
def test_bad_prefix(prefix):
    with pytest.raises(ConfigError):
        plan.select_files('3.3-3.4', prefix, False)


@pytest.mark.parametrize('fw', ['3.5', '', '3.0', '3.0-3.4'])
def test_bad_fw(fw):
    with pytest.raises(ConfigError):
        plan.select_files(fw, 'B006', False)


def test_manifest_keys():
    manifest = packages.load_manifest()
    assert set(manifest) == {'jailbreak', 'mkk', 'keystore', 'kual', 'usbnet', 'koreader'}
    for entry in manifest.values():
        assert set(entry) == {'url', 'sha256', 'filename'}
    path = Path(packages.__file__).parent / 'packages.json'
    assert json.loads(path.read_text()) == manifest
