from unittest.mock import MagicMock, patch

import pytest
from googleapiclient.errors import HttpError
from unmagic import fixture, use

from gmail_cleaner import gmail

monkeypatch = fixture('monkeypatch')


@fixture
def no_sleep():
    monkeypatch().setattr('gmail_cleaner.gmail.time.sleep', lambda _s: None)
    yield


def test_build_service_calls_build():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    with patch(
        'gmail_cleaner.gmail.build', return_value=mock_service
    ) as mock_build:
        result = gmail.build_service(mock_creds)
    mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)
    assert result is mock_service


def test_get_user_email_returns_email_address():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        'emailAddress': 'user@example.com'
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        result = gmail.get_user_email(mock_creds)
    assert result == 'user@example.com'


def test_list_user_labels_filters_to_user_type_and_sorts_by_name():
    mock_service = MagicMock()
    mock_service.users().labels().list().execute.return_value = {
        'labels': [
            {'id': 'Label_2', 'name': 'Zebra', 'type': 'user'},
            {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
            {'id': 'Label_1', 'name': 'Apple', 'type': 'user'},
        ],
    }
    result = gmail._list_user_labels(mock_service)
    assert [label['name'] for label in result] == ['Apple', 'Zebra']
    assert all(label['type'] == 'user' for label in result)


@pytest.mark.parametrize(
    'response, expected',
    [
        ({'messages': [{'id': 'm1'}]}, True),
        ({'messages': []}, False),
        ({}, False),
    ],
)
def test_label_has_recent_message(response, expected):
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = response
    result = gmail._label_has_recent_message(mock_service, 'Label_1', '2y')
    assert result is expected


def test_label_has_recent_message_passes_label_id_and_age():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
    }
    gmail._label_has_recent_message(mock_service, 'Label_1', '30d')
    mock_service.users().messages().list.assert_called_with(
        userId='me',
        labelIds=['Label_1'],
        q='newer_than:30d',
        maxResults=1,
    )


def test_find_old_labels_returns_old_labels_and_total():
    mock_creds = MagicMock()
    labels = [
        {'id': 'L1', 'name': 'Apple', 'type': 'user'},
        {'id': 'L2', 'name': 'Banana', 'type': 'user'},
        {'id': 'L3', 'name': 'Cherry', 'type': 'user'},
    ]
    has_recent = {'L1': False, 'L2': True, 'L3': False}
    with (
        patch('gmail_cleaner.gmail.build') as mock_build,
        patch(
            'gmail_cleaner.gmail._list_user_labels',
            return_value=labels,
        ),
        patch(
            'gmail_cleaner.gmail._label_has_recent_message',
            side_effect=lambda _s, label_id, _a: has_recent[label_id],
        ),
    ):
        old, total = gmail.find_old_labels(mock_creds, '2y')
    assert [label['name'] for label in old] == ['Apple', 'Cherry']
    assert total == 3


def test_search_messages_returns_ids_and_estimate():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
        'resultSizeEstimate': 42,
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        ids, estimate = gmail.search_messages(
            mock_creds,
            'in:inbox',
            max_results=10,
        )
    assert ids == ['m1', 'm2']
    assert estimate == 42


def test_search_messages_handles_empty_response():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 0,
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        ids, estimate = gmail.search_messages(
            mock_creds,
            'in:inbox',
            max_results=10,
        )
    assert ids == []
    assert estimate == 0


def test_search_messages_passes_query_and_max_results():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 0,
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        gmail.search_messages(mock_creds, 'older_than:1y', max_results=100)
    mock_service.users().messages().list.assert_called_with(
        userId='me',
        q='older_than:1y',
        maxResults=100,
    )


def test_get_message_headers_extracts_three_headers():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {
            'headers': [
                {'name': 'Date', 'value': 'Mon, 13 Apr 2026 14:30:00 -0400'},
                {'name': 'From', 'value': 'Alice <alice@example.com>'},
                {'name': 'Subject', 'value': 'Hi there'},
                {'name': 'X-Other', 'value': 'irrelevant'},
            ],
        },
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        headers = gmail.get_message_headers(mock_creds, 'm1')
    assert headers == {
        'Date': 'Mon, 13 Apr 2026 14:30:00 -0400',
        'From': 'Alice <alice@example.com>',
        'Subject': 'Hi there',
    }


def test_get_message_headers_missing_headers_default_to_empty_string():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {'headers': []},
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        headers = gmail.get_message_headers(mock_creds, 'm1')
    assert headers == {'Date': '', 'From': '', 'Subject': ''}


