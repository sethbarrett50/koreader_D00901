"""Exceptions raised by the installer.

Everything the user can cause or fix (a bad choice, a missing Kindle, a bad download) is an
InstallerError, which the CLI and TUI report as one line instead of a traceback.
"""


class InstallerError(Exception):
    """Base class for expected failures that are reported to the user without a traceback."""


class ConfigError(InstallerError, ValueError):
    """An unsupported firmware range, serial prefix, or option."""


class PackageError(InstallerError):
    """A package could not be downloaded, or lacks the file this install needs."""


class ChecksumError(PackageError, ValueError):
    """Downloaded or cached bytes do not match the manifest sha256."""


class UnsafeArchiveError(PackageError, ValueError):
    """A package name or archive member would escape its directory, or is a link."""


class DeviceError(InstallerError):
    """The Kindle is not mounted where expected, or could not be ejected."""
