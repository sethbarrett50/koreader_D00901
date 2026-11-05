"""Full-screen installer for KOReader on a Kindle Keyboard (K3), built with Textual."""

import argparse
import logging
import threading

from dataclasses import dataclass
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, ProgressBar, RichLog, Select, Static
from textual.worker import get_current_worker

from koreader_d00901 import __version__, device, packages, plan
from koreader_d00901.cli import DONE_MESSAGE, add_common_args, describe
from koreader_d00901.errors import InstallerError
from koreader_d00901.logs import setup_logging

log = logging.getLogger(__name__)

MODELS = {
    'B006': 'B006 - Kindle Keyboard 3G (US)',
    'B008': 'B008 - Kindle Keyboard Wi-Fi',
    'B00A': 'B00A - Kindle Keyboard 3G (UK/Europe)',
}
FIRMWARE = {
    '3.3-3.4': '3.3 to 3.4.x (for example 3.4.2)',
    '3.0-3.2': '3.0 to 3.2.x',
}
MARKS = {'pending': '[dim]·[/]', 'current': '[bold yellow]▶[/]', 'done': '[green]✓[/]', 'failed': '[red]✗[/]'}


class Cancelled(Exception):
    """The app is closing; stop the install worker."""


@dataclass(frozen=True)
class Plan:
    fw: str
    prefix: str
    usbnet: bool
    mount: Path
    wipe: tuple[Path, ...] = ()


class ConfirmWipe(ModalScreen[bool]):
    """Show exactly what --wipe-books would delete and ask before anything is removed."""

    CSS = """
    ConfirmWipe { align: center middle; }
    #dialog { width: 70; height: auto; max-height: 80%; border: thick $error; padding: 1 2; background: $surface; }
    #entries { height: auto; max-height: 20; }
    #choices { height: auto; margin-top: 1; }
    #choices Button { margin-right: 2; }
    """

    def __init__(self, entries: list[Path]) -> None:
        super().__init__()
        self.entries = entries

    def compose(self) -> ComposeResult:
        with Vertical(id='dialog'):
            yield Label(f'[b]Delete {len(self.entries)} entries from documents/?[/] KUAL and dictionaries are kept.')
            with VerticalScroll(id='entries'):
                yield Static('\n'.join(describe(self.entries, limit=200)))
            with Horizontal(id='choices'):
                yield Button('Delete them', variant='error', id='wipe-yes')
                yield Button('Keep my books', variant='primary', id='wipe-no')

    @on(Button.Pressed, '#wipe-yes')
    def yes(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, '#wipe-no')
    def no(self) -> None:
        self.dismiss(False)


