from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cleanup import (
    LabelDeletion,
    LabelLookup,
    LabelPreview,
)
from gmail_cleaner.cli import app

runner = CliRunner()


def test_delete_label_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['delete-label', 'MySpace'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


def test_delete_label_not_found_exits_with_error():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.find_label',
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
            'gmail_cleaner.commands.delete_label.cleanup.find_label',
            return_value=LabelLookup(label, 5, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.delete_label_completely',
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
            'gmail_cleaner.commands.delete_label.cleanup.find_label',
            return_value=LabelLookup(label, 1523, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.delete_label_completely',
            return_value=LabelDeletion(1523, 2),
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
            'gmail_cleaner.commands.delete_label.cleanup.find_label',
            return_value=LabelLookup(label, 0, False),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.delete_label_completely',
            return_value=LabelDeletion(0, 0),
        ) as del_complete,
    ):
        result = runner.invoke(app, ['delete-label', '--force', 'X'])
    assert result.exit_code == 0
    del_complete.assert_called_once()
    assert 'Deleted 0 messages, 0 filters' in result.stderr


def test_delete_label_dry_run_shows_count_filters_and_sample():
    creds = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    preview = LabelPreview(
        total=1523,
        sample_ids=['m1'],
        filters=[
            {
                'id': 'f1',
                'criteria': {'from': 'newsletter@foo.com'},
                'action': {'addLabelIds': ['L1']},
            },
            {
                'id': 'f2',
                'criteria': {'subject': 'unsubscribe', 'hasAttachment': True},
                'action': {'addLabelIds': ['L1']},
            },
        ],
    )
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.find_label',
            return_value=LabelLookup(label, 1523, True),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.preview_label',
            return_value=preview,
        ) as preview_call,
        patch(
            'gmail_cleaner.commands._progress.gmail.iter_message_headers',
            return_value=iter(
                [
                    {
                        'Date': 'Mon, 13 Apr 2026 14:30:00 -0400',
                        'From': 'Alice <a@example.com>',
                        'Subject': 'Hi',
                    },
                ],
            ),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.delete_label_completely',
        ) as del_complete,
    ):
        result = runner.invoke(
            app,
            ['delete-label', '--dry-run', 'MySpace'],
        )
    assert result.exit_code == 0
    preview_call.assert_called_once_with(creds, label)
    del_complete.assert_not_called()
    assert 'DRY RUN' in result.stdout
    assert "Label 'MySpace': 1,523 messages" in result.stdout
    assert 'Filters that would be removed (2)' in result.stdout
    assert 'from:newsletter@foo.com' in result.stdout
    assert 'subject:unsubscribe AND has:attachment' in result.stdout
    assert '2026-04-13  Alice <a@example.com>  Hi' in result.stdout


def test_delete_label_dry_run_with_no_filters_omits_filters_section():
    creds = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    preview = LabelPreview(total=0, sample_ids=[], filters=[])
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.find_label',
            return_value=LabelLookup(label, 0, False),
        ),
        patch(
            'gmail_cleaner.commands.delete_label.cleanup.preview_label',
            return_value=preview,
        ),
    ):
        result = runner.invoke(app, ['delete-label', '--dry-run', 'X'])
    assert result.exit_code == 0
    assert "Label 'X': 0 messages" in result.stdout
    assert 'Filters that would be removed' not in result.stdout
