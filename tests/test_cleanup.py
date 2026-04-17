from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from unmagic import fixture, use

from gmail_cleaner import cleanup

monkeypatch = fixture('monkeypatch')


@fixture
def no_sleep():
    monkeypatch().setattr(
        'gmail_cleaner.gmail.time.sleep',
        lambda _s: None,
    )
    yield


def test_iter_message_ids_single_page():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
    }
    mock_service.users().messages().list_next.return_value = None
    assert list(cleanup._iter_message_ids(mock_service, query='in:inbox')) == [
        'm1',
        'm2',
    ]


def test_iter_message_ids_paginates():
    mock_service = MagicMock()
    page1 = {'messages': [{'id': 'm1'}], 'nextPageToken': 'tok'}
    page2 = {'messages': [{'id': 'm2'}]}

    first_request = MagicMock()
    first_request.execute.return_value = page1
    mock_service.users().messages().list.return_value = first_request

    second_request = MagicMock()
    second_request.execute.return_value = page2
    mock_service.users().messages().list_next.side_effect = [
        second_request,
        None,
    ]

    assert list(cleanup._iter_message_ids(mock_service, query='in:inbox')) == [
        'm1',
        'm2',
    ]


def test_iter_message_ids_empty():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    assert (
        list(cleanup._iter_message_ids(mock_service, query='in:inbox')) == []
    )


def test_iter_message_ids_is_lazy():
    mock_service = MagicMock()
    page1 = {'messages': [{'id': 'm1'}], 'nextPageToken': 'tok'}
    page2 = {'messages': [{'id': 'm2'}]}
    first_request = MagicMock()
    first_request.execute.return_value = page1
    mock_service.users().messages().list.return_value = first_request
    second_request = MagicMock()
    second_request.execute.return_value = page2
    mock_service.users().messages().list_next.side_effect = [
        second_request,
        None,
    ]

    iterator = cleanup._iter_message_ids(mock_service, query='in:inbox')
    # Drain only first page.
    assert next(iterator) == 'm1'
    # Second page must not have been fetched yet.
    assert second_request.execute.call_count == 0
    # Now drain the rest.
    assert list(iterator) == ['m2']
    assert second_request.execute.call_count == 1


def test_delete_message_batches_groups_by_500():
    mock_service = MagicMock()
    ids = [f'm{i}' for i in range(750)]
    progress = []
    total = cleanup._delete_message_batches(
        mock_service,
        ids,
        on_progress=progress.append,
    )
    batch_delete = mock_service.users().messages().batchDelete
    assert batch_delete.call_count == 2
    assert len(batch_delete.call_args_list[0].kwargs['body']['ids']) == 500
    assert len(batch_delete.call_args_list[1].kwargs['body']['ids']) == 250
    assert progress == [500, 750]
    assert total == 750


def test_delete_message_batches_empty_is_noop():
    mock_service = MagicMock()
    progress = []
    total = cleanup._delete_message_batches(
        mock_service,
        iter([]),
        on_progress=progress.append,
    )
    mock_service.users().messages().batchDelete.assert_not_called()
    assert progress == []
    assert total == 0


def test_delete_message_batches_consumes_generator():
    def gen():
        yield from (f'm{i}' for i in range(3))

    mock_service = MagicMock()
    total = cleanup._delete_message_batches(
        mock_service,
        gen(),
        on_progress=lambda _d: None,
    )
    assert total == 3
    assert mock_service.users().messages().batchDelete.call_count == 1


@use(no_sleep)
def test_delete_message_batches_retries_failed_batch():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    mock_service.users().messages().batchDelete().execute.side_effect = [
        err,
        None,
    ]
    total = cleanup._delete_message_batches(
        mock_service,
        ['m1'],
        on_progress=lambda _d: None,
    )
    assert total == 1
    assert (
        mock_service.users().messages().batchDelete().execute.call_count == 2
    )


@use(no_sleep)
def test_delete_message_batches_propagates_after_retries():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    mock_service.users().messages().batchDelete().execute.side_effect = err
    with pytest.raises(HttpError):
        cleanup._delete_message_batches(
            mock_service,
            (f'm{i}' for i in range(600)),  # forces 2 batches
            on_progress=lambda _d: None,
        )