def test_get_message_headers_uses_metadata_format():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {'headers': []},
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        gmail.get_message_headers(mock_creds, 'm1')
    mock_service.users().messages().get.assert_called_with(
        userId='me',
        id='m1',
        format='metadata',
        metadataHeaders=['Date', 'From', 'Subject'],
    )


def test_with_retry_returns_value_on_first_success():
    result = gmail._with_retry(lambda: 'ok')
    assert result == 'ok'


@use(no_sleep)
def test_with_retry_retries_on_5xx():
    fn = MagicMock(
        side_effect=[
            HttpError(MagicMock(status=503), b''),
            'ok',
        ],
    )
    assert gmail._with_retry(fn) == 'ok'
    assert fn.call_count == 2


@use(no_sleep)
def test_with_retry_retries_on_429():
    fn = MagicMock(
        side_effect=[
            HttpError(MagicMock(status=429), b''),
            'ok',
        ],
    )
    assert gmail._with_retry(fn) == 'ok'


def test_with_retry_does_not_retry_on_403():
    err = HttpError(MagicMock(status=403), b'')
    fn = MagicMock(side_effect=err)
    with pytest.raises(HttpError):
        gmail._with_retry(fn)
    assert fn.call_count == 1


def test_with_retry_does_not_retry_on_value_error():
    fn = MagicMock(side_effect=ValueError('bug'))
    with pytest.raises(ValueError):
        gmail._with_retry(fn)
    assert fn.call_count == 1


@use(no_sleep)
def test_with_retry_raises_after_all_attempts_fail():
    err = HttpError(MagicMock(status=500), b'')
    fn = MagicMock(side_effect=err)
    with pytest.raises(HttpError):
        gmail._with_retry(fn)
    assert fn.call_count == 3


def test_iter_message_ids_single_page():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
    }
    mock_service.users().messages().list_next.return_value = None
    assert list(gmail._iter_message_ids(mock_service, 'in:inbox')) == [
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

    assert list(gmail._iter_message_ids(mock_service, 'in:inbox')) == [
        'm1',
        'm2',
    ]


def test_iter_message_ids_empty():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    assert list(gmail._iter_message_ids(mock_service, 'in:inbox')) == []


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

    it = gmail._iter_message_ids(mock_service, 'in:inbox')
    # Drain only first page.
    assert next(it) == 'm1'
    # Second page must not have been fetched yet.
    assert second_request.execute.call_count == 0
    # Now drain the rest.
    assert list(it) == ['m2']
    assert second_request.execute.call_count == 1


def test_delete_message_batches_groups_by_500():
    mock_service = MagicMock()
    ids = [f'm{i}' for i in range(750)]
    progress = []
    total = gmail._delete_message_batches(
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
    total = gmail._delete_message_batches(
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
    total = gmail._delete_message_batches(
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
    total = gmail._delete_message_batches(
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
        gmail._delete_message_batches(
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
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        estimate, has_results = gmail.scan_for_messages(creds, 'in:inbox')
    assert estimate == 42
    assert has_results is True


def test_scan_for_messages_empty_first_page_no_token():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'resultSizeEstimate': 0,
    }
    with patch(
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        estimate, has_results = gmail.scan_for_messages(creds, 'in:inbox')
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
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        estimate, has_results = gmail.scan_for_messages(creds, 'in:inbox')
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
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        estimate, has_results = gmail.scan_for_messages(creds, 'in:inbox')
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
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        deleted = gmail.delete_messages_matching(
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
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        deleted = gmail.delete_messages_matching(
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
    assert gmail._list_filters(mock_service) == filters


def test_list_filters_empty_response():
    mock_service = MagicMock()
    mock_service.users().settings().filters().list().execute.return_value = {}
    assert gmail._list_filters(mock_service) == []


def test_delete_filter_calls_api():
    mock_service = MagicMock()
    gmail._delete_filter(mock_service, 'f1')
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
    gmail._delete_filter(mock_service, 'f1')
    assert (
        mock_service.users().settings().filters().delete().execute.call_count
        == 2
    )


def test_delete_label_by_id_calls_api():
    mock_service = MagicMock()
    gmail._delete_label_by_id(mock_service, 'Label_1')
    mock_service.users().labels().delete.assert_called_with(
        userId='me',
        id='Label_1',
    )


@use(no_sleep)
def test_delete_label_by_id_retries_on_5xx():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=500), b'')
    mock_service.users().labels().delete().execute.side_effect = [err, None]
    gmail._delete_label_by_id(mock_service, 'Label_1')
    assert mock_service.users().labels().delete().execute.call_count == 2
