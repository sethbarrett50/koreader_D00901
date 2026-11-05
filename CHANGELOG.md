# Changelog

All notable changes to `koreader_D00901`. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

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

[0.2.1]: https://github.com/sethbarrett50/koreader_D00901/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/sethbarrett50/koreader_D00901/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/sethbarrett50/koreader_D00901/releases/tag/v0.1.0
