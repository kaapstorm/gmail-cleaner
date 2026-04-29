from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


def test_old_labels_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['old-labels'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


def test_old_labels_bad_age_exits_with_usage_error():
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        result = runner.invoke(app, ['old-labels', '--age', 'forever'])
    assert result.exit_code == 2
    assert 'must look like' in result.stderr.lower()


def test_old_labels_lists_only_labels_with_no_recent_messages():
    mock_creds = MagicMock()
    old = [
        {'id': 'L1', 'name': 'Apple', 'type': 'user'},
        {'id': 'L3', 'name': 'Cherry', 'type': 'user'},
    ]
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.old_labels.gmail.find_old_labels',
            return_value=(old, 3),
        ):
            result = runner.invoke(app, ['old-labels'])
    assert result.exit_code == 0
    assert result.stdout.splitlines() == ['Apple', 'Cherry']
    assert '2 of 3 labels have no messages newer than 2y' in result.stderr


def test_old_labels_summary_uses_custom_age():
    mock_creds = MagicMock()
    with patch('gmail_cleaner.auth.load_token', return_value=mock_creds):
        with patch(
            'gmail_cleaner.commands.old_labels.gmail.find_old_labels',
            return_value=([], 0),
        ):
            result = runner.invoke(app, ['old-labels', '--age', '6m'])
    assert result.exit_code == 0
    assert '0 of 0 labels have no messages newer than 6m' in result.stderr
