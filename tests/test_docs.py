import json
import re
import tomllib

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / 'docs'
README = (ROOT / 'README.md').read_text(encoding='utf-8')
INSTALL = (DOCS / 'install.md').read_text(encoding='utf-8')


def section(text: str, title: str) -> str:
    match = re.search(rf'^## {re.escape(title)}\n(.*?)(?=^## |\Z)', text, re.MULTILINE | re.DOTALL)
    assert match, f'missing section: {title}'
    return match.group(1)


INSTALL_REQUIRED = {
    'What gets installed': ['Jailbreak', 'MKK', '2025 developer keystore', 'USBNetwork', 'KUAL', 'KOReader'],
    'Before you start': [
        'Charge',
        'Settings > Registration',
        'wireless off',
        'bottom of the Settings',
        'serial prefix',
    ],
    'Which files your Kindle needs': ['B006', 'k3g', 'B008', 'k3w', 'B00A', 'k3gb', '3.0-3.2', '3.3-3.4'],
    'Getting the installer': ['uv tool install koreader_D00901', 'uvx --from koreader_D00901', 'uv run'],
    'The full-screen installer (recommended)': ['koreader-d00901-tui', 'Eject Kindle', 'Continue', 'Dry run'],
    'The terminal installer': ['koreader-d00901 --dry-run', 'install.log'],
    'On the Kindle': [
        'Eject and unplug',
        '[HOME] > [MENU] > Settings > [MENU] > Update Your Kindle',
        'jailbreak, then MKK, then the 2025 keystore',
        'open KUAL from the library',
        'Start KOReader',
    ],
    'If something goes wrong': [
        'greyed out',
        'Never force',
        'about 15 seconds',
        'Reinstall MKK',
        'not signed by a registered developer',
        ';dumpMessages',
    ],
    'Pinned packages': [],
    'Credits': [
        'https://www.mobileread.com/forums/showthread.php?t=225030',
        'https://www.mobileread.com/forums/showthread.php?t=88004',
        'https://www.mobileread.com/forums/showthread.php?t=203326',
        'https://github.com/koreader/koreader',
    ],
}


@pytest.mark.parametrize('title', INSTALL_REQUIRED)
def test_install_section_has_required_text(title):
    body = section(INSTALL, title)
    for needle in INSTALL_REQUIRED[title]:
        assert needle in body, f'{title!r} lacks {needle!r}'


def test_usbnetwork_page():
    text = (DOCS / 'usbnetwork.md').read_text(encoding='utf-8')
    for needle in (
        ';debugOn',
        '~usbNetwork',
        ';debugOff',
        'ssh root@192.168.2.2',
        'ip addr add 192.168.2.1',
        'any password is accepted',
        'managed no',
        '--only usbnet',
    ):
        assert needle in text, needle


def test_mkk_description():
    assert 'run custom Kindlets' in INSTALL
    assert 'unsigned updates' not in INSTALL + README


def test_readme_is_short_with_risk_note_and_quickstart():
    assert len(README.splitlines()) <= 60
    assert 'at your own risk' in README[:500]
    quickstart = section(README, 'Quickstart')
    assert 'uv tool install koreader_D00901' in quickstart
    assert 'koreader-d00901-tui' in quickstart


def test_readme_links_are_absolute_and_cover_every_page():
    # The PyPI page is rendered from README.md, where relative links break.
    links = re.findall(r'\]\(([^)]+)\)', README)
    assert links
    assert all(link.startswith('https://') for link in links), links
    for page in (
        'docs/install.md',
        'docs/usbnetwork.md',
        'docs/battery.md',
        'docs/development.md',
        'docs/rss.md',
        'docs/dashboard.md',
        'CHANGELOG.md',
    ):
        assert any(link.endswith(page) for link in links), f'README does not link {page}'
        assert (ROOT / page).is_file(), page


def test_screenshot_exists():
    svg = (DOCS / 'tui.svg').read_text(encoding='utf-8')
    assert svg.lstrip().startswith('<svg')
    assert '/tmp' not in svg


def test_every_flag_documented():
    flags = set()
    for module in ('cli.py', 'battery.py'):
        source = (ROOT / 'src' / 'koreader_d00901' / module).read_text(encoding='utf-8')
        flags |= set(re.findall(r'add_argument\(\s*(?:[\'"]-\w[\'"],\s*)?[\'"](--[a-z-]+)[\'"]', source))
    assert {'--only', '--wipe-books', '--raw', '--note', '--verbose'} <= flags
    docs = INSTALL + (DOCS / 'battery.md').read_text(encoding='utf-8') + README
    for flag in flags - {'--host', '--user', '--log'}:
        assert flag in docs, f'flag {flag} not documented'


def test_pins_listed():
    manifest = json.loads((ROOT / 'src' / 'koreader_d00901' / 'packages.json').read_text(encoding='utf-8'))
    body = section(INSTALL, 'Pinned packages')
    for name, pkg in manifest.items():
        assert pkg['filename'] in body, f'{name} filename missing'
        assert pkg['sha256'][:12] in body, f'{name} sha256 prefix missing'


def test_changelog_has_current_version():
    version = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']['version']
    changelog = (ROOT / 'CHANGELOG.md').read_text(encoding='utf-8')
    assert f'## [{version}]' in changelog
    assert f'[{version}]: https://github.com/sethbarrett50/koreader_D00901/' in changelog


def test_release_steps_documented():
    text = (DOCS / 'development.md').read_text(encoding='utf-8')
    for needle in (
        '## Releasing',
        'release.yml',
        'trusted publisher',
        'environment named `pypi`',
        'git tag',
        'CHANGELOG.md',
    ):
        assert needle in text, f'development.md lacks {needle!r}'
