from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from unmagic import use

from gmail_cleaner.cli import app
from tests.fixtures import tmp_dir

runner = CliRunner()


def test_login_already_logged_in_prints_message():
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.login.gmail.get_user_email',
            return_value='user@example.com',
        ):
            result = runner.invoke(app, ['login'])
    assert result.exit_code == 0
    assert 'Already logged in as user@example.com' in result.output


@use(tmp_dir)
def test_login_missing_credentials_exits_with_error():
    tmp_path = tmp_dir()
    creds_path = tmp_path / 'credentials.json'
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            result = runner.invoke(app, ['login'])
    assert result.exit_code == 1


@use(tmp_dir)
def test_login_missing_credentials_prints_message():
    tmp_path = tmp_dir()
    creds_path = tmp_path / 'credentials.json'
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            result = runner.invoke(app, ['login'])
    assert 'credentials.json not found' in result.output


@use(tmp_dir)
def test_login_success_saves_token_and_prints_email():
    tmp_path = tmp_dir()
    creds_path = tmp_path / 'credentials.json'
    creds_path.write_text('{}')
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        with patch(
            'gmail_cleaner.auth.get_credentials_path', return_value=creds_path
        ):
            with patch(
                'gmail_cleaner.auth.run_oauth_flow', return_value=mock_creds
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
