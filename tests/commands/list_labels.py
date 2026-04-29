import json
from unittest.mock import MagicMock, patch

from testsweet import test
from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


@test
def list_labels_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['list-labels'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


@test
def list_labels_prints_jsonl_one_per_line():
    creds = MagicMock()
    records = [
        {'id': 'L1', 'name': 'A'},
        {'id': 'L2', 'name': 'B'},
    ]
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_labels.labels.list_labels',
            return_value=records,
        ),
    ):
        result = runner.invoke(app, ['list-labels'])
    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert [json.loads(line) for line in lines] == records


@test
def list_labels_empty_prints_nothing():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.list_labels.labels.list_labels',
            return_value=[],
        ),
    ):
        result = runner.invoke(app, ['list-labels'])
    assert result.exit_code == 0
    assert result.stdout == ''
