# Development

Python 3.14 only, managed with [uv](https://docs.astral.sh/uv/).

```
make sync           # uv sync --dev (ruff, ty, pytest)
make lint           # ruff format + ruff check --fix
make typecheck      # ty check
make test           # pytest
make ci             # everything CI runs, without fixes
make build          # sdist + wheel into dist/
make smoke          # install the wheel in a clean env and run every command
make version-check  # package changed since the last tag? then the version must be bumped
make screenshot     # regenerate docs/tui.svg
make dashboard-json # regenerate the K3 Grafana dashboard from scripts/make_k3_dashboard.py
uv run python -m koreader_d00901.pins   # re-download every pin and check it (about 100 MB)
uv run python -m koreader_d00901.feeds --check   # fetch and parse every news feed
```

## Code layout

The code lives in `src/koreader_d00901/`:

- `plan.py`: which files a given serial prefix and firmware range need.
- `packages.py`: downloading, verifying and unpacking the packages pinned in `packages.json`.
  Nothing downloaded is ever executed on the host.
- `device.py`: everything that touches the Kindle's USB volume (staging, copying, wiping, eject).
- `cli.py` / `tui.py`: the terminal and full-screen front ends.
- `battery.py`: the USBNetwork battery reader.
- `pins.py`: the upstream pin check used by the weekly workflow.
- `feeds.py` / `feeds.toml`: the news feed list and its rendering into KOReader's `feed_config.lua`.
- `dashboard.py`, `k3dash/` and `k3-status.json`: the Grafana status display. The server-side
  `koreader-d00901-dashboard` command (Pillow, from the `dashboard` extra), the KUAL extension
  copied to the Kindle, and the Grafana dashboard. The monitor-01 systemd units are in
  `deploy/k3-dashboard/`.
- `errors.py`: `InstallerError` and its subclasses, which are reported to the user as one line.
- `logs.py`: logging setup (a debug log file on every run).

Tests are in `tests/`. They use a fake mounted Kindle and `file://` packages (`tests/conftest.py`),
so they need no network and no device. `tests/test_docs.py` checks that every flag is documented
and every pin is listed.

## CI

- `.github/workflows/ci.yml` runs `make ci`, `make build`, `make smoke` and `make version-check`
  on Python 3.14 for every push and PR.
- `.github/workflows/pins.yml` runs weekly (also from the Actions tab, and on PRs that touch the
  pins). It re-downloads every package in `packages.json`, verifies its sha256, and confirms it
  still holds every file the installer stages for each serial prefix and firmware range. If
  upstream drifts, it opens an issue, or comments on the open one. The same workflow fetches every
  feed in `feeds.toml` marked `check = true` and fails if one no longer parses as RSS/Atom.
- Dependabot opens weekly grouped updates for GitHub Actions and uv. Read the release notes of a
  major bump before merging. `make version-check` is skipped for Dependabot PRs, because they
  cannot bump the version. Their updates ship with the next bumped release.

## Releasing

1. In the same PR as the change, bump `version` in `pyproject.toml`
   (`uv version --bump patch`, `minor` or `major`) and add a section to `CHANGELOG.md`.
   `make version-check` fails any PR that changes `src/`, the dependencies or `uv.lock` since the
   last `vX.Y.Z` tag without raising the version, so every release gets a new version on PyPI.
2. After merging, tag the merge commit with the new version and push the tag:
   `git tag -a vX.Y.Z -m "koreader_D00901 X.Y.Z" && git push origin vX.Y.Z`.
3. `.github/workflows/release.yml` checks the tag against the version, runs `make ci`, builds and
   smoke-tests the wheel, and publishes it to PyPI through trusted publishing (no API token is
   stored anywhere).

The PyPI project page is built from `README.md`, so links there must be absolute URLs.

One-time PyPI setup (already done): a trusted publisher for project `koreader_D00901`, owner
`sethbarrett50`, repository `koreader_D00901`, workflow `release.yml` and environment `pypi`, plus
a GitHub environment named `pypi`.
