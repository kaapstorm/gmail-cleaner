from unittest.mock import patch

from testsweet import test
from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


@test
def logout_calls_delete_token():
    with patch('gmail_cleaner.auth.delete_token') as mock_delete:
        result = runner.invoke(app, ['logout'])
    assert result.exit_code == 0
    mock_delete.assert_called_once()


@test
def logout_prints_logged_out():
    with patch('gmail_cleaner.auth.delete_token'):
        result = runner.invoke(app, ['logout'])
    assert 'Logged out' in result.output


@test
def logout_idempotent():
    # delete_token is a no-op if token doesn't exist; logout should still succeed
    with patch('gmail_cleaner.auth.delete_token'):
        result = runner.invoke(app, ['logout'])
    assert result.exit_code == 0
