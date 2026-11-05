import pytest

from koreader_d00901 import feeds
from koreader_d00901.errors import ConfigError

ATOM = b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>a</title></entry></feed>'
RSS = b'<?xml version="1.0"?><rss><channel><item><title>a</title></item></channel></rss>'


def _toml(tmp_path, body: str):
    path = tmp_path / 'feeds.toml'
    path.write_text(body)
    return path


def test_bundled_list_loads_and_matches_the_curated_set():
    feed_list = feeds.load_feeds()
    enabled = [f for f in feed_list if f.enabled]
    assert len(enabled) == 13
    assert {f.section for f in enabled} == set(feeds.SECTIONS)
    assert all(f.max_age for f in enabled), 'every enabled feed should have a max_age to avoid backlog floods'
    assert all(f.limit <= 10 for f in enabled)
    names = {f.name for f in enabled}
    assert {'FastAPI releases', 'PostgreSQL news', 'Debian security advisories (full text)'} <= names
    assert not any(f.url == 'https://rss.arxiv.org/rss/cs.LG' and f.enabled for f in feed_list)


@pytest.mark.parametrize(
    ('entry', 'message'),
    [
        ('section = "news"', 'section must be one of'),
        ('limit = -1', 'limit must be'),
        ('max_age = "7 days"', 'max_age must look like'),
        ('colour = "red"', 'unknown field'),
    ],
)
def test_invalid_entries_are_rejected(tmp_path, entry, message):
    base = {'name': '"x"', 'section': '"research"', 'url': '"https://example.org/f.xml"', 'limit': '1'}
    key = entry.split(' = ')[0]
    base[key] = entry.split(' = ', 1)[1]
    body = '[[feed]]\n' + '\n'.join(f'{k} = {v}' for k, v in base.items()) + '\n'
    with pytest.raises(ConfigError, match=message):
        feeds.load_feeds(_toml(tmp_path, body))


def test_non_http_url_and_empty_list_are_rejected(tmp_path):
    with pytest.raises(ConfigError, match='url must be http'):
        feeds.load_feeds(_toml(tmp_path, '[[feed]]\nname="x"\nsection="research"\nurl="file:///etc/passwd"\nlimit=1\n'))
    with pytest.raises(ConfigError, match='no enabled feeds'):
        feeds.load_feeds(
            _toml(tmp_path, '[[feed]]\nname="x"\nsection="research"\nurl="https://e.org"\nlimit=1\nenabled=false\n')
        )


def test_rendered_lua_is_valid_and_matches_the_plugin_format():
    lupa = pytest.importorskip('lupa')
    text = feeds.render_lua(feeds.load_feeds())
    assert text.startswith('return {--do NOT change this line')
    assert text.rstrip().endswith('}--do NOT change this line')
    config = lupa.LuaRuntime().execute(text)
    entries = list(config.values())
    assert len(entries) == 13
    first = entries[0]
    assert first[1].startswith('https://')
    assert first['limit'] == 5
    assert first['max_age'] == '7d'
    assert first['download_full_article'] is False


def test_lua_strings_are_escaped():
    feed = feeds.Feed(name='q', section='research', url='https://e.org/?q="a"\\b', limit=1)
    assert '"https://e.org/?q=\\"a\\"\\\\b"' in feeds.render_lua([feed])


def test_install_writes_config_and_backs_up_a_different_one(tmp_path):
    feed_list = feeds.load_feeds()
    target = feeds.install_feeds(tmp_path, feed_list)
    assert target == tmp_path / 'koreader' / 'news' / 'feed_config.lua'
    assert not target.with_name('feed_config.lua.bak').exists()
    feeds.install_feeds(tmp_path, feed_list)  # same content: no backup
    assert not target.with_name('feed_config.lua.bak').exists()
    target.write_text('return { { "https://hand-edited.example", limit = 1 } }')
    feeds.install_feeds(tmp_path, feed_list)
    assert 'hand-edited' in target.with_name('feed_config.lua.bak').read_text()
    assert 'hand-edited' not in target.read_text()


@pytest.mark.parametrize('body', [ATOM, RSS])
def test_check_feed_ok(tmp_path, body):
    path = tmp_path / 'f.xml'
    path.write_bytes(body)
    assert feeds.check_feed(feeds.Feed(name='f', section='research', url=path.as_uri(), limit=1)) is None


@pytest.mark.parametrize(
    ('body', 'message'), [(b'<html><body>nope</body></html>', 'no items'), (b'not xml at all', 'syntax error')]
)
def test_check_feed_problems(tmp_path, body, message):
    path = tmp_path / 'f.xml'
    path.write_bytes(body)
    problem = feeds.check_feed(feeds.Feed(name='f', section='research', url=path.as_uri(), limit=1))
    assert problem is not None
    assert message in problem


def test_main_check_skips_feeds_marked_check_false(tmp_path, monkeypatch, capsys):
    checked = []
    monkeypatch.setattr(feeds, 'check_feed', lambda feed: checked.append(feed.name))
    body = (
        '[[feed]]\nname="good"\nsection="research"\nurl="https://example.org/a.xml"\nlimit=1\n'
        '[[feed]]\nname="blocked"\nsection="security"\nurl="https://blocked.invalid/x"\nlimit=1\ncheck=false\n'
    )
    assert feeds.main(['--feeds', str(_toml(tmp_path, body)), '--check']) == 0
    out = capsys.readouterr().out
    assert checked == ['good']
    assert 'ok   good' in out
    assert 'skip blocked' in out


def test_main_check_fails_on_a_broken_feed(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(feeds, 'check_feed', lambda feed: f'{feed.name}: HTTP Error 404')
    body = '[[feed]]\nname="gone"\nsection="research"\nurl="https://example.org/gone.xml"\nlimit=1\n'
    assert feeds.main(['--feeds', str(_toml(tmp_path, body)), '--check']) == 1
    assert 'gone: HTTP Error 404' in capsys.readouterr().err
