import asyncio

import pytest

from conftest import FILES, FW, PREFIX
from textual.widgets import Button, Checkbox, Input, RichLog, SelectionList

from koreader_d00901.tui import InstallerApp


def _name(key: str) -> str:
    member = FILES[key]
    assert member is not None
    return member.split('/')[-1]


def _log_text(app: InstallerApp) -> str:
    return '\n'.join(line.text for line in app.query_one('#log', RichLog).lines)


async def _drive(
    app: InstallerApp,
    mount,
    press: str = '#install',
    limit: int = 400,
    answer: str | None = None,
    setup=None,
) -> tuple[list[list[str]], str]:
    """Press a button, then press Continue at every device step until the install settles."""
    waits: list[list[str]] = []
    text = ''
    async with app.run_test(size=(140, 50)) as pilot:
        if setup is not None:
            setup(app)
            await pilot.pause(0.05)
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
    assert (mount / 'koreader' / 'news' / 'feed_config.lua').is_file()
    assert set(app._marks.values()) == {'done'}
    assert 'Write news feed list' in dict(app._steps).values()


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


def test_tui_only_preselects_steps(kindle):
    app = _app(kindle, only=['feeds'])
    waits, log_text = asyncio.run(_drive(app, kindle.mount))
    assert app.state == 'done', log_text
    assert waits == []
    assert [key for key, _ in app._steps] == ['feeds']
    assert (kindle.mount / 'koreader' / 'news' / 'feed_config.lua').is_file()
    assert not (kindle.mount / 'koreader' / 'koreader.sh').exists()
    assert 'Done with the selected steps' in log_text


def test_tui_unticking_a_step_skips_it(kindle):
    def untick(app):
        steps = app.query_one('#steps-select', SelectionList)
        for key in ('jailbreak', 'mkk', 'keystore', 'koreader'):
            steps.deselect(key)

    app = _app(kindle)
    waits, log_text = asyncio.run(_drive(app, kindle.mount, setup=untick))
    assert app.state == 'done', log_text
    assert waits == []
    assert (kindle.mount / 'documents' / 'KUAL-KDK-1.0.azw2').is_file()
    assert not (kindle.mount / 'koreader' / 'koreader.sh').exists()


def test_tui_custom_feed_file(kindle, tmp_path):
    custom = tmp_path / 'mine.toml'
    custom.write_text('[[feed]]\nname = "Mine"\nsection = "research"\nurl = "https://example.org/a.xml"\nlimit = 1\n')
    app = _app(kindle, only=['feeds'], feeds_file=custom)
    _, log_text = asyncio.run(_drive(app, kindle.mount))
    assert app.state == 'done', log_text
    assert 'https://example.org/a.xml' in (kindle.mount / 'koreader' / 'news' / 'feed_config.lua').read_text()


def test_tui_bad_feed_file_refuses_to_start(kindle, tmp_path):
    def point_at_missing(app):
        app.query_one('#feeds', Input).value = str(tmp_path / 'missing.toml')

    app = _app(kindle)
    _, log_text = asyncio.run(_drive(app, kindle.mount, limit=5, setup=point_at_missing))
    assert app.state == 'setup'
    assert 'feed list:' in log_text


def test_tui_debug_toggle_streams_debug_log(kindle):
    def debug_on(app):
        app.query_one('#debug', Checkbox).value = True

    app = _app(kindle, only=['feeds'])
    _, log_text = asyncio.run(_drive(app, kindle.mount, setup=debug_on))
    assert app.state == 'done', log_text
    assert 'INFO koreader_d00901.feeds: wrote 20 feeds (13 enabled)' in log_text
    assert 'DEBUG koreader_d00901.device: syncing writes to disk' in log_text


def test_tui_debug_off_hides_debug_log(kindle):
    app = _app(kindle, only=['feeds'])
    _, log_text = asyncio.run(_drive(app, kindle.mount))
    assert 'DEBUG' not in log_text
    assert 'INFO koreader_d00901' not in log_text


def test_tui_dashboard_url_preselects_and_installs(kindle):
    app = _app(kindle, only=['feeds'], dashboard_url='http://10.0.0.5:8090/k3.png', dashboard_interval=120)
    _, log_text = asyncio.run(_drive(app, kindle.mount))
    assert app.state == 'done', log_text
    assert app.install is not None
    assert 'dashboard' in app.install.steps
    conf = (kindle.mount / 'extensions' / 'k3dash' / 'k3dash.conf').read_text()
    assert 'INTERVAL=120' in conf
    assert 'Installed the status display' in log_text


def test_tui_dashboard_step_needs_a_url(kindle):
    def tick_dashboard(app):
        app.query_one('#steps-select', SelectionList).select('dashboard')

    app = _app(kindle)
    _, log_text = asyncio.run(_drive(app, kindle.mount, limit=5, setup=tick_dashboard))
    assert app.state == 'setup'
    assert 'status display:' in log_text


async def _open_wipe_dialog(app: InstallerApp, size: tuple[int, int]):
    """Open the delete-books dialog at a terminal size and return the pilot-run results."""
    async with app.run_test(size=size) as pilot:
        app.query_one('#install', Button).press()
        for _ in range(250):
            await pilot.pause(0.02)
            if app.screen.query('#wipe-no'):
                break
        await pilot.pause(0.1)
        screen = app.screen
        dialog = screen.query_one('#dialog').region
        regions = {name: screen.query_one(name).region for name in ('#wipe-yes', '#wipe-no', '#wipe-help')}
        focused = app.focused.id if app.focused else None
        await pilot.press('escape')
        await pilot.pause(0.1)
        return dialog, regions, focused, app.screen is not screen, _log_text(app)


@pytest.mark.parametrize('size', [(80, 24), (60, 20), (140, 50)])
def test_tui_wipe_dialog_buttons_stay_on_screen_with_many_books(kindle, size):
    # Regression for #26: with a long list the buttons ended up below the dialog, out of sight.
    for i in range(60):
        (kindle.mount / 'documents' / f'Previous Owner Book Title {i:03d} - Some Author.azw').write_text('x')
    app = _app(kindle, wipe=True)
    dialog, regions, focused, closed, log_text = asyncio.run(_open_wipe_dialog(app, size))
    cols, rows = size
    assert dialog.right <= cols
    assert dialog.bottom <= rows
    for name in ('#wipe-yes', '#wipe-no'):
        button = regions[name]
        assert button.height == 3, name
        assert dialog.contains_region(button), f'{name} {button} is outside the dialog {dialog}'
        assert not button.overlaps(regions['#wipe-help']), name
    assert focused == 'wipe-no', 'the safe choice should have focus'
    assert closed, 'Esc should close the dialog'
    assert 'Kept your books' in log_text
    assert (kindle.mount / 'documents' / 'Previous Owner Book Title 000 - Some Author.azw').is_file()
