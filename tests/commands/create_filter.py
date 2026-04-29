import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from testsweet import test
from typer.testing import CliRunner

from gmail_cleaner import filters
from gmail_cleaner.cli import app

runner = CliRunner()


def _write_jsonl(path, records):
    with path.open('w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write('\n')


@test
def create_filter_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['create-filter', '-'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


@test
def create_filter_reads_jsonl_from_file_and_prints_created():
    with tempfile.TemporaryDirectory() as tmp:
        creds = MagicMock()
        path = Path(tmp) / 'filters.jsonl'
        inputs = [
            {'criteria': {'from': 'a@x'}, 'action': {'addLabelIds': ['L1']}},
            {'criteria': {'from': 'b@x'}, 'action': {'addLabelIds': ['L2']}},
        ]
        outputs = [{'id': 'f1', **inputs[0]}, {'id': 'f2', **inputs[1]}]
        _write_jsonl(path, inputs)
        with (
            patch('gmail_cleaner.auth.load_token', return_value=creds),
            patch(
                'gmail_cleaner.commands.create_filter.filters.create_filters',
                return_value=outputs,
            ) as mock_create,
        ):
            result = runner.invoke(app, ['create-filter', str(path)])
    assert result.exit_code == 0
    mock_create.assert_called_once_with(creds, inputs)
    printed = [
        json.loads(line) for line in result.stdout.splitlines() if line.strip()
    ]
    assert printed == outputs


@test
def create_filter_reads_jsonl_from_stdin():
    creds = MagicMock()
    inputs = [{'criteria': {'from': 'a@x'}, 'action': {}}]
    outputs = [{'id': 'f1', **inputs[0]}]
    stdin_text = json.dumps(inputs[0]) + '\n'
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.create_filter.filters.create_filters',
            return_value=outputs,
        ) as mock_create,
    ):
        result = runner.invoke(app, ['create-filter', '-'], input=stdin_text)
    assert result.exit_code == 0
    mock_create.assert_called_once_with(creds, inputs)
    assert json.loads(result.stdout.strip()) == outputs[0]


@test
def create_filter_ignores_blank_lines():
    with tempfile.TemporaryDirectory() as tmp:
        creds = MagicMock()
        path = Path(tmp) / 'filters.jsonl'
        inputs = [{'criteria': {'from': 'a@x'}, 'action': {}}]
        outputs = [{'id': 'f1', **inputs[0]}]
        with path.open('w', encoding='utf-8') as handle:
            handle.write('\n')
            handle.write(json.dumps(inputs[0]) + '\n')
            handle.write('   \n')
        with (
            patch('gmail_cleaner.auth.load_token', return_value=creds),
            patch(
                'gmail_cleaner.commands.create_filter.filters.create_filters',
                return_value=outputs,
            ) as mock_create,
        ):
            result = runner.invoke(app, ['create-filter', str(path)])
    assert result.exit_code == 0
    mock_create.assert_called_once_with(creds, inputs)


@test
def create_filter_malformed_json_reports_line_number():
    with tempfile.TemporaryDirectory() as tmp:
        creds = MagicMock()
        path = Path(tmp) / 'filters.jsonl'
        with path.open('w', encoding='utf-8') as handle:
            handle.write(json.dumps({'criteria': {}, 'action': {}}) + '\n')
            handle.write('{not valid json\n')
        with patch('gmail_cleaner.auth.load_token', return_value=creds):
            result = runner.invoke(app, ['create-filter', str(path)])
        assert result.exit_code != 0
        combined = result.stdout + (result.stderr or '')
        assert ':2' in combined
        assert str(path) in combined


@test
def create_filter_midbatch_failure_prints_created_and_exits_nonzero():
    with tempfile.TemporaryDirectory() as tmp:
        creds = MagicMock()
        path = Path(tmp) / 'filters.jsonl'
        inputs = [
            {'criteria': {'from': 'a@x'}, 'action': {}},
            {'bogus': True},
        ]
        _write_jsonl(path, inputs)
        good = {'id': 'f1', **inputs[0]}
        err = filters.CreateFiltersError([good], failed_index=1)
        with (
            patch('gmail_cleaner.auth.load_token', return_value=creds),
            patch(
                'gmail_cleaner.commands.create_filter.filters.create_filters',
                side_effect=err,
            ),
        ):
            result = runner.invoke(app, ['create-filter', str(path)])
    assert result.exit_code == 1
    printed = [
        json.loads(line) for line in result.stdout.splitlines() if line.strip()
    ]
    assert printed == [good]
