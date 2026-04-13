import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from unmagic import fixture, use

from gmail_cleaner.cli import app

runner = CliRunner()


@fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


def test_login_already_logged_in_prints_message():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        'emailAddress': 'user@example.com'
    }
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.login.build', return_value=mock_service
        ):
            result = runner.invoke(app, ['login'])
    assert result.exit_code == 0
    assert 'Already logged in as user@example.com' in result.output


@use(tmp_dir)
def test_login_missing_credentials_exits_with_error():
    d = tmp_dir()
    creds_path = d / 'credentials.json'
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            result = runner.invoke(app, ['login'])
    assert result.exit_code == 1


@use(tmp_dir)
def test_login_missing_credentials_prints_message():
    d = tmp_dir()
    creds_path = d / 'credentials.json'
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            result = runner.invoke(app, ['login'])
    assert 'credentials.json not found' in result.output


@use(tmp_dir)
def test_login_success_saves_token_and_prints_email():
    d = tmp_dir()
    creds_path = d / 'credentials.json'
    creds_path.write_text('{}')
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        'emailAddress': 'user@example.com'
    }
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            with patch(
                'gmail_cleaner.auth.run_oauth_flow', return_value=mock_creds
            ):
                with patch('gmail_cleaner.auth.save_token') as mock_save:
                    with patch(
                        'gmail_cleaner.commands.login.build',
                        return_value=mock_service,
                    ):
                        result = runner.invoke(app, ['login'])
    assert result.exit_code == 0
    assert 'Logged in as user@example.com' in result.output
    mock_save.assert_called_once_with(mock_creds)
