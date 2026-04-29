import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from unmagic import use

from gmail_cleaner.cli import app
from tests.fixtures import tmp_dir

runner = CliRunner()


def _record(mid: str) -> dict:
    return {
        'id': mid,
        'thread_id': f't-{mid}',
        'date': '2026-04-13T14:30:00-04:00',
        'from': 'Alice <alice@example.com>',
        'to': ['me@example.com'],
        'cc': [],
        'subject': f'Subject {mid}',
        'list_id': None,
        'list_unsubscribe': None,
        'labels': ['INBOX'],
        'snippet': 'hi',
        'attachments': [],
    }


def _iter_records(ids):
    def _side_effect(_creds, *, on_error):
        return iter(_record(mid) for mid in ids)

    return _side_effect


def test_export_inbox_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['export-inbox', '/tmp/out.jsonl'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


@use(tmp_dir)
def test_export_inbox_writes_jsonl_to_file():
    out = tmp_dir() / 'out.jsonl'
    mock_creds = MagicMock()
    ids = ['a', 'b', 'c']
    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.export.iter_inbox_records',
            side_effect=_iter_records(ids),
        ),
    ):
        result = runner.invoke(app, ['export-inbox', str(out)])
    assert result.exit_code == 0, result.output
    lines = out.read_text().splitlines()
    assert [json.loads(line)['id'] for line in lines] == ids


def test_export_inbox_writes_to_stdout_when_output_is_dash():
    mock_creds = MagicMock()
    ids = ['a', 'b']
    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.export.iter_inbox_records',
            side_effect=_iter_records(ids),
        ),
    ):
        result = runner.invoke(app, ['export-inbox', '-'])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line]
    assert [json.loads(line)['id'] for line in lines] == ids


@use(tmp_dir)
def test_export_inbox_skips_messages_that_error():
    from googleapiclient.errors import HttpError

    out = tmp_dir() / 'out.jsonl'
    mock_creds = MagicMock()

    def _side_effect(_creds, *, on_error):
        for mid in ['a', 'b', 'c']:
            if mid == 'b':
                on_error(mid, HttpError(MagicMock(status=404), b''))
                continue
            yield _record(mid)

    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.export.iter_inbox_records',
            side_effect=_side_effect,
        ),
    ):
        result = runner.invoke(app, ['export-inbox', str(out)])
    assert result.exit_code == 0, result.output
    lines = out.read_text().splitlines()
    assert [json.loads(line)['id'] for line in lines] == ['a', 'c']
    assert 'skipped b' in result.stderr
