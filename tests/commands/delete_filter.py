from unittest.mock import MagicMock, patch

from testsweet import test
from typer.testing import CliRunner

from gmail_cleaner import filters
from gmail_cleaner.cli import app

runner = CliRunner()


@test
def delete_filter_not_logged_in_exits_with_error():
    with patch('gmail_cleaner.auth.load_token', return_value=None):
        result = runner.invoke(app, ['delete-filter', 'f1'])
    assert result.exit_code == 1
    assert 'Not logged in' in (result.stdout + (result.stderr or ''))


@test
def delete_filter_deletes_single_id():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_filter.filters.delete_filters',
            return_value=filters.DeleteResult(deleted=1, missing=[]),
        ) as mock_delete,
    ):
        result = runner.invoke(app, ['delete-filter', 'f1'])
    assert result.exit_code == 0
    mock_delete.assert_called_once_with(creds, ['f1'])
    assert 'deleted f1' in (result.stdout + (result.stderr or ''))


@test
def delete_filter_reports_missing_and_exits_zero():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_filter.filters.delete_filters',
            return_value=filters.DeleteResult(
                deleted=1,
                missing=['ghost'],
            ),
        ),
    ):
        result = runner.invoke(app, ['delete-filter', 'f1', 'ghost'])
    assert result.exit_code == 0
    combined = result.stdout + (result.stderr or '')
    assert 'deleted f1' in combined
    assert 'not found ghost' in combined


@test
def delete_filter_multiple_ids_passes_them_through():
    creds = MagicMock()
    with (
        patch('gmail_cleaner.auth.load_token', return_value=creds),
        patch(
            'gmail_cleaner.commands.delete_filter.filters.delete_filters',
            return_value=filters.DeleteResult(deleted=3, missing=[]),
        ) as mock_delete,
    ):
        result = runner.invoke(app, ['delete-filter', 'f1', 'f2', 'f3'])
    assert result.exit_code == 0
    mock_delete.assert_called_once_with(creds, ['f1', 'f2', 'f3'])
