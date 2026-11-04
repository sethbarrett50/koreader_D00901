import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text()

REQUIRED = {
    "What this does": ["jailbreak", "MKK", "KUAL", "KOReader", "USBNetwork"],
    "Before you start": [
        "Charge",
        "Settings > Registration",
        "wireless off",
        "bottom of the Settings",
        "serial prefix",
    ],
    "Which files your Kindle needs": [
        "B006",
        "k3g",
        "B008",
        "k3w",
        "B00A",
        "k3gb",
        "3.0-3.2",
        "3.3-3.4",
    ],
    "Running the installer": ["uv run k3_install.py"],
    "On the Kindle": [
        "Eject and unplug",
        "[HOME] > [MENU] > Settings > [MENU] > Update Your Kindle",
        "jailbreak, then MKK",
        "open KUAL from the library",
        "KOReader",
    ],
    "If something goes wrong": [
        "greyed out",
        "Never force",
        "about 15 seconds",
        "Reinstall MKK",
    ],
    "USBNetwork (optional)": [
        ";debugOn",
        "~usbNetwork",
        ";debugOff",
        "ssh root@192.168.2.2",
        "192.168.2.1",
        "passwordless only over USB with Wi-Fi mode off",
    ],
    "Pinned packages": [],
    "Credits": [
        "https://www.mobileread.com/forums/showthread.php?t=225030",
        "https://www.mobileread.com/forums/showthread.php?t=88004",
        "https://www.mobileread.com/forums/showthread.php?t=203326",
        "https://github.com/koreader/koreader",
    ],
}


def section(title):
    match = re.search(
        rf"^## {re.escape(title)}\n(.*?)(?=^## |\Z)", README, re.MULTILINE | re.DOTALL
    )
    assert match, f"missing section: {title}"
    return match.group(1)


@pytest.mark.parametrize("title", REQUIRED)
def test_section_has_required_text(title):
    body = section(title)
    for needle in REQUIRED[title]:
        assert needle in body, f"{title!r} lacks {needle!r}"


def test_risk_note_near_top():
    assert "at your own risk" in README[:500]


def test_every_flag_documented():
    source = (ROOT / "k3_install.py").read_text()
    flags = re.findall(r'add_argument\(\s*"(--[a-z-]+)"', source)
    assert flags
    body = section("Running the installer")
    for flag in flags:
        assert flag in body, f"flag {flag} not documented"
    assert body.index("--dry-run") < body.index("uv run k3_install.py\n")


def test_pins_listed():
    manifest = json.loads((ROOT / "packages.json").read_text())
    body = section("Pinned packages")
    for name, pkg in manifest.items():
        assert pkg["filename"] in body, f"{name} filename missing"
        assert pkg["sha256"][:12] in body, f"{name} sha256 prefix missing"
