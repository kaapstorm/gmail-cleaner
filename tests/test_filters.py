from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from gmail_cleaner import filters


def test_list_filters_returns_all_filters():
    creds = MagicMock()
    service = MagicMock()
    all_filters = [{'id': 'f1'}, {'id': 'f2'}]
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._list_filters',
            return_value=all_filters,
        ) as mock_list,
    ):
        assert filters.list_filters(creds) == all_filters
    mock_list.assert_called_once_with(service)


def test_list_filters_by_id_returns_single_filter_in_list():
    creds = MagicMock()
    service = MagicMock()
    one = {'id': 'f1', 'criteria': {}, 'action': {}}
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._get_filter',
            return_value=one,
        ) as mock_get,
    ):
        assert filters.list_filters(creds, filter_id='f1') == [one]
    mock_get.assert_called_once_with(service, 'f1')


def test_list_filters_by_id_missing_raises_filter_not_found():
    creds = MagicMock()
    service = MagicMock()
    err = HttpError(MagicMock(status=404), b'')
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch('gmail_cleaner.filters._get_filter', side_effect=err),
        pytest.raises(filters.FilterNotFound) as exc_info,
    ):
        filters.list_filters(creds, filter_id='missing')
    assert 'missing' in str(exc_info.value)
