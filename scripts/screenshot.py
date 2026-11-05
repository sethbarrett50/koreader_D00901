"""Regenerate docs/tui.svg: the TUI after a dry run against a temporary fake Kindle mount."""

import asyncio
import sys
import tempfile

from pathlib import Path

from textual.widgets import Button

from koreader_d00901.tui import InstallerApp

OUT = Path(__file__).resolve().parent.parent / 'docs' / 'tui.svg'


async def shoot(mount: Path, cache: Path) -> None:
    app = InstallerApp(cache, mount=mount, fw='3.3-3.4', prefix='B006', usbnet=True)
    async with app.run_test(size=(120, 36)) as pilot:
        app.query_one('#dry-run', Button).press()
        await pilot.pause(0.3)
        app.save_screenshot(filename=OUT.name, path=str(OUT.parent))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        mount = Path(tmp) / 'Kindle'
        (mount / 'documents').mkdir(parents=True)
        asyncio.run(shoot(mount, Path(tmp) / 'cache'))
        # Show a stable, readable path instead of the temporary directory.
        OUT.write_text(OUT.read_text().replace(str(mount), '/media/you/Kindle'))
    print(f'wrote {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
