from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


def test_whoami_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['whoami'])
    assert result.exit_code == 1


def test_whoami_not_logged_in_prints_message():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['whoami'])
    assert 'Not logged in' in result.output


def test_whoami_prints_email():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        'emailAddress': 'user@example.com'
    }
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.whoami.build', return_value=mock_service
        ):
            result = runner.invoke(app, ['whoami'])
    assert result.exit_code == 0
    assert 'user@example.com' in result.output
