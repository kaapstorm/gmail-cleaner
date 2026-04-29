import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from testsweet import test
from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


@test
def login_already_logged_in_prints_message():
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.login.gmail.get_user_email',
            return_value='user@example.com',
        ):
            result = runner.invoke(app, ['login'])
    assert result.exit_code == 0
    assert 'Already logged in as user@example.com' in result.output


@test
def login_missing_credentials_exits_with_error():
    with tempfile.TemporaryDirectory() as tmp:
        creds_path = Path(tmp) / 'credentials.json'
        with patch('gmail_cleaner.auth.load_token', return_value=None):
            with patch(
                'gmail_cleaner.auth.get_credentials_path',
                return_value=creds_path,
            ):
                result = runner.invoke(app, ['login'])
    assert result.exit_code == 1


@test
def login_missing_credentials_prints_message():
    with tempfile.TemporaryDirectory() as tmp:
        creds_path = Path(tmp) / 'credentials.json'
        with patch('gmail_cleaner.auth.load_token', return_value=None):
            with patch(
                'gmail_cleaner.auth.get_credentials_path',
                return_value=creds_path,
            ):
                result = runner.invoke(app, ['login'])
    assert 'credentials.json not found' in result.output


@test
def login_success_saves_token_and_prints_email():
    with tempfile.TemporaryDirectory() as tmp:
        creds_path = Path(tmp) / 'credentials.json'
        creds_path.write_text('{}')
        mock_creds = MagicMock()
        with patch('gmail_cleaner.auth.load_token', return_value=None):
            with patch(
                'gmail_cleaner.auth.get_credentials_path',
                return_value=creds_path,
            ):
                with patch(
                    'gmail_cleaner.auth.run_oauth_flow',
                    return_value=mock_creds,
                ):
                    with patch('gmail_cleaner.auth.save_token') as mock_save:
                        with patch(
                            'gmail_cleaner.commands.login.gmail.get_user_email',
                            return_value='user@example.com',
                        ):
                            result = runner.invoke(app, ['login'])
    assert result.exit_code == 0
    assert 'Logged in as user@example.com' in result.output
    mock_save.assert_called_once_with(mock_creds)
