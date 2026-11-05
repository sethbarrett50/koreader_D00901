import asyncio

from conftest import FILES, FW, PREFIX
from textual.widgets import Button, RichLog

from koreader_d00901.tui import InstallerApp


def _name(key: str) -> str:
    member = FILES[key]
    assert member is not None
    return member.split('/')[-1]


def _log_text(app: InstallerApp) -> str:
    return '\n'.join(line.text for line in app.query_one('#log', RichLog).lines)


async def _drive(
    app: InstallerApp, mount, press: str = '#install', limit: int = 400, answer: str | None = None
) -> tuple[list[list[str]], str]:
    """Press a button, then press Continue at every device step until the install settles."""
    waits: list[list[str]] = []
    text = ''
    async with app.run_test(size=(140, 50)) as pilot:
        app.query_one(press, Button).press()
        if answer is not None:
            # Wait for the dialog to be composed instead of sleeping a fixed time (slow CI runners).
            for _ in range(250):
                await pilot.pause(0.02)
                if app.screen.query(answer):
                    break
            app.screen.query_one(answer, Button).press()
        for _ in range(limit):
            await pilot.pause(0.02)
            if app.state == 'waiting' and not app.query_one('#continue', Button).disabled:
                waits.append(sorted(p.name for p in mount.glob('Update[-_]*.bin')))
                app.query_one('#continue', Button).press()
            if app.state in ('done', 'failed') or (press != '#install' and app.state == 'setup'):
                await pilot.pause(0.05)
                break
        text = _log_text(app)
    return waits, text


def _app(kindle, **kw) -> InstallerApp:
    kw.setdefault('fw', FW)
    kw.setdefault('prefix', PREFIX)
    return InstallerApp(kindle.cache, mount=kindle.mount, **kw)


def test_tui_full_install(kindle):
    app = _app(kindle)
    waits, log_text = asyncio.run(_drive(app, kindle.mount))
    assert app.state == 'done', log_text
    names = [_name(k) for k in ('jailbreak', 'mkk', 'keystore')]
    assert waits == [[n] for n in names]
    mount = kindle.mount
    assert (mount / 'documents' / 'KUAL-KDK-1.0.azw2').read_bytes() == b'kual'
    assert (mount / 'documents' / 'keep.txt').read_text() == 'mine'
    assert (mount / 'koreader' / 'koreader.sh').is_file()
    assert (mount / 'launchpad' / 'boot.sh').is_file()
    assert set(app._marks.values()) == {'done'}


def test_tui_usbnet_adds_a_step(kindle):
    app = _app(kindle, usbnet=True)
    waits, log_text = asyncio.run(_drive(app, kindle.mount))
    assert app.state == 'done', log_text
    assert len(waits) == 4
    assert waits[-1] == [_name('usbnet')]


def test_tui_refuses_to_start_without_choices(kindle):
    app = InstallerApp(kindle.cache, mount=kindle.mount)
    _, log_text = asyncio.run(_drive(app, kindle.mount, limit=5))
    assert app.state == 'setup'
    assert 'choose a firmware range' in log_text
    assert 'choose a serial prefix' in log_text
    assert not (kindle.mount / 'koreader').exists()


def test_tui_dry_run_changes_nothing(kindle):
    before = sorted(p.name for p in kindle.mount.rglob('*'))
    app = _app(kindle)
    _, log_text = asyncio.run(_drive(app, kindle.mount, press='#dry-run', limit=5))
    assert 'Nothing was changed.' in log_text
    assert _name('keystore') in log_text
    assert sorted(p.name for p in kindle.mount.rglob('*')) == before


def test_tui_download_failure_is_reported(kindle):
    kindle.manifest['jailbreak']['url'] = (kindle.cache.parent / 'gone.tar.xz').as_uri()
    app = _app(kindle)
    _, log_text = asyncio.run(_drive(app, kindle.mount))
    assert app.state == 'failed'
    assert 'Install failed' in log_text
    assert 'could not download' in log_text
    assert app._marks['packages'] == 'failed'


def _add_book(kindle):
    (kindle.mount / 'documents' / 'novel.mobi').write_bytes(b'book')


def test_tui_wipe_confirmed(kindle):
    _add_book(kindle)
    app = _app(kindle, wipe=True)
    _, log_text = asyncio.run(_drive(app, kindle.mount, answer='#wipe-yes'))
    assert app.state == 'done', log_text
    assert 'Deleted 2 entries' in log_text
    assert sorted(p.name for p in (kindle.mount / 'documents').iterdir()) == ['KUAL-KDK-1.0.azw2']


def test_tui_wipe_declined_does_not_start(kindle):
    _add_book(kindle)
    app = _app(kindle, wipe=True)
    _, log_text = asyncio.run(_drive(app, kindle.mount, limit=5, answer='#wipe-no'))
    assert app.state == 'setup'
    assert 'Kept your books' in log_text
    assert (kindle.mount / 'documents' / 'novel.mobi').is_file()
    assert not (kindle.mount / 'koreader').exists()
