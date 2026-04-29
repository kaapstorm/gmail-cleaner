from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError
from testsweet import catch_exceptions, test

from gmail_cleaner import filters


@test
def list_filters_returns_all_filters():
    creds = MagicMock()
    service = MagicMock()
    all_filters = [{'id': 'f1'}, {'id': 'f2'}]
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch(
            'gmail_cleaner.gmail.list_filters',
            return_value=all_filters,
        ) as mock_list,
    ):
        assert filters.list_filters(creds) == all_filters
    mock_list.assert_called_once_with(service)


@test
def get_filter_returns_single_filter():
    creds = MagicMock()
    service = MagicMock()
    one = {'id': 'f1', 'criteria': {}, 'action': {}}
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch(
            'gmail_cleaner.gmail.get_filter',
            return_value=one,
        ) as mock_get,
    ):
        assert filters.get_filter(creds, 'f1') == one
    mock_get.assert_called_once_with(service, 'f1')


@test
def get_filter_missing_raises_filter_not_found():
    creds = MagicMock()
    service = MagicMock()
    err = HttpError(MagicMock(status=404), b'')
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch('gmail_cleaner.gmail.get_filter', side_effect=err),
        catch_exceptions() as excs,
    ):
        filters.get_filter(creds, 'missing')
    assert type(excs[0]) is filters.FilterNotFound
    assert 'missing' in str(excs[0])


@test
def get_filter_non_404_http_error_propagates():
    creds = MagicMock()
    service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch('gmail_cleaner.gmail.get_filter', side_effect=err),
        catch_exceptions() as excs,
    ):
        filters.get_filter(creds, 'f1')
    assert type(excs[0]) is HttpError


@test
def create_filters_creates_each_and_returns_created_list():
    creds = MagicMock()
    service = MagicMock()
    inputs = [
        {'criteria': {'from': 'a@x'}, 'action': {'addLabelIds': ['L1']}},
        {'criteria': {'from': 'b@x'}, 'action': {'addLabelIds': ['L2']}},
    ]
    outputs = [{'id': 'f1', **inputs[0]}, {'id': 'f2', **inputs[1]}]
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch(
            'gmail_cleaner.gmail.create_filter',
            side_effect=outputs,
        ) as mock_create,
    ):
        assert filters.create_filters(creds, inputs) == outputs
    assert mock_create.call_count == 2


@test
def create_filters_midbatch_failure_reports_partial():
    creds = MagicMock()
    service = MagicMock()
    good = {'id': 'f1', 'criteria': {'from': 'a@x'}, 'action': {}}
    err = HttpError(MagicMock(status=400), b'bad filter')
    inputs = [{'criteria': {'from': 'a@x'}, 'action': {}}, {'bogus': True}]
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch(
            'gmail_cleaner.gmail.create_filter',
            side_effect=[good, err],
        ),
        catch_exceptions() as excs,
    ):
        filters.create_filters(creds, inputs)
    assert type(excs[0]) is filters.CreateFiltersError
    assert excs[0].created == [good]
    assert excs[0].failed_index == 1
    assert '1' in str(excs[0])
    assert excs[0].__cause__ is err


@test
def create_filters_empty_input_returns_empty_list():
    creds = MagicMock()
    with patch(
        'gmail_cleaner.gmail.build_service',
        return_value=MagicMock(),
    ):
        assert filters.create_filters(creds, []) == []


@test
def delete_filters_deletes_all_given_ids():
    creds = MagicMock()
    service = MagicMock()
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch('gmail_cleaner.gmail.delete_filter') as mock_del,
    ):
        result = filters.delete_filters(creds, ['f1', 'f2'])
    assert result == filters.DeleteResult(deleted=2, missing=[])
    assert mock_del.call_count == 2


@test
def delete_filters_404_is_recorded_as_missing():
    creds = MagicMock()
    service = MagicMock()
    err = HttpError(MagicMock(status=404), b'')
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch(
            'gmail_cleaner.gmail.delete_filter',
            side_effect=[None, err, None],
        ),
    ):
        result = filters.delete_filters(creds, ['f1', 'missing', 'f3'])
    assert result == filters.DeleteResult(deleted=2, missing=['missing'])


@test
def delete_filters_non_404_http_error_propagates():
    creds = MagicMock()
    service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    with (
        patch('gmail_cleaner.gmail.build_service', return_value=service),
        patch('gmail_cleaner.gmail.delete_filter', side_effect=err),
        catch_exceptions() as excs,
    ):
        filters.delete_filters(creds, ['f1'])
    assert type(excs[0]) is HttpError
