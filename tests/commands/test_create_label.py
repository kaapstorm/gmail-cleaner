import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner
from unmagic import use

from gmail_cleaner import labels
from gmail_cleaner.cli import app
from tests.fixtures import tmp_dir

runner = CliRunner()


def _write_jsonl(path, records):
    with path.open('w', encoding='utf-8') as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write('\n')


def test_create_label_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['create-label', '-'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


@use(tmp_dir)
def test_create_label_reads_jsonl_from_file_and_prints_created():
    creds = MagicMock()
    path = tmp_dir() / 'labels.jsonl'
    inputs = [{'name': 'A'}, {'name': 'B'}]
    outputs = [{'id': 'L1', **inputs[0]}, {'id': 'L2', **inputs[1]}]
    _write_jsonl(path, inputs)
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.create_label.labels.create_labels',
            return_value=outputs,
        ) as mock_create,
    ):
        result = runner.invoke(app, ['create-label', str(path)])
    assert result.exit_code == 0
    mock_create.assert_called_once_with(creds, inputs)
    printed = [
        json.loads(line) for line in result.stdout.splitlines() if line.strip()
    ]
    assert printed == outputs


def test_create_label_reads_jsonl_from_stdin():
    creds = MagicMock()
    inputs = [{'name': 'A'}]
    outputs = [{'id': 'L1', **inputs[0]}]
    stdin_text = json.dumps(inputs[0]) + '\n'
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.create_label.labels.create_labels',
            return_value=outputs,
        ) as mock_create,
    ):
        result = runner.invoke(app, ['create-label', '-'], input=stdin_text)
    assert result.exit_code == 0
    mock_create.assert_called_once_with(creds, inputs)
    assert json.loads(result.stdout.strip()) == outputs[0]


@use(tmp_dir)
def test_create_label_malformed_json_reports_line_number():
    creds = MagicMock()
    path = tmp_dir() / 'labels.jsonl'
    with path.open('w', encoding='utf-8') as handle:
        handle.write(json.dumps({'name': 'A'}) + '\n')
        handle.write('{not valid json\n')
    with patch('gmail_cleaner.auth.load_token', return_value=creds):
        result = runner.invoke(app, ['create-label', str(path)])
    assert result.exit_code != 0
    combined = result.stdout + (result.stderr or '')
    assert ':2' in combined
    assert str(path) in combined


@use(tmp_dir)
def test_create_label_midbatch_failure_prints_created_and_exits_nonzero():
    creds = MagicMock()
    path = tmp_dir() / 'labels.jsonl'
    inputs = [{'name': 'A'}, {'name': 'A'}]
    _write_jsonl(path, inputs)
    good = {'id': 'L1', **inputs[0]}
    err = labels.CreateLabelsError([good], failed_index=1)
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.create_label.labels.create_labels',
            side_effect=err,
        ),
    ):
        result = runner.invoke(app, ['create-label', str(path)])
    assert result.exit_code == 1
    printed = [
        json.loads(line) for line in result.stdout.splitlines() if line.strip()
    ]
    assert printed == [good]
