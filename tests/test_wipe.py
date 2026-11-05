import builtins

import pytest

from conftest import FW, PREFIX

from koreader_d00901 import device
from koreader_d00901.cli import main
from koreader_d00901.errors import DeviceError


@pytest.fixture
def books(kindle):
    docs = kindle.mount / 'documents'
    (docs / 'novel.mobi').write_bytes(b'book')
    (docs / 'novel.sdr').mkdir()
    (docs / 'novel.sdr' / 'novel.mbp').write_bytes(b'notes')
    (docs / 'KUAL-KDK-1.0.azw2').write_bytes(b'old kual')
    (docs / 'Dictionaries').mkdir()
    (docs / 'Dictionaries' / 'dict.mobi').write_bytes(b'dict')
    return kindle


def _names(paths):
    return [p.name for p in paths]


def test_list_books_keeps_kual_and_dictionaries(books):
    assert _names(device.list_books(books.mount)) == ['keep.txt', 'novel.mobi', 'novel.sdr']


def test_list_books_without_documents(tmp_path):
    assert device.list_books(tmp_path) == []


def test_wipe_books_deletes_only_listed_entries(books):
    docs = books.mount / 'documents'
    assert device.wipe_books(books.mount, device.list_books(books.mount)) == 3
    assert sorted(p.name for p in docs.iterdir()) == ['Dictionaries', 'KUAL-KDK-1.0.azw2']
    assert (docs / 'Dictionaries' / 'dict.mobi').is_file()


@pytest.mark.parametrize('target', ['outside', 'nested', 'kept'])
def test_wipe_books_refuses_anything_else(books, target):
    docs = books.mount / 'documents'
    path = {
        'outside': books.mount / 'Update_stale.bin',
        'nested': docs / 'novel.sdr' / 'novel.mbp',
        'kept': docs / 'dictionaries',
    }[target]
    with pytest.raises(DeviceError):
        device.wipe_books(books.mount, [path])
    assert (books.mount / 'Update_stale.bin').exists()
    assert (docs / 'novel.sdr' / 'novel.mbp').exists()


def _argv(kindle, *extra):
    return ['--mount', str(kindle.mount), '--fw', FW, '--prefix', PREFIX, '--cache', str(kindle.cache), *extra]


def _answers(monkeypatch, first):
    prompts = []

    def fake_input(prompt=''):
        prompts.append(prompt)
        return first if len(prompts) == 1 else ''

    monkeypatch.setattr(builtins, 'input', fake_input)
    return prompts


def test_cli_wipe_confirmed(books, monkeypatch, capsys):
    prompts = _answers(monkeypatch, 'wipe')
    assert main(_argv(books, '--wipe-books')) == 0
    docs = books.mount / 'documents'
    assert "Type 'wipe'" in prompts[0]
    assert 'will delete 3 entries' in capsys.readouterr().out
    assert sorted(p.name for p in docs.iterdir()) == ['Dictionaries', 'KUAL-KDK-1.0.azw2']
    assert (docs / 'KUAL-KDK-1.0.azw2').read_bytes() == b'kual'


def test_cli_wipe_declined_keeps_books(books, monkeypatch, capsys):
    _answers(monkeypatch, 'no')
    assert main(_argv(books, '--wipe-books')) == 0
    assert 'no books were deleted' in capsys.readouterr().out
    assert (books.mount / 'documents' / 'novel.mobi').is_file()


def test_cli_wipe_dry_run_lists_and_keeps(books, monkeypatch, capsys):
    prompts = _answers(monkeypatch, 'wipe')
    assert main(_argv(books, '--wipe-books', '--dry-run')) == 0
    out = capsys.readouterr().out
    assert 'would delete 3 entries' in out
    assert 'novel.sdr/' in out
    assert prompts == []
    assert (books.mount / 'documents' / 'novel.mobi').is_file()