def test_scan_for_messages_returns_estimate_and_has_results():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
        'resultSizeEstimate': 42,
        'nextPageToken': 'tok',
    }
    with patch(
        'gmail_cleaner.cleanup.build_service',
        return_value=mock_service,
    ):
        estimate, has_results = cleanup.scan_for_messages(creds, 'in:inbox')
    assert estimate == 42
    assert has_results is True


def test_scan_for_messages_empty_first_page_no_token():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 0,
    }
    with patch(
        'gmail_cleaner.cleanup.build_service',
        return_value=mock_service,
    ):
        estimate, has_results = cleanup.scan_for_messages(creds, 'in:inbox')
    assert estimate == 0
    assert has_results is False


def test_scan_for_messages_empty_first_page_with_token():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 5,
        'nextPageToken': 'tok',
    }
    with patch(
        'gmail_cleaner.cleanup.build_service',
        return_value=mock_service,
    ):
        estimate, has_results = cleanup.scan_for_messages(creds, 'in:inbox')
    assert estimate == 5
    assert has_results is True


def test_scan_for_messages_messages_present_estimate_zero():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
        'resultSizeEstimate': 0,
    }
    with patch(
        'gmail_cleaner.cleanup.build_service',
        return_value=mock_service,
    ):
        estimate, has_results = cleanup.scan_for_messages(creds, 'in:inbox')
    assert estimate == 0
    assert has_results is True


def test_delete_messages_matching_paginates_and_deletes():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': f'm{i}'} for i in range(3)],
    }
    mock_service.users().messages().list_next.return_value = None
    progress = []
    with patch(
        'gmail_cleaner.cleanup.build_service',
        return_value=mock_service,
    ):
        deleted = cleanup.delete_messages_matching(
            creds,
            'in:inbox',
            on_progress=progress.append,
        )
    assert deleted == 3
    assert progress == [3]
    mock_service.users().messages().batchDelete.assert_called_once()


def test_delete_messages_matching_empty():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    with patch(
        'gmail_cleaner.cleanup.build_service',
        return_value=mock_service,
    ):
        deleted = cleanup.delete_messages_matching(
            creds,
            'in:inbox',
            on_progress=lambda _d: None,
        )
    assert deleted == 0
    mock_service.users().messages().batchDelete.assert_not_called()


def test_list_filters_returns_filter_list():
    mock_service = MagicMock()
    filters = [
        {'id': 'f1', 'action': {'addLabelIds': ['L1']}},
        {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
    ]
    mock_service.users().settings().filters().list().execute.return_value = {
        'filter': filters,
    }
    assert cleanup._list_filters(mock_service) == filters


def test_list_filters_empty_response():
    mock_service = MagicMock()
    mock_service.users().settings().filters().list().execute.return_value = {}
    assert cleanup._list_filters(mock_service) == []


def test_delete_filter_calls_api():
    mock_service = MagicMock()
    cleanup._delete_filter(mock_service, 'f1')
    mock_service.users().settings().filters().delete.assert_called_with(
        userId='me',
        id='f1',
    )


@use(no_sleep)
def test_delete_filter_retries_on_5xx():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    mock_service.users().settings().filters().delete().execute.side_effect = [
        err,
        None,
    ]
    cleanup._delete_filter(mock_service, 'f1')
    assert (
        mock_service.users().settings().filters().delete().execute.call_count
        == 2
    )


def test_delete_label_by_id_calls_api():
    mock_service = MagicMock()
    cleanup._delete_label_by_id(mock_service, 'Label_1')
    mock_service.users().labels().delete.assert_called_with(
        userId='me',
        id='Label_1',
    )


@use(no_sleep)
def test_delete_label_by_id_retries_on_5xx():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    mock_service.users().labels().delete().execute.side_effect = [err, None]
    cleanup._delete_label_by_id(mock_service, 'Label_1')
    assert mock_service.users().labels().delete().execute.call_count == 2


@pytest.mark.parametrize(
    'kwargs, expected',
    [
        (
            {'query': 'in:inbox', 'label_ids': None},
            {'userId': 'me', 'maxResults': 500, 'q': 'in:inbox'},
        ),
        (
            {'query': None, 'label_ids': ['L1']},
            {'userId': 'me', 'maxResults': 500, 'labelIds': ['L1']},
        ),
        (
            {'query': None, 'label_ids': None},
            {'userId': 'me', 'maxResults': 500},
        ),
    ],
)
def test_list_messages_kwargs_omits_none_values(kwargs, expected):
    assert cleanup._list_messages_kwargs(**kwargs) == expected


def test_find_label_returns_none_when_not_found():
    creds = MagicMock()
    mock_service = MagicMock()
    with (
        patch(
            'gmail_cleaner.cleanup.build_service',
            return_value=mock_service,
        ),
        patch(
            'gmail_cleaner.cleanup._list_user_labels',
            return_value=[
                {'id': 'L1', 'name': 'Other', 'type': 'user'},
            ],
        ),
    ):
        assert cleanup.find_label(creds, 'MySpace') is None


def test_find_label_returns_label_estimate_and_has_messages():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
        'resultSizeEstimate': 7,
    }
    with (
        patch(
            'gmail_cleaner.cleanup.build_service',
            return_value=mock_service,
        ),
        patch(
            'gmail_cleaner.cleanup._list_user_labels',
            return_value=[label],
        ),
    ):
        result = cleanup.find_label(creds, 'MySpace')
    assert result is not None
    found_label, estimate, has_messages = result
    assert found_label == label
    assert estimate == 7
    assert has_messages is True
    mock_service.users().messages().list.assert_called_with(
        userId='me',
        maxResults=500,
        labelIds=['L1'],
    )


