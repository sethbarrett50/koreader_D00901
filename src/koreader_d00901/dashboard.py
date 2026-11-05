"""Grafana status display for the K3 (#4).

Server side, `koreader-d00901-dashboard render` asks Grafana's image renderer for one dashboard
at 1200x1600 (Grafana switches to its one-column mobile layout below about 770px, so the K3's own
600px width cannot be requested directly), halves it to 600x800, and quantises it to the 16 grey
levels of the K3 panel. Run it from a timer and serve the output directory over plain HTTP.

Kindle side, the installer copies a small KUAL extension (k3dash/) that fetches that PNG every few
minutes and draws it with KOReader's fbink. The K3 cannot verify a modern TLS certificate, so the
image URL is plain http:// on the local network.
"""

import argparse
import io
import logging
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from importlib.resources import files
from pathlib import Path

from koreader_d00901 import __version__
from koreader_d00901.errors import ConfigError, InstallerError

log = logging.getLogger(__name__)

EXTENSION = ('extensions', 'k3dash')
CONF_NAME = 'k3dash.conf'
RENDER_SIZE = (1200, 1600)
K3_SIZE = (600, 800)
GREY_LEVELS = 16
DEFAULT_UID = 'k3-status'
DEFAULT_INTERVAL = 300
MIN_INTERVAL = 60
USER_AGENT = f'koreader-d00901/{__version__} dashboard'


class RenderError(InstallerError):
    """Grafana did not return a dashboard image."""


def check_url(url: str) -> str:
    """The image URL the Kindle fetches: plain http with a host, no shell-special characters."""
    url = url.strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != 'http' or not parts.hostname:
        raise ConfigError(f'dashboard URL must be http://host[:port]/path (the K3 cannot do modern TLS): {url!r}')
    if any(ch in url for ch in '"\'`$\\ \n'):
        raise ConfigError(f'dashboard URL contains a character the Kindle script cannot take: {url!r}')
    return url


def check_interval(seconds: int) -> int:
    if seconds < MIN_INTERVAL:
        raise ConfigError(f'dashboard interval must be at least {MIN_INTERVAL} seconds, not {seconds}')
    return seconds


def render_conf(url: str, interval: int) -> str:
    return (
        '# Written by koreader-d00901; rerun `koreader-d00901 --only dashboard --dashboard-url URL` to change.\n'
        f'URL="{check_url(url)}"\n'
        f'INTERVAL={check_interval(interval)}\n'
    )


def _extension_files() -> list[tuple[str, bytes]]:
    root = files('koreader_d00901').joinpath('k3dash')
    return [(name, root.joinpath(name).read_bytes()) for name in ('config.xml', 'menu.json', 'bin/k3dash.sh')]


def install_extension(mount: Path, url: str, interval: int = DEFAULT_INTERVAL) -> Path:
    """Copy the KUAL extension onto the Kindle and write its settings. Returns the extension folder."""
    conf = render_conf(url, interval)
    target = mount.joinpath(*EXTENSION)
    for name, data in _extension_files():
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    # Sourced by the Kindle's shell, so LF only: a CRLF would leave INTERVAL=300\r.
    (target / CONF_NAME).write_bytes(conf.encode())
    log.info('installed the dashboard extension at %s (%s every %ss)', target, url, interval)
    return target


def render_url(grafana: str, uid: str, tz: str | None = None) -> str:
    width, height = RENDER_SIZE
    params = {'width': width, 'height': height, 'kiosk': 'true', 'theme': 'light'}
    if tz:
        params['tz'] = tz
    return f'{grafana.rstrip("/")}/render/d/{urllib.parse.quote(uid)}?{urllib.parse.urlencode(params)}'


def fetch_render(url: str, token: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}', 'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            kind = response.headers.get_content_type()
            body = response.read()
    except urllib.error.HTTPError as exc:
        raise RenderError(f'Grafana answered {exc.code} {exc.reason} for {url}') from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RenderError(f'could not reach Grafana at {url}: {exc}') from exc
    if kind != 'image/png':
        snippet = body[:200].decode('utf-8', 'replace').strip()
        raise RenderError(f'Grafana sent {kind}, not a PNG (is the image renderer set up?): {snippet!r}')
    return body


def to_k3(png: bytes) -> bytes:
    """Scale a render to 600x800 and quantise it to the K3's 16 grey levels."""
    try:
        from PIL import Image
    except ImportError:
        raise InstallerError(
            'rendering needs Pillow: install koreader_D00901[dashboard] (for example `uv tool install '
            "'koreader_D00901[dashboard]'`)"
        ) from None
    image = Image.open(io.BytesIO(png)).convert('L')
    image = image.resize(K3_SIZE, Image.Resampling.LANCZOS)
    step = 255 / (GREY_LEVELS - 1)
    image = image.point([round(round(v / step) * step) for v in range(256)])
    out = io.BytesIO()
    image.save(out, format='PNG', optimize=True)
    return out.getvalue()


def write_atomic(path: Path, data: bytes) -> None:
    """Replace path in one step so the Kindle never fetches a half-written image."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f'.{path.name}.')
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def dashboard_json() -> str:
    return files('koreader_d00901').joinpath('k3-status.json').read_text(encoding='utf-8')


def _render(args: argparse.Namespace) -> int:
    token = (
        args.token_file.read_text(encoding='utf-8').strip() if args.token_file else os.environ.get('GRAFANA_TOKEN', '')
    )
    if not token:
        raise ConfigError('no Grafana token: pass --token-file or set GRAFANA_TOKEN')
    url = render_url(args.grafana, args.uid, args.tz)
    log.debug('rendering %s', url)
    image = to_k3(fetch_render(url, token, args.timeout))
    write_atomic(args.out, image)
    log.info('wrote %s (%d bytes)', args.out, len(image))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='koreader-d00901-dashboard', description=__doc__.split('\n\n')[0])
    parser.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('-v', '--verbose', action='store_true', help='debug logging')
    sub = parser.add_subparsers(dest='command', required=True)
    render = sub.add_parser('render', help='render the dashboard to a K3-ready PNG')
    render.add_argument('--grafana', default='http://localhost:3000', help='Grafana base URL (default %(default)s)')
    render.add_argument('--uid', default=DEFAULT_UID, help='dashboard UID (default %(default)s)')
    render.add_argument('--token-file', type=Path, help='file holding a Grafana service account token (Viewer)')
    render.add_argument('--out', type=Path, required=True, help='PNG to write, for example /srv/k3/k3.png')
    render.add_argument('--tz', help='time zone for the render, for example America/New_York')
    render.add_argument('--timeout', type=int, default=120, help='seconds to wait for Grafana (default %(default)s)')
    sub.add_parser('grafana-json', help='print the K3 status dashboard JSON to import into Grafana')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(levelname)s %(message)s')
    if args.command == 'grafana-json':
        sys.stdout.write(dashboard_json())
        return 0
    try:
        return _render(args)
    except (InstallerError, OSError) as exc:
        log.debug('render failed', exc_info=True)
        print(f'error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
