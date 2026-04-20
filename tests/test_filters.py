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


def test_create_filters_creates_each_and_returns_created_list():
    creds = MagicMock()
    service = MagicMock()
    inputs = [
        {'criteria': {'from': 'a@x'}, 'action': {'addLabelIds': ['L1']}},
        {'criteria': {'from': 'b@x'}, 'action': {'addLabelIds': ['L2']}},
    ]
    outputs = [{'id': 'f1', **inputs[0]}, {'id': 'f2', **inputs[1]}]
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._create_filter',
            side_effect=outputs,
        ) as mock_create,
    ):
        assert filters.create_filters(creds, inputs) == outputs
    assert mock_create.call_count == 2


def test_create_filters_midbatch_failure_reports_partial():
    creds = MagicMock()
    service = MagicMock()
    good = {'id': 'f1', 'criteria': {'from': 'a@x'}, 'action': {}}
    err = HttpError(MagicMock(status=400), b'bad filter')
    inputs = [{'criteria': {'from': 'a@x'}, 'action': {}}, {'bogus': True}]
    with (
        patch('gmail_cleaner.filters.build_service', return_value=service),
        patch(
            'gmail_cleaner.filters._create_filter',
            side_effect=[good, err],
        ),
        pytest.raises(filters.CreateFiltersError) as exc_info,
    ):
        filters.create_filters(creds, inputs)
    assert exc_info.value.created == [good]
    assert exc_info.value.__cause__ is err


def test_create_filters_empty_input_returns_empty_list():
    creds = MagicMock()
    with patch(
        'gmail_cleaner.filters.build_service',
        return_value=MagicMock(),
    ):
        assert filters.create_filters(creds, []) == []
