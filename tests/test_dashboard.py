import io
import json
import runpy
import shutil
import subprocess
import sys
import threading
import xml.etree.ElementTree as ET

from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from koreader_d00901 import dashboard, plan
from koreader_d00901.errors import ConfigError

Image = pytest.importorskip('PIL.Image')
ROOT = Path(__file__).resolve().parent.parent
URL = 'http://192.168.10.158:8090/k3.png'
needs_sh = pytest.mark.skipif(
    sys.platform == 'win32', reason='runs the Kindle shell script with sh, which Windows lacks'
)


def _png(size=(1200, 1600), mode='RGB') -> bytes:
    image = Image.new(mode, size)
    width, height = size
    image.putdata([((x * 255) // width, (y * 255) // height, 128) for y in range(height) for x in range(width)])
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


@pytest.mark.parametrize('url', [URL, 'http://k3-dash.home.arpa/k3.png'])
def test_good_urls(url):
    assert dashboard.check_url(f'  {url} ') == url


@pytest.mark.parametrize(
    ('url', 'message'),
    [
        ('https://grafana.home.arpa/k3.png', 'must be http://'),
        ('ftp://host/k3.png', 'must be http://'),
        ('http:///k3.png', 'must be http://'),
        ('http://host/k3.png"; rm -rf /mnt/us; "', 'character'),
        ('http://host/$(reboot).png', 'character'),
    ],
)
def test_bad_urls(url, message):
    with pytest.raises(ConfigError, match=message):
        dashboard.check_url(url)


def test_interval_floor():
    assert dashboard.check_interval(60) == 60
    with pytest.raises(ConfigError, match='at least 60'):
        dashboard.check_interval(59)


def test_dashboard_step_is_opt_in():
    assert 'dashboard' not in plan.selected_steps()
    assert 'dashboard' in plan.selected_steps(dashboard=True)
    assert plan.selected_steps(['feeds'], dashboard=True) == {'feeds', 'dashboard'}
    assert plan.selected_steps(['dashboard']) == {'dashboard'}


def test_install_extension_layout_and_conf(tmp_path):
    target = dashboard.install_extension(tmp_path, URL, 300)
    assert target == tmp_path / 'extensions' / 'k3dash'
    assert sorted(p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()) == [
        'bin/k3dash.sh',
        'config.xml',
        'k3dash.conf',
        'menu.json',
    ]
    assert ET.parse(target / 'config.xml').getroot().findtext('menus/menu') == 'menu.json'
    menu = json.loads((target / 'menu.json').read_text(encoding='utf-8'))
    params = [item['params'] for item in menu['items'][0]['items']]
    assert params == [f'/mnt/us/extensions/k3dash/bin/k3dash.sh {verb}' for verb in ('start', 'once', 'stop')]
    for path in target.rglob('*'):
        if path.is_file():
            assert b'\r' not in path.read_bytes(), f'{path.name}: CRLF line endings break the Kindle shell'


@needs_sh
def test_conf_is_sourced_by_sh(tmp_path):
    target = dashboard.install_extension(tmp_path, URL, 300)
    # The conf is sourced by the Kindle's shell: it must give back exactly what was written.
    out = subprocess.run(
        ['sh', '-c', '. "$1"; printf "%s|%s" "$URL" "$INTERVAL"', 'sh', str(target / 'k3dash.conf')],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out == f'{URL}|300'


def test_bundled_extension_files_have_lf_line_endings():
    # .gitattributes keeps them LF in a Windows checkout too, so a wheel built there stays correct.
    for path in (ROOT / 'src' / 'koreader_d00901' / 'k3dash').rglob('*'):
        if path.is_file():
            assert b'\r' not in path.read_bytes(), f'{path.name}: CRLF line endings break the Kindle shell'


@needs_sh
def test_kindle_script_parses_and_uses_only_device_paths():
    script = ROOT / 'src' / 'koreader_d00901' / 'k3dash' / 'bin' / 'k3dash.sh'
    subprocess.run(['sh', '-n', str(script)], check=True)
    if busybox := shutil.which('busybox'):
        subprocess.run([busybox, 'sh', '-n', str(script)], check=True)
    text = script.read_text(encoding='utf-8')
    assert '\r' not in text, 'CRLF line endings break the Kindle shell'
    assert 'lipc-set-prop -i com.lab126.wifid enable 1' in text
    assert 'FBINK=/mnt/us/koreader/fbink' in text


@needs_sh
def test_kindle_script_once_with_fakes(tmp_path):
    """Run the real script with fake wget/fbink/lipc to check the fetch-and-draw path."""
    fakes = tmp_path / 'bin'
    fakes.mkdir()
    calls = tmp_path / 'calls'
    for name, body in {
        'wget': 'echo "wget $*" >>"$CALLS"; while [ "$1" != -O ]; do shift; done; printf png >"$2"',
        'fbink': 'echo "fbink $*" >>"$CALLS"',
        'lipc-set-prop': 'echo "lipc $*" >>"$CALLS"',
    }.items():
        (fakes / name).write_text(f'#!/bin/sh\n{body}\n')
        (fakes / name).chmod(0o755)
    script = (ROOT / 'src' / 'koreader_d00901' / 'k3dash' / 'bin' / 'k3dash.sh').read_text(encoding='utf-8')
    ext = tmp_path / 'k3dash'
    (ext / 'bin').mkdir(parents=True)
    (ext / 'k3dash.conf').write_text(dashboard.render_conf(URL, 120))
    patched = (
        script
        .replace('DIR=/mnt/us/extensions/k3dash', f'DIR={ext}')
        .replace('IMG=/tmp/k3dash.png', f'IMG={tmp_path}/k3dash.png')
        .replace('PIDFILE=/tmp/k3dash.pid', f'PIDFILE={tmp_path}/k3dash.pid')
        .replace('FBINK=/mnt/us/koreader/fbink', f'FBINK={fakes}/fbink')
    )
    (ext / 'bin' / 'k3dash.sh').write_text(patched)
    env = {'PATH': f'{fakes}:/usr/bin:/bin', 'CALLS': str(calls)}
    subprocess.run(['sh', str(ext / 'bin' / 'k3dash.sh'), 'once'], env=env, check=True)
    lines = calls.read_text(encoding='utf-8').splitlines()
    assert lines[0].startswith('wget -q -T 30 -O ')
    assert lines[0].endswith(URL)
    assert lines[1] == f'fbink -q -c -f -g file={tmp_path}/k3dash.png'
    assert (tmp_path / 'k3dash.png').read_text(encoding='utf-8') == 'png'


def test_to_k3_scales_and_quantises():
    out = Image.open(io.BytesIO(dashboard.to_k3(_png())))
    assert out.size == (600, 800)
    assert out.mode == 'L'
    levels = {value for _count, value in out.getcolors()}
    assert len(levels) <= 16
    assert all(value % 17 == 0 for value in levels)


def test_render_url():
    assert dashboard.render_url('http://localhost:3000/', 'k3-status', 'America/New_York') == (
        'http://localhost:3000/render/d/k3-status?width=1200&height=1600&kiosk=true&theme=light&tz=America%2FNew_York'
    )


class _FakeGrafana(BaseHTTPRequestHandler):
    body = b''
    kind = 'image/png'
    seen: list[tuple[str, str | None]] = []

    def do_GET(self):
        type(self).seen.append((self.path, self.headers.get('Authorization')))
        self.send_response(200)
        self.send_header('Content-Type', self.kind)
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format, *args):
        pass


@pytest.fixture
def grafana():
    _FakeGrafana.seen = []
    server = HTTPServer(('127.0.0.1', 0), _FakeGrafana)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield _FakeGrafana, f'http://127.0.0.1:{server.server_port}'
    server.shutdown()


def test_render_command_writes_a_k3_png(grafana, tmp_path):
    handler, base = grafana
    handler.body, handler.kind = _png(), 'image/png'
    token = tmp_path / 'token'
    token.write_text('glsa_secret\n')
    out = tmp_path / 'srv' / 'k3.png'
    code = dashboard.main(['render', '--grafana', base, '--token-file', str(token), '--out', str(out)])
    assert code == 0
    assert handler.seen == [('/render/d/k3-status?width=1200&height=1600&kiosk=true&theme=light', 'Bearer glsa_secret')]
    assert Image.open(out).size == (600, 800)
    assert [p.name for p in out.parent.iterdir()] == ['k3.png'], 'no temp files left behind'


def test_render_command_reports_a_login_page(grafana, tmp_path, capsys, monkeypatch):
    handler, base = grafana
    handler.body, handler.kind = b'<html>login</html>', 'text/html'
    monkeypatch.setenv('GRAFANA_TOKEN', 'x')
    out = tmp_path / 'k3.png'
    assert dashboard.main(['render', '--grafana', base, '--out', str(out)]) == 1
    assert 'not a PNG (is the image renderer set up?)' in capsys.readouterr().err
    assert not out.exists()


def test_render_command_needs_a_token(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv('GRAFANA_TOKEN', raising=False)
    assert dashboard.main(['render', '--out', str(tmp_path / 'k3.png')]) == 1
    assert 'no Grafana token' in capsys.readouterr().err


def test_grafana_dashboard_json_is_current_and_portable(capsys):
    assert dashboard.main(['grafana-json']) == 0
    model = json.loads(capsys.readouterr().out)
    generated = runpy.run_path(str(ROOT / 'scripts' / 'make_k3_dashboard.py'))['dashboard']()
    assert model == generated, 'run `make dashboard-json` after editing scripts/make_k3_dashboard.py'
    assert model['uid'] == dashboard.DEFAULT_UID
    assert [i['name'] for i in model['__inputs']] == ['DS_PROMETHEUS']
    for panel in model['panels']:
        assert panel['datasource']['uid'] == '${DS_PROMETHEUS}'
        assert all(t['datasource']['uid'] == '${DS_PROMETHEUS}' for t in panel['targets'])
        assert panel['gridPos']['x'] + panel['gridPos']['w'] <= 24
