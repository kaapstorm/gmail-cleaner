from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


def test_delete_query_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['delete-query', 'in:inbox'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


def test_delete_query_no_matches_exits_cleanly():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.scan_for_messages',
            return_value=(0, False),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.delete_messages_matching',
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
            'gmail_cleaner.commands.delete_query.gmail.scan_for_messages',
            return_value=(3, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.delete_messages_matching',
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
            'gmail_cleaner.commands.delete_query.gmail.scan_for_messages',
            return_value=(3, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.delete_messages_matching',
            return_value=3,
        ) as del_match,
    ):
        result = runner.invoke(app, ['delete-query', 'in:inbox'], input='y\n')
    assert result.exit_code == 0
    del_match.assert_called_once()
    assert 'Deleted 3 messages' in result.stderr


def test_delete_query_force_skips_confirmation():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.scan_for_messages',
            return_value=(1, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_query.gmail.delete_messages_matching',
            return_value=1,
        ) as del_match,
    ):
        result = runner.invoke(
            app,
            ['delete-query', '--force', 'in:inbox'],
        )
    assert result.exit_code == 0
    del_match.assert_called_once()
