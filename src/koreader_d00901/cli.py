"""Command-line installer: prompts on the terminal and waits for Enter between device updates."""

import argparse
import logging
import sys

from collections.abc import Callable
from pathlib import Path

from koreader_d00901 import __version__, device, packages, plan
from koreader_d00901.errors import ConfigError, InstallerError
from koreader_d00901.logs import DEFAULT_CACHE, setup_logging

log = logging.getLogger(__name__)

DEVICE_STEPS = (
    '  First safely eject (unmount) the Kindle and unplug it from the computer;\n'
    '  the update cannot run while it is in USB drive mode.\n'
    '  Then on the Kindle: [HOME] > [MENU] > Settings > [MENU] > Update Your Kindle.\n'
    '  Never reboot the Kindle by hand to force the update.\n'
    "  If 'Update Your Kindle' is greyed out, the wrong file was staged."
)
DONE_MESSAGE = 'Done. Eject the Kindle, then on the device open the KUAL book in your library and choose KOReader.'


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument('--mount', type=Path, help='Kindle USB mount point (auto-detected if omitted)')
    parser.add_argument('--fw', help='firmware range: ' + ', '.join(plan.FIRMWARE_RANGES))
    parser.add_argument('--prefix', help='serial prefix: ' + ', '.join(plan.VARIANTS))
    parser.add_argument('--usbnet', action='store_true', help='also install USBNetwork')
    parser.add_argument('--cache', type=Path, default=DEFAULT_CACHE, help='download cache directory')
    parser.add_argument('--log-file', type=Path, help='debug log file (default CACHE/install.log)')
    parser.add_argument('-v', '--verbose', action='store_true', help='show debug logging on the console')
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')


def _ask_valid(prompt: str, value: str | None, check: Callable[[str], str], flag: str) -> str:
    """Validate a flag value (fatal when bad) or prompt until one validates."""
    if value is not None:
        try:
            return check(value)
        except ConfigError as exc:
            raise ConfigError(f'{flag}: {exc}') from None
    while True:
        try:
            return check(input(prompt))
        except ConfigError as exc:
            print(f'  {exc}')


def _copy_with_progress(pairs: list[tuple[Path, Path]], label: str) -> None:
    """Copy (src, dst) file pairs, printing a running count so slow USB writes don't look hung."""
    every = max(1, len(pairs) // 100)

    def show(i: int, total: int) -> None:
        if i % every == 0 or i == total:
            print(f'\r  {label}: {i}/{total} files', end='', flush=True)

    device.copy_files(pairs, show)
    print()


def _update_step(mount: Path, bin_path: Path, label: str) -> None:
    device.stage_update(mount, bin_path)
    print(f'\nStaged {bin_path.name} ({label}).')
    print(DEVICE_STEPS)
    input('Press Enter once the Kindle has rebooted and remounted... ')
    while not mount.is_dir():
        log.debug('waiting for %s to come back', mount)
        input(f'Kindle not mounted at {mount} yet; reconnect it in USB drive mode and press Enter... ')
    if device.update_pending(mount, bin_path):
        log.warning('%s is still at the Kindle root; the update may not have applied.', bin_path.name)


def run(args: argparse.Namespace) -> int:
    fw = _ask_valid(f'Firmware range ({"/".join(plan.FIRMWARE_RANGES)}): ', args.fw, plan.check_firmware, '--fw')
    prefix = _ask_valid(f'Serial prefix ({"/".join(plan.VARIANTS)}): ', args.prefix, plan.check_prefix, '--prefix')
    files = plan.select_files(fw, prefix, args.usbnet)
    mount = device.require_mount(args.mount)
    steps = plan.update_steps(files)
    log.debug('plan: fw=%s prefix=%s usbnet=%s mount=%s files=%s', fw, prefix, args.usbnet, mount, files)

    if args.dry_run:
        print(f'Dry run: mount={mount} firmware={fw} prefix={prefix}')
        for key, label in steps:
            print(f'  would stage {files[key]} ({label})')
        print(f'  would copy {plan.KUAL_FILE} into documents/')
        print('  would merge koreader/, extensions/, launchpad/ into the mount root')
        return 0

    print('Getting packages (cached after the first run):')
    roots = packages.fetch_packages(plan.package_keys(files), args.cache, lambda name: print(f'  {name}', flush=True))
    bins = [(packages.member_path(roots[key], files[key]), label) for key, label in steps]
    kual = packages.member_path(roots['kual'], files['kual'])
    for bin_path, label in bins:
        _update_step(mount, bin_path, label)

    print(f'\nCopying {kual.name} to documents/')
    device.install_kual(mount, kual)

    pairs = device.koreader_pairs(roots['koreader'], mount)
    size_mb = sum(src.stat().st_size for src, _ in pairs) / 1e6
    print(
        f'Copying KOReader ({len(pairs)} files, {size_mb:.0f} MB). '
        'This takes several minutes on a K3; leave it plugged in.'
    )
    _copy_with_progress(pairs, 'KOReader')
    print('Flushing writes to the Kindle...', flush=True)
    device.flush()
    print(f'\n{DONE_MESSAGE}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='koreader-d00901', description='Install KOReader on a Kindle K3.')
    add_common_args(parser)
    parser.add_argument('--dry-run', action='store_true', help='print the plan only')
    args = parser.parse_args(argv)
    log_file = args.log_file or args.cache / 'install.log'
    setup_logging(log_file, verbose=args.verbose)
    log.debug('koreader-d00901 %s, args=%s', __version__, vars(args))
    try:
        return run(args)
    except InstallerError as exc:
        log.debug('install failed', exc_info=True)
        print(f'error: {exc}\n(details in {log_file})', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('\nInterrupted.')
        return 130
