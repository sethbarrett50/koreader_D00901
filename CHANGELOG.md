# Changelog

All notable changes to `koreader_D00901`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.4.1] - 2026-11-05

### Fixed

- TUI: with many books on the Kindle, the delete-books dialog ran off the screen and hid its
  **Delete them** / **Keep my books** buttons (#26). The buttons and a short explanation of each
  choice now always stay visible, and the list scrolls between them. The dialog fits narrow
  terminals, **Keep my books** has focus, and Esc keeps the books.

## [0.4.0] - 2026-11-05

### Added

- Grafana status display (#4): a K3 on its charger shows a small `k3-status` dashboard on its e-ink
  screen and refreshes it every few minutes.
  - `koreader-d00901-dashboard render` (with the new `dashboard` extra) renders the dashboard through
    Grafana's image renderer and turns it into a 600x800, 16-grey PNG.
    `koreader-d00901-dashboard grafana-json` prints the dashboard to import.
  - `--dashboard-url URL` and `--dashboard-interval SEC` (also in the TUI) install a KUAL extension
    that fetches the image and draws it with KOReader's `fbink`.
  - Setup for monitor-01: systemd units in `deploy/k3-dashboard/`, the renderer compose snippet and
    the router rule in `docs/dashboard.md`.

## [0.3.0] - 2026-11-05

### Added

- News feeds (#5): the installer writes a curated list of 13 RSS/Atom feeds (security, engineering,
  research) to KOReader's news downloader, which each Kindle syncs itself over Wi-Fi. The list is
  `feeds.toml` in the package; `--feeds FILE` uses your own, and `--only feeds` updates just the
  list. `python -m koreader_d00901.feeds --check` fetches every feed, and the weekly pin workflow
  runs it. See `docs/rss.md`.
- TUI parity with the CLI: a **Steps** checklist (`--only`, `--usbnet`), a **News feed list** field
  (`--feeds`) and a **Show debug log** toggle (`--verbose`).

## [0.2.1] - 2026-11-05

### Changed

- Documentation split into a short README plus `docs/install.md`, `docs/usbnetwork.md`,
  `docs/battery.md` and `docs/development.md`, with a TUI screenshot (#21).

### Fixed

- TUI: the log clipped long lines mid-word on narrow panels, and the USBNetwork checkbox label was cut off.

## [0.2.0] - 2026-11-05

### Added

- `koreader-d00901-battery`: reads a unit's battery over USBNetwork SSH and logs readings per serial
  number, printing the drain since the previous reading (#2).
- `koreader-d00901 --only STEP`: run only the chosen steps, for example `--only usbnet` on a unit
  that is already set up.
- `docs/battery.md`: the measurement procedure and the per-unit table.

## [0.1.0] - 2026-11-05

First release on PyPI.

### Added

- Installer for KOReader on the Kindle Keyboard (K3): jailbreak, MKK, the 2025 developer keystore,
  optional USBNetwork, KUAL and KOReader. Packages are pinned by sha256 and never executed on the host.
- `koreader-d00901-tui`: a full-screen installer with step status, mount detection, an Eject button
  and copy progress (#10).
- `--wipe-books`: delete the existing books in `documents/` first, after confirmation (#11).
- Weekly CI check that every pinned upstream package still downloads and matches (#6).

### Fixed

- KUAL failed with "not signed by a registered developer" because MKK's 2014 certificates expired
  in April 2025. The installer now applies NiLuJe's 2025 keystore update after MKK.

[0.4.1]: https://github.com/sethbarrett50/koreader_D00901/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/sethbarrett50/koreader_D00901/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/sethbarrett50/koreader_D00901/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/sethbarrett50/koreader_D00901/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/sethbarrett50/koreader_D00901/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sethbarrett50/koreader_D00901/releases/tag/v0.1.0
