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


def test_export_inbox_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['export-inbox', '/tmp/out.jsonl'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


@use(tmp_dir)
def test_export_inbox_writes_jsonl_to_file():
    out = tmp_dir() / 'out.jsonl'
    mock_creds = MagicMock()
    ids = ['a', 'b', 'c']
    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.export.iter_inbox_ids',
            return_value=iter(ids),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.build_service',
            return_value=MagicMock(),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.export.fetch_message_export',
            side_effect=lambda _svc, mid: _record(mid),
        ),
    ):
        result = runner.invoke(app, ['export-inbox', str(out)])
    assert result.exit_code == 0, result.output
    lines = out.read_text().splitlines()
    assert [json.loads(line)['id'] for line in lines] == ids


def test_export_inbox_writes_to_stdout_when_output_is_dashdash():
    mock_creds = MagicMock()
    ids = ['a', 'b']
    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.export.iter_inbox_ids',
            return_value=iter(ids),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.build_service',
            return_value=MagicMock(),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.export.fetch_message_export',
            side_effect=lambda _svc, mid: _record(mid),
        ),
    ):
        result = runner.invoke(app, ['export-inbox', '--', '--'])
    assert result.exit_code == 0, result.output
    lines = [line for line in result.stdout.splitlines() if line]
    assert [json.loads(line)['id'] for line in lines] == ids


@use(tmp_dir)
def test_export_inbox_skips_messages_that_error():
    from googleapiclient.errors import HttpError

    out = tmp_dir() / 'out.jsonl'
    mock_creds = MagicMock()
    ids = ['a', 'b', 'c']

    def _fetch(_svc, mid):
        if mid == 'b':
            raise HttpError(MagicMock(status=404), b'')
        return _record(mid)

    with (
        patch('gmail_cleaner.auth.load_token', return_value=mock_creds),
        patch(
            'gmail_cleaner.commands.export_inbox.export.iter_inbox_ids',
            return_value=iter(ids),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.gmail.build_service',
            return_value=MagicMock(),
        ),
        patch(
            'gmail_cleaner.commands.export_inbox.export.fetch_message_export',
            side_effect=_fetch,
        ),
    ):
        result = runner.invoke(app, ['export-inbox', str(out)])
    assert result.exit_code == 0, result.output
    lines = out.read_text().splitlines()
    assert [json.loads(line)['id'] for line in lines] == ['a', 'c']
    assert 'skipped b' in result.stderr
