"""Install KOReader on a Kindle Keyboard (K3) from Linux."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('koreader_D00901')
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = '0.0.0'
