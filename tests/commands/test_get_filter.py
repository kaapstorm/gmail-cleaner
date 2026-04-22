import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner import filters
from gmail_cleaner.cli import app

runner = CliRunner()


def test_get_filter_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['get-filter', 'f1'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


def test_get_filter_prints_single_json_line():
    creds = MagicMock()
    record = {'id': 'f1', 'criteria': {}, 'action': {}}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.get_filter.filters.get_filter',
            return_value=record,
        ) as mock_get,
    ):
        result = runner.invoke(app, ['get-filter', 'f1'])
    assert result.exit_code == 0
    mock_get.assert_called_once_with(creds, 'f1')
    assert json.loads(result.stdout.strip()) == record


def test_get_filter_missing_exits_nonzero():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.get_filter.filters.get_filter',
            side_effect=filters.FilterNotFound('missing'),
        ),
    ):
        result = runner.invoke(app, ['get-filter', 'missing'])
    assert result.exit_code == 1
    assert 'missing' in (result.stdout + (result.stderr or ''))
