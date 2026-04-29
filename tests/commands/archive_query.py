from unittest.mock import MagicMock, patch

from testsweet import test
from typer.testing import CliRunner

from gmail_cleaner.cleanup import Preview, ScanResult
from gmail_cleaner.cli import app

runner = CliRunner()


@test
def archive_query_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['archive-query', 'in:inbox'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


@test
def archive_query_no_matches_exits_cleanly():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.scan_for_messages',
            return_value=ScanResult(0, False),
        ),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.archive_messages_matching',
        ) as archive,
    ):
        result = runner.invoke(app, ['archive-query', 'in:inbox'])
    assert result.exit_code == 0
    assert 'No matching messages' in result.stdout
    archive.assert_not_called()


@test
def archive_query_aborted_by_user():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.scan_for_messages',
            return_value=ScanResult(3, True),
        ),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.archive_messages_matching',
        ) as archive,
    ):
        result = runner.invoke(app, ['archive-query', 'in:inbox'], input='n\n')
    assert result.exit_code == 1
    archive.assert_not_called()


@test
def archive_query_archives():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.scan_for_messages',
            return_value=ScanResult(3, True),
        ),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.archive_messages_matching',
            return_value=3,
        ) as archive,
    ):
        result = runner.invoke(app, ['archive-query', 'in:inbox'], input='y\n')
    assert result.exit_code == 0
    archive.assert_called_once()
    assert 'Archived 3 messages' in result.stderr


@test
def archive_query_dry_run_shows_count_and_sample():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.preview_query',
            return_value=Preview(total=42, sample_ids=['m1']),
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
                ],
            ),
        ),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.archive_messages_matching',
        ) as archive,
    ):
        result = runner.invoke(
            app,
            ['archive-query', '--dry-run', 'in:inbox'],
        )
    assert result.exit_code == 0
    preview.assert_called_once_with(creds, query='in:inbox')
    archive.assert_not_called()
    assert 'DRY RUN' in result.stdout
    assert '42 matches' in result.stdout


@test
def archive_query_force_skips_confirmation():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.scan_for_messages',
            return_value=ScanResult(1, True),
        ),
        patch(
            'gmail_cleaner.commands.archive_query.cleanup.archive_messages_matching',
            return_value=1,
        ) as archive,
    ):
        result = runner.invoke(
            app,
            ['archive-query', '--force', 'in:inbox'],
        )
    assert result.exit_code == 0
    archive.assert_called_once()
