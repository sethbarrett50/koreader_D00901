"""Logging setup shared by the CLI and the TUI.

Every run writes a DEBUG-level log file (default ~/.cache/k3-koreader/install.log), so a failed
install can be diagnosed afterwards. The console shows warnings, or everything with --verbose.
"""

import logging

from pathlib import Path

DEFAULT_CACHE = Path('~/.cache/k3-koreader').expanduser()
FORMAT = '%(asctime)s %(levelname)-7s %(name)s: %(message)s'


def setup_logging(log_file: Path | None, verbose: bool = False, console: bool = True) -> None:
    root = logging.getLogger('koreader_d00901')
    root.setLevel(logging.DEBUG)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    if console:
        stream = logging.StreamHandler()
        stream.setLevel(logging.DEBUG if verbose else logging.WARNING)
        stream.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
        root.addHandler(stream)
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(FORMAT))
        root.addHandler(file_handler)
