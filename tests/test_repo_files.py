from pathlib import Path

GITHUB = Path(__file__).resolve().parent.parent / '.github'


def test_bug_form_asks_for_device_and_output():
    form = (GITHUB / 'ISSUE_TEMPLATE' / 'bug_report.yml').read_text()
    for needle in ('id: prefix', 'id: firmware', 'id: step', 'id: output', 'install.log', ';dumpMessages'):
        assert needle in form, needle


def test_pr_template_sections():
    body = (GITHUB / 'pull_request_template.md').read_text()
    for needle in ('## Summary', '## Changes', '## Testing', 'Closes #'):
        assert needle in body, needle


def test_dependabot_covers_actions_and_uv():
    config = (GITHUB / 'dependabot.yml').read_text()
    assert 'package-ecosystem: github-actions' in config
    assert 'package-ecosystem: uv' in config


def test_license_present():
    assert (GITHUB.parent / 'LICENSE').read_text().startswith('MIT License')
