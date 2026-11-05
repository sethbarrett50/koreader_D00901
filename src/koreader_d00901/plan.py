"""Which files a given K3 needs: serial prefix and firmware range to package members."""

from typing import TYPE_CHECKING

from koreader_d00901.errors import ConfigError

if TYPE_CHECKING:
    from collections.abc import Iterable

VARIANTS = {'B006': 'k3g', 'B008': 'k3w', 'B00A': 'k3gb'}
FIRMWARE_RANGES = ('3.0-3.2', '3.3-3.4')

# Update packages applied through Settings > Update Your Kindle, in order.
UPDATE_STEPS = (
    ('jailbreak', 'jailbreak'),
    ('mkk', 'MKK (developer certificates)'),
    ('keystore', '2025 developer keystore (needed to launch KUAL)'),
    ('usbnet', 'USBNetwork'),
)
KUAL_FILE = 'KUAL-KDK-1.0.azw2'
KOREADER_TREES = ('koreader', 'extensions', 'launchpad')


def check_prefix(prefix: str) -> str:
    """Return the normalised serial prefix or raise ConfigError."""
    prefix = prefix.strip().upper()
    if prefix not in VARIANTS:
        raise ConfigError(f'unsupported serial prefix: {prefix!r} (expected one of {", ".join(VARIANTS)})')
    return prefix


def check_firmware(fw: str) -> str:
    """Return the firmware range or raise ConfigError."""
    fw = fw.strip()
    if fw not in FIRMWARE_RANGES:
        raise ConfigError(f'unsupported firmware range: {fw!r} (expected one of {", ".join(FIRMWARE_RANGES)})')
    return fw


def select_files(fw: str, prefix: str, usbnet: bool) -> dict[str, str | None]:
    """Map a firmware range and serial prefix to the archive members to install."""
    prefix = check_prefix(prefix)
    fw = check_firmware(fw)
    variant = VARIANTS[prefix]
    suffix = '-3.0-to-3.2' if fw == '3.0-3.2' else ''
    return {
        'jailbreak': f'Jailbreak/Update_jailbreak_0.13.N_{variant}{suffix}_install.bin',
        'mkk': f'DevCerts/Update_mkk-20141129-{variant}-{prefix}_install.bin',
        'keystore': f'Update-mkk-20250419-{variant}-{prefix}_keystore-install.bin',
        'usbnet': f'Update_usbnetwork_0.57.N_{variant}_install.bin' if usbnet else None,
        'kual': KUAL_FILE,
    }


def update_steps(files: dict[str, str | None]) -> list[tuple[str, str]]:
    """The (key, label) update steps to run, in order, for a select_files() result."""
    return [(key, label) for key, label in UPDATE_STEPS if files[key]]


def package_keys(files: dict[str, str | None]) -> list[str]:
    """Every manifest package this install needs, in install order."""
    return [key for key, _ in update_steps(files)] + ['kual', 'koreader']


# Every step either front end can run, in order, with a short label. USBNetwork and the Grafana
# status display are off unless asked for.
STEP_LABELS = {
    'jailbreak': 'Jailbreak',
    'mkk': 'MKK certificates',
    'keystore': '2025 keystore',
    'usbnet': 'USBNetwork (SSH)',
    'kual': 'KUAL',
    'koreader': 'KOReader',
    'feeds': 'News feed list',
    'dashboard': 'Grafana status display',
}
OPT_IN_STEPS = ('usbnet', 'dashboard')
ALL_STEPS = tuple(STEP_LABELS)


def selected_steps(only: Iterable[str] | None = None, usbnet: bool = False, dashboard: bool = False) -> frozenset[str]:
    """The steps to run: exactly `only` when given (--only), else every step except the opt-in ones not asked for."""
    asked = {step for step, wanted in (('usbnet', usbnet), ('dashboard', dashboard)) if wanted}
    if only:
        unknown = set(only) - set(ALL_STEPS)
        if unknown:
            raise ConfigError(f'unknown step(s): {", ".join(sorted(unknown))}')
        return frozenset(only) | asked
    return frozenset(step for step in ALL_STEPS if step not in OPT_IN_STEPS or step in asked)
