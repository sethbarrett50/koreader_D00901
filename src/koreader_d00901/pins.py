"""Check that every pinned package still downloads, matches its sha256, and holds the files we install.

Run by the scheduled pin-check workflow: ``python -m koreader_d00901.pins``. Exits 1 and prints
one line per problem when upstream has moved, so drift is caught before a user hits it.
"""

import argparse
import logging
import sys
import tempfile

from pathlib import Path

from koreader_d00901 import packages, plan
from koreader_d00901.errors import InstallerError
from koreader_d00901.logs import setup_logging

log = logging.getLogger(__name__)


def check_pins(cache: Path) -> list[str]:
    """Fetch and unpack every pinned package; return a list of problems (empty when all is well)."""
    problems: list[str] = []
    roots: dict[str, Path] = {}
    for key, pkg in packages.load_manifest().items():
        try:
            roots[key] = packages.extract(packages.fetch(pkg, cache), cache / key)
        except InstallerError as exc:
            log.debug('pin check failed for %s', key, exc_info=True)
            problems.append(f'{key}: {exc}')
            continue
        print(f'{key}: downloaded and verified {pkg["filename"]}', flush=True)

    for prefix in plan.VARIANTS:
        for fw in plan.FIRMWARE_RANGES:
            for key, member in plan.select_files(fw, prefix, usbnet=True).items():
                if member is None or key not in roots:
                    continue
                if not (roots[key] / member).is_file():
                    problems.append(f'{key}: {member} (prefix {prefix}, firmware {fw}) is missing from the package')

    if 'koreader' in roots:
        for tree in plan.KOREADER_TREES:
            if not (roots['koreader'] / tree).is_dir():
                problems.append(f'koreader: {tree}/ is missing from the package')
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m koreader_d00901.pins', description=__doc__)
    parser.add_argument('--cache', type=Path, help='download directory (default: a temporary directory)')
    parser.add_argument('-v', '--verbose', action='store_true', help='show debug logging')
    args = parser.parse_args(argv)
    setup_logging(None, verbose=args.verbose)

    with tempfile.TemporaryDirectory(prefix='k3-pins-') as tmp:
        problems = check_pins(args.cache or Path(tmp))
    if problems:
        print(f'{len(problems)} pin problem(s):', file=sys.stderr)
        for problem in problems:
            print(f'- {problem}', file=sys.stderr)
        return 1
    print('All pinned packages download, match their sha256, and contain every installed file.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
