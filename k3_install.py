# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Install KOReader on a Kindle Keyboard (K3)."""

import json
from pathlib import Path

VARIANTS = {"B006": "k3g", "B008": "k3w", "B00A": "k3gb"}
FIRMWARE_RANGES = ("3.0-3.2", "3.3-3.4")


def load_manifest() -> dict[str, dict[str, str]]:
    return json.loads((Path(__file__).parent / "packages.json").read_text())


def select_files(fw: str, prefix: str, usbnet: bool) -> dict[str, str | None]:
    """Map a firmware range and serial prefix to the archive members to install."""
    prefix = prefix.upper()
    if prefix not in VARIANTS:
        raise ValueError(f"unsupported serial prefix: {prefix!r}")
    if fw not in FIRMWARE_RANGES:
        raise ValueError(f"unsupported firmware range: {fw!r}")
    variant = VARIANTS[prefix]
    suffix = "-3.0-to-3.2" if fw == "3.0-3.2" else ""
    return {
        "jailbreak": f"Jailbreak/Update_jailbreak_0.13.N_{variant}{suffix}_install.bin",
        "mkk": f"DevCerts/Update_mkk-20141129-{variant}-{prefix}_install.bin",
        "usbnet": f"Update_usbnetwork_0.57.N_{variant}_install.bin" if usbnet else None,
        "kual": "KUAL-KDK-1.0.azw2",
    }