def test_delete_label_completely_deletes_messages_filters_and_label():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'MySpace', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
    }
    mock_service.users().messages().list_next.return_value = None
    filters = [
        {'id': 'f1', 'action': {'addLabelIds': ['L1']}},
        {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
        {'id': 'f3', 'action': {'addLabelIds': ['L1', 'L2']}},
    ]
    with (
        patch(
            'gmail_cleaner.cleanup.build_service',
            return_value=mock_service,
        ),
        patch('gmail_cleaner.cleanup._list_filters', return_value=filters),
        patch('gmail_cleaner.cleanup._delete_filter') as del_filter,
        patch('gmail_cleaner.cleanup._delete_label_by_id') as del_label,
    ):
        msgs, fs = cleanup.delete_label_completely(
            creds,
            label,
            on_progress=lambda _d: None,
        )
    assert msgs == 2
    assert fs == 2
    assert del_filter.call_count == 2
    del_label.assert_called_once_with(mock_service, 'L1')


def test_delete_label_completely_handles_filters_without_action():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    filters = [
        {'id': 'f1'},
        {'id': 'f2', 'action': {}},
        {'id': 'f3', 'action': {'addLabelIds': ['L1']}},
    ]
    with (
        patch(
            'gmail_cleaner.cleanup.build_service',
            return_value=mock_service,
        ),
        patch('gmail_cleaner.cleanup._list_filters', return_value=filters),
        patch('gmail_cleaner.cleanup._delete_filter') as del_filter,
        patch('gmail_cleaner.cleanup._delete_label_by_id'),
    ):
        msgs, fs = cleanup.delete_label_completely(
            creds,
            label,
            on_progress=lambda _d: None,
        )
    assert fs == 1
    del_filter.assert_called_once_with(mock_service, 'f3')


def test_delete_label_completely_zero_matching_filters():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    with (
        patch(
            'gmail_cleaner.cleanup.build_service',
            return_value=mock_service,
        ),
        patch(
            'gmail_cleaner.cleanup._list_filters',
            return_value=[
                {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
            ],
        ),
        patch('gmail_cleaner.cleanup._delete_filter') as del_filter,
        patch('gmail_cleaner.cleanup._delete_label_by_id'),
    ):
        _, fs = cleanup.delete_label_completely(
            creds,
            label,
            on_progress=lambda _d: None,
        )
    assert fs == 0
    del_filter.assert_not_called()


def test_delete_label_completely_zero_messages_still_cleans_up():
    creds = MagicMock()
    mock_service = MagicMock()
    label = {'id': 'L1', 'name': 'X', 'type': 'user'}
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    with (
        patch(
            'gmail_cleaner.cleanup.build_service',
            return_value=mock_service,
        ),
        patch('gmail_cleaner.cleanup._list_filters', return_value=[]),
        patch('gmail_cleaner.cleanup._delete_label_by_id') as del_label,
    ):
        msgs, fs = cleanup.delete_label_completely(
            creds,
            label,
            on_progress=lambda _d: None,
        )
    assert msgs == 0
    assert fs == 0
    del_label.assert_called_once_with(mock_service, 'L1')
