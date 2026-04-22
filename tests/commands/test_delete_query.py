from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cleanup import Preview, ScanResult
from gmail_cleaner.cli import app

runner = CliRunner()


def test_delete_query_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['delete-query', 'in:inbox'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


def test_delete_query_no_matches_exits_cleanly():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.scan_for_messages',
            return_value=ScanResult(0, False),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.delete_messages_matching',
        ) as del_match,
    ):
        result = runner.invoke(app, ['delete-query', 'in:inbox'])
    assert result.exit_code == 0
    assert 'No matching messages' in result.stdout
    del_match.assert_not_called()


def test_delete_query_aborted_by_user():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.scan_for_messages',
            return_value=ScanResult(3, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.delete_messages_matching',
        ) as del_match,
    ):
        result = runner.invoke(app, ['delete-query', 'in:inbox'], input='n\n')
    assert result.exit_code == 1
    del_match.assert_not_called()


def test_delete_query_deletes():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.scan_for_messages',
            return_value=ScanResult(3, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.delete_messages_matching',
            return_value=3,
        ) as del_match,
    ):
        result = runner.invoke(app, ['delete-query', 'in:inbox'], input='y\n')
    assert result.exit_code == 0
    del_match.assert_called_once()
    assert 'Deleted 3 messages' in result.stderr


def test_delete_query_dry_run_shows_count_and_sample():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.preview_query',
            return_value=Preview(total=1523, sample_ids=['m1', 'm2']),
        ) as preview,
        patch(
            'gmail_cleaner.commands._progress.gmail.iter_message_headers',
            return_value=iter(
                [
                    {
                        'Date': 'Mon, 13 Apr 2026 14:30:00 -0400',
                        'From': 'Alice <a@example.com>',
                        'Subject': 'Re: meetup',
                    },
                    {
                        'Date': 'bogus',
                        'From': 'Bob',
                        'Subject': 'Weekly digest',
                    },
                ],
            ),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.delete_messages_matching',
        ) as del_match,
    ):
        result = runner.invoke(
            app,
            ['delete-query', '--dry-run', 'in:inbox'],
        )
    assert result.exit_code == 0
    preview.assert_called_once_with(creds, query='in:inbox')
    del_match.assert_not_called()
    assert 'DRY RUN' in result.stdout
    assert '1,523 matches' in result.stdout
    assert '2026-04-13  Alice <a@example.com>  Re: meetup' in result.stdout
    assert 'bogus  Bob  Weekly digest' in result.stdout


def test_delete_query_dry_run_no_matches_still_shows_zero():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.preview_query',
            return_value=Preview(total=0, sample_ids=[]),
        ),
    ):
        result = runner.invoke(
            app,
            ['delete-query', '--dry-run', 'in:inbox'],
        )
    assert result.exit_code == 0
    assert '0 matches' in result.stdout


def test_delete_query_force_skips_confirmation():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.scan_for_messages',
            return_value=ScanResult(1, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.cleanup.delete_messages_matching',
            return_value=1,
        ) as del_match,
    ):
        result = runner.invoke(
            app,
            ['delete-query', '--force', 'in:inbox'],
        )
    assert result.exit_code == 0
    del_match.assert_called_once()
