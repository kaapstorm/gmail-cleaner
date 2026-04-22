import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from unmagic import use

from gmail_cleaner import filters
from gmail_cleaner.cli import app
from tests.fixtures import tmp_dir

runner = CliRunner()


def _write_jsonl(path, records):
    with path.open('w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write('\n')


def test_create_filter_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['create-filter', '-'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


@use(tmp_dir)
def test_create_filter_reads_jsonl_from_file_and_prints_created():
    creds = MagicMock()
    path = tmp_dir() / 'filters.jsonl'
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


def test_create_filter_reads_jsonl_from_stdin():
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


@use(tmp_dir)
def test_create_filter_ignores_blank_lines():
    creds = MagicMock()
    path = tmp_dir() / 'filters.jsonl'
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


@use(tmp_dir)
def test_create_filter_malformed_json_reports_line_number():
    creds = MagicMock()
    path = tmp_dir() / 'filters.jsonl'
    with path.open('w', encoding='utf-8') as handle:
        handle.write(json.dumps({'criteria': {}, 'action': {}}) + '\n')
        handle.write('{not valid json\n')
    with patch('gmail_cleaner.auth.load_token', return_value=creds):
        result = runner.invoke(app, ['create-filter', str(path)])
    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or '')
    assert ':2' in combined
    assert str(path) in combined


@use(tmp_dir)
def test_create_filter_midbatch_failure_prints_created_and_exits_nonzero():
    creds = MagicMock()
    path = tmp_dir() / 'filters.jsonl'
    inputs = [
        {'criteria': {'from': 'a@x'}, 'action': {}},
        {'bogus': True},
    ]
    _write_jsonl(path, inputs)
    good = {'id': 'f1', **inputs[0]}
    err = filters.CreateFiltersError([good])
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
