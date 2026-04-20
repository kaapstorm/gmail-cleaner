import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner import filters
from gmail_cleaner.cli import app

runner = CliRunner()


def test_list_filters_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['list-filters'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


def test_list_filters_prints_jsonl_one_per_line():
    creds = MagicMock()
    records = [
        {'id': 'f1', 'criteria': {'from': 'a@x'}, 'action': {}},
        {'id': 'f2', 'criteria': {'from': 'b@x'}, 'action': {}},
    ]
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_filters.filters.list_filters',
            return_value=records,
        ),
    ):
        result = runner.invoke(app, ['list-filters'])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert [json.loads(line) for line in lines] == records


def test_list_filters_empty_prints_nothing():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_filters.filters.list_filters',
            return_value=[],
        ),
    ):
        result = runner.invoke(app, ['list-filters'])
    assert result.exit_code == 0
    assert result.stdout == ''


def test_list_filters_by_id_prints_single_line():
    creds = MagicMock()
    one = {'id': 'f1', 'criteria': {}, 'action': {}}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_filters.filters.list_filters',
            return_value=[one],
        ) as mock_list,
    ):
        result = runner.invoke(app, ['list-filters', '--id', 'f1'])
    assert result.exit_code == 0
    mock_list.assert_called_once_with(creds, filter_id='f1')
    assert json.loads(result.stdout.strip()) == one


def test_list_filters_by_id_missing_exits_nonzero():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_filters.filters.list_filters',
            side_effect=filters.FilterNotFound('missing'),
        ),
    ):
        result = runner.invoke(app, ['list-filters', '--id', 'missing'])
    assert result.exit_code == 1
    # stderr may or may not be separated by CliRunner; check combined output.
    assert 'missing' in (result.stdout + (result.stderr or ''))
