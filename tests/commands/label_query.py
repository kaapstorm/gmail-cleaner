from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from gmail_cleaner.cleanup import LabelLookup, Preview, ScanResult
from gmail_cleaner.cli import app

runner = CliRunner()

_LABEL = {'id': 'Label_134', 'name': 'Salesforce', 'type': 'user'}


def _lookup(estimate=3, has_messages=True):
    return LabelLookup(
        label=_LABEL, estimate=estimate, has_messages=has_messages
    )


def test_label_query_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(
            app,
            ['label-query', '--label', 'Salesforce', 'in:inbox'],
        )
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


def test_label_query_missing_label_exits_with_error():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.find_label',
            return_value=None,
        ),
    ):
        result = runner.invoke(
            app,
            ['label-query', '--label', 'Nope', 'in:inbox'],
        )
    assert result.exit_code == 1
    assert 'Label not found: Nope' in (result.stdout + (result.stderr or ''))


def test_label_query_no_matches_exits_cleanly():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.find_label',
            return_value=_lookup(),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.scan_for_messages',
            return_value=ScanResult(0, False),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.label_messages_matching',
        ) as label_match,
    ):
        result = runner.invoke(
            app,
            ['label-query', '--label', 'Salesforce', 'in:inbox'],
        )
    assert result.exit_code == 0
    assert 'No matching messages' in result.stdout
    label_match.assert_not_called()


def test_label_query_aborted_by_user():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.find_label',
            return_value=_lookup(),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.scan_for_messages',
            return_value=ScanResult(3, True),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.label_messages_matching',
        ) as label_match,
    ):
        result = runner.invoke(
            app,
            ['label-query', '--label', 'Salesforce', 'in:inbox'],
            input='n\n',
        )
    assert result.exit_code == 1
    label_match.assert_not_called()


def test_label_query_labels_messages():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.find_label',
            return_value=_lookup(),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.scan_for_messages',
            return_value=ScanResult(3, True),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.label_messages_matching',
            return_value=3,
        ) as label_match,
    ):
        result = runner.invoke(
            app,
            ['label-query', '--label', 'Salesforce', 'in:inbox'],
            input='y\n',
        )
    assert result.exit_code == 0
    # Confirms we pass the resolved label id through to the logic layer.
    _, _, label_id = label_match.call_args.args
    assert label_id == 'Label_134'
    assert 'Labeled 3 messages' in result.stderr


def test_label_query_dry_run_does_not_require_scan():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.find_label',
            return_value=_lookup(),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.preview_query',
            return_value=Preview(total=5, sample_ids=[]),
        ) as preview,
        patch(
            'gmail_cleaner.commands.label_query.cleanup.label_messages_matching',
        ) as label_match,
    ):
        result = runner.invoke(
            app,
            [
                'label-query',
                '--dry-run',
                '--label',
                'Salesforce',
                'in:inbox',
            ],
        )
    assert result.exit_code == 0
    preview.assert_called_once_with(creds, query='in:inbox')
    label_match.assert_not_called()
    assert '5 matches' in result.stdout


def test_label_query_force_skips_confirmation():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.find_label',
            return_value=_lookup(),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.scan_for_messages',
            return_value=ScanResult(1, True),
        ),
        patch(
            'gmail_cleaner.commands.label_query.cleanup.label_messages_matching',
            return_value=1,
        ) as label_match,
    ):
        result = runner.invoke(
            app,
            ['label-query', '--force', '--label', 'Salesforce', 'in:inbox'],
        )
    assert result.exit_code == 0
    label_match.assert_called_once()
