from unittest.mock import MagicMock, patch

from testsweet import test
from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


@test
def whoami_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['whoami'])
    assert result.exit_code == 1


@test
def whoami_not_logged_in_prints_message():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['whoami'])
    assert 'Not logged in' in result.output


@test
def whoami_prints_email():
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.whoami.gmail.get_user_email',
            return_value='user@example.com',
        ):
            result = runner.invoke(app, ['whoami'])
    assert result.exit_code == 0
    assert 'user@example.com' in result.output