class InstallerApp(App[None]):
    TITLE = 'K3 KOReader installer'
    CSS = """
    #setup { width: 44; padding: 0 1; border: round $primary; }
    #setup Label { margin-top: 1; }
    #setup Button { width: 100%; margin-top: 1; }
    #run { padding: 0 1; }
    #steps { height: auto; border: round $secondary; padding: 0 1; }
    #kindle { margin: 1 0 0 0; }
    #instructions { height: auto; border: round $warning; padding: 0 1; display: none; }
    #instructions.show { display: block; }
    #progress { margin: 1 0; }
    #actions { height: auto; }
    #actions Button { margin-right: 2; }
    #log { border: round $panel; }
    """
    BINDINGS = [('q', 'quit', 'Quit')]

    def __init__(
        self,
        cache: Path,
        mount: Path | None = None,
        fw: str | None = None,
        prefix: str | None = None,
        usbnet: bool = False,
        log_file: Path | None = None,
        wipe: bool = False,
    ) -> None:
        super().__init__()
        self.cache = cache
        self.log_file = log_file or cache / 'install.log'
        self.initial = (mount, fw, prefix.upper() if prefix else None, usbnet, wipe)
        self.install: Plan | None = None
        self.state = 'setup'  # setup -> running -> waiting -> running ... -> done | failed
        self._continue = threading.Event()

    # Layout

    def compose(self) -> ComposeResult:
        mount, fw, prefix, usbnet, wipe = self.initial
        yield Header()
        with Horizontal():
            with Vertical(id='setup'):
                yield Label('Firmware (bottom of the Settings page)')
                yield Select(
                    [(label, key) for key, label in FIRMWARE.items()],
                    id='fw',
                    prompt='Choose firmware',
                    value=fw if fw in FIRMWARE else Select.NULL,
                )
                yield Label('Serial prefix (first 4 characters)')
                yield Select(
                    [(label, key) for key, label in MODELS.items()],
                    id='prefix',
                    prompt='Choose model',
                    value=prefix if prefix in MODELS else Select.NULL,
                )
                yield Checkbox('Also install USBNetwork (ssh over USB)', usbnet, id='usbnet')
                yield Checkbox('Delete existing books first (asks)', wipe, id='wipe')
                yield Label('Kindle mount point')
                yield Input(str(mount) if mount else '', placeholder='auto-detected when plugged in', id='mount')
                yield Button('Install', variant='primary', id='install')
                yield Button('Dry run (show plan)', id='dry-run')
            with Vertical(id='run'):
                yield Static('Choose your Kindle on the left, then press Install.', id='steps')
                yield Static('', id='kindle')
                yield Static('', id='instructions')
                yield ProgressBar(id='progress', show_eta=False)
                with Horizontal(id='actions'):
                    yield Button('Continue', variant='success', id='continue', disabled=True)
                    yield Button('Eject Kindle', id='eject')
                yield RichLog(id='log', markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._steps: list[tuple[str, str]] = []
        self._marks: dict[str, str] = {}
        self.refresh_kindle()
        self.set_interval(1.0, self.refresh_kindle)

    # Small UI helpers (main thread only)

    def log_line(self, text: str) -> None:
        self.query_one('#log', RichLog).write(text)

    def mount_path(self) -> Path | None:
        if self.install is not None:
            return self.install.mount
        value = self.query_one('#mount', Input).value.strip()
        return Path(value).expanduser() if value else None

    def refresh_kindle(self) -> None:
        mount_input = self.query_one('#mount', Input)
        if self.install is None and not mount_input.value.strip():
            found = device.find_mount()
            if found is not None:
                mount_input.value = str(found)
        mount = self.mount_path()
        if mount is not None and mount.is_dir():
            text = f'Kindle: [green]connected[/] at {mount}'
        elif mount is not None:
            text = f'Kindle: [red]not mounted[/] at {mount}'
        else:
            text = 'Kindle: [red]not detected[/]; connect it in USB drive mode'
        self.query_one('#kindle', Static).update(text)
        self.query_one('#eject', Button).disabled = mount is None or not mount.is_dir()

    def render_steps(self) -> None:
        lines = [f'{MARKS[self._marks[key]]} {label}' for key, label in self._steps]
        self.query_one('#steps', Static).update('\n'.join(lines))

    def mark(self, key: str, status: str) -> None:
        self._marks[key] = status
        self.render_steps()

    def read_plan(self) -> Plan | None:
        fw = self.query_one('#fw', Select).value
        prefix = self.query_one('#prefix', Select).value
        mount = self.mount_path()
        problems = []
        if not isinstance(fw, str):
            problems.append('choose a firmware range')
        if not isinstance(prefix, str):
            problems.append('choose a serial prefix')
        if mount is None or not mount.is_dir():
            problems.append('connect the Kindle in USB drive mode (or type its mount point)')
        if problems or not isinstance(fw, str) or not isinstance(prefix, str) or mount is None:
            self.log_line('[red]Cannot start:[/] ' + '; '.join(problems) + '.')
            return None
        return Plan(fw, prefix, self.query_one('#usbnet', Checkbox).value, mount)

    def plan_steps(self, install: Plan) -> tuple[dict[str, str | None], list[tuple[str, str]]]:
        files = plan.select_files(install.fw, install.prefix, install.usbnet)
        steps = plan.update_steps(files)
        return files, steps

    # Buttons

    @on(Button.Pressed, '#dry-run')
    def dry_run(self) -> None:
        install = self.read_plan()
        if install is None:
            return
        files, steps = self.plan_steps(install)
        self.log_line(f'[b]Plan[/] for {MODELS[install.prefix]}, firmware {install.fw}, at {install.mount}:')
        if self.query_one('#wipe', Checkbox).value:
            entries = device.list_books(install.mount)
            self.log_line(f'  ask, then delete {len(entries)} entries in documents/ (KUAL and dictionaries kept)')
            for line in describe(entries):
                self.log_line(f'  {line}')
        for key, label in steps:
            self.log_line(f'  stage {files[key]} ({label}), then Update Your Kindle')
        self.log_line('  copy KUAL-KDK-1.0.azw2 into documents/')
        self.log_line('  merge koreader/, extensions/, launchpad/ into the Kindle root')
        self.log_line('Nothing was changed.')

    @on(Button.Pressed, '#install')
    def start_install(self) -> None:
        install = self.read_plan()
        if install is None:
            return
        entries = device.list_books(install.mount) if self.query_one('#wipe', Checkbox).value else []
        if not entries:
            if self.query_one('#wipe', Checkbox).value:
                self.log_line('No books to delete in documents/.')
            self.begin(install)
            return

        def answered(confirmed: bool | None) -> None:
            if confirmed:
                self.begin(Plan(install.fw, install.prefix, install.usbnet, install.mount, tuple(entries)))
            else:
                self.log_line('Kept your books; press Install again, or untick the delete option.')

        self.push_screen(ConfirmWipe(entries), answered)

    def begin(self, install: Plan) -> None:
        self.install = install
        _files, steps = self.plan_steps(install)
        self._steps = [('wipe', f'Delete {len(install.wipe)} old entries')] if install.wipe else []
        self._steps += [('packages', 'Download and verify packages'), *steps]
        self._steps += [('kual', 'Copy KUAL to documents/'), ('koreader', 'Copy KOReader')]
        self._marks = {key: 'pending' for key, _ in self._steps}
        self.render_steps()
        for widget in self.query('#setup Select, #setup Checkbox, #setup Input, #setup Button'):
            widget.disabled = True
        self.state = 'running'
        self.run_install(install)

    @on(Button.Pressed, '#continue')
    def continue_pressed(self) -> None:
        mount = self.mount_path()
        if mount is None or not mount.is_dir():
            self.log_line(f'Kindle is not mounted at {mount} yet. Reconnect it in USB drive mode, then press Continue.')
            return
        self.query_one('#continue', Button).disabled = True
        self.query_one('#instructions', Static).remove_class('show')
        self.state = 'running'
        self._continue.set()

    @on(Button.Pressed, '#eject')
    def eject_pressed(self) -> None:
        mount = self.mount_path()
        if mount is not None:
            self.do_eject(mount)

    @work(thread=True, group='eject')
    def do_eject(self, mount: Path) -> None:
        try:
            out = device.eject(mount)
        except InstallerError as exc:
            self.call_from_thread(self.log_line, f'[red]Eject failed:[/] {exc}')
            return
        self.call_from_thread(self.log_line, f'Ejected. {out} You can unplug the Kindle now.')
        self.call_from_thread(self.refresh_kindle)

    # Install worker (runs in a thread; touches the UI only through call_from_thread)

    def _ui(self, fn, *args) -> None:
        if get_current_worker().is_cancelled:
            raise Cancelled
        self.call_from_thread(fn, *args)

    def _wait_for_continue(self) -> None:
        worker = get_current_worker()
        while not self._continue.wait(0.2):
            if worker.is_cancelled:
                raise Cancelled
        self._continue.clear()

    def _await_device(self, label: str) -> None:
        self.state = 'waiting'
        box = self.query_one('#instructions', Static)
        box.update(
            f'[b]Now apply the {label} update on the Kindle:[/]\n'
            '1. Press [b]Eject Kindle[/] below, then unplug the USB cable.\n'
            '2. On the Kindle: HOME > MENU > Settings > MENU > Update Your Kindle.\n'
            '3. Wait for it to reboot, plug it back in, then press [b]Continue[/].\n'
            'Never reboot by hand to force it. Greyed out means the wrong file was staged.'
        )
        box.add_class('show')
        self.query_one('#continue', Button).disabled = False

    def _progress(self, done: int, total: int) -> None:
        self.query_one('#progress', ProgressBar).update(total=total, progress=done)

    def _finish(self, ok: bool, message: str) -> None:
        self.state = 'done' if ok else 'failed'
        self.log_line(message)
        if ok:
            self.notify('KOReader installed')

    @work(thread=True, exclusive=True, group='install')
    def run_install(self, install: Plan) -> None:
        current = 'packages'
        try:
            files, steps = self.plan_steps(install)
            if install.wipe:
                current = 'wipe'
                self._ui(self.mark, current, 'current')
                removed = device.wipe_books(install.mount, list(install.wipe))
                self._ui(self.log_line, f'Deleted {removed} entries from documents/.')
                self._ui(self.mark, current, 'done')
                current = 'packages'
            self._ui(self.mark, current, 'current')
            log.debug('plan: %s files=%s', install, files)
            roots = packages.fetch_packages(
                plan.package_keys(files), self.cache, lambda name: self._ui(self.log_line, f'Getting {name}')
            )
            self._ui(self.mark, current, 'done')

            for key, label in steps:
                current = key
                bin_path = packages.member_path(roots[key], files[key])
                self._ui(self.mark, key, 'current')
                device.stage_update(install.mount, bin_path)
                self._ui(self.log_line, f'Staged {bin_path.name}.')
                self._ui(self._await_device, label)
                self._wait_for_continue()
                if device.update_pending(install.mount, bin_path):
                    self._ui(
                        self.log_line,
                        f'[yellow]Warning:[/] {bin_path.name} is still on the Kindle; the update may not have applied.',
                    )
                self._ui(self.mark, key, 'done')

            current = 'kual'
            self._ui(self.mark, current, 'current')
            device.install_kual(install.mount, packages.member_path(roots['kual'], files['kual']))
            self._ui(self.mark, current, 'done')

            current = 'koreader'
            self._ui(self.mark, current, 'current')
            pairs = device.koreader_pairs(roots['koreader'], install.mount)
            size_mb = sum(src.stat().st_size for src, _ in pairs) / 1e6
            self._ui(
                self.log_line,
                f'Copying KOReader ({len(pairs)} files, {size_mb:.0f} MB). '
                'This takes several minutes; leave it plugged in.',
            )
            every = max(1, len(pairs) // 200)
            device.copy_files(pairs, lambda i, n: self._ui(self._progress, i, n) if i % every == 0 or i == n else None)
            self._ui(self.log_line, 'Flushing writes to the Kindle...')
            device.flush()
            self._ui(self.mark, current, 'done')
            self._ui(self._finish, True, f'[green]{DONE_MESSAGE}[/]')
        except Cancelled:
            return
        except InstallerError as exc:
            log.debug('install failed', exc_info=True)
            self.call_from_thread(self.mark, current, 'failed')
            self.call_from_thread(self._finish, False, f'[red]Install failed:[/] {exc} (details in {self.log_file})')
        except Exception as exc:
            log.exception('unexpected error during %s', current)
            self.call_from_thread(self.mark, current, 'failed')
            self.call_from_thread(
                self._finish, False, f'[red]Unexpected error:[/] {exc!r}; the traceback is in {self.log_file}'
            )

    def on_unmount(self) -> None:
        self.workers.cancel_all()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='koreader-d00901-tui', description='Full-screen KOReader installer for the Kindle K3.'
    )
    add_common_args(parser)
    args = parser.parse_args(argv)
    log_file = args.log_file or args.cache / 'install.log'
    # Console logging would draw over the TUI, so the TUI logs to the file only.
    setup_logging(log_file, verbose=args.verbose, console=False)
    log.debug('koreader-d00901-tui %s, args=%s', __version__, vars(args))
    InstallerApp(args.cache, args.mount, args.fw, args.prefix, args.usbnet, log_file, args.wipe_books).run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
