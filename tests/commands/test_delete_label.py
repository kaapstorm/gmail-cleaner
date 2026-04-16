from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cli import app

runner = CliRunner()


def test_delete_label_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['delete-label', 'MySpace'])
    assert result.exit_code == 1
    assert 'Not logged in' in result.stdout


def test_delete_label_not_found_exits_with_error():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.find_label',
            return_value=None,
        ),
    ):
        result = runner.invoke(app, ['delete-label', 'MySpace'])
    assert result.exit_code == 1
    assert "Label 'MySpace' not found" in result.stdout


def test_delete_label_aborted_by_user():
    creds = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.find_label',
            return_value=(label, 5, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.delete_label_completely',
        ) as del_complete,
    ):
        result = runner.invoke(
            app,
            ['delete-label', 'MySpace'],
            input='n\n',
        )
    assert result.exit_code == 1
    del_complete.assert_not_called()


def test_delete_label_deletes_messages_filters_and_label():
    creds = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.find_label',
            return_value=(label, 1523, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.delete_label_completely',
            return_value=(1523, 2),
        ) as del_complete,
    ):
        result = runner.invoke(
            app,
            ['delete-label', '--force', 'MySpace'],
        )
    assert result.exit_code == 0
    del_complete.assert_called_once()
    assert (
        "Deleted 1,523 messages, 2 filters, and label 'MySpace'"
        in result.stderr
    )


def test_delete_label_zero_messages_still_proceeds():
    creds = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.find_label',
            return_value=(label, 0, False),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.gmail.delete_label_completely',
            return_value=(0, 0),
        ) as del_complete,
    ):
        result = runner.invoke(app, ['delete-label', '--force', 'X'])
    assert result.exit_code == 0
    del_complete.assert_called_once()
    assert 'Deleted 0 messages, 0 filters' in result.stderr
