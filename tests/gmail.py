from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError
from testsweet import catch_exceptions, test, test_params

from gmail_cleaner import gmail


@test
def build_service_calls_build():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    with patch(
        'gmail_cleaner.gmail.build', return_value=mock_service
    ) as mock_build:
        result = gmail.build_service(mock_creds)
    mock_build.assert_called_once_with('gmail', 'v1', credentials=mock_creds)
    assert result is mock_service


@test
def get_user_email_returns_email_address():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().getProfile().execute.return_value = {
        'emailAddress': 'user@example.com'
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        result = gmail.get_user_email(mock_creds)
    assert result == 'user@example.com'


@test
def list_user_labels_filters_to_user_type_and_sorts_by_name():
    mock_service = MagicMock()
    mock_service.users().labels().list().execute.return_value = {
        'labels': [
            {'id': 'Label_2', 'name': 'Zebra', 'type': 'user'},
            {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
            {'id': 'Label_1', 'name': 'Apple', 'type': 'user'},
        ],
    }
    result = gmail.list_user_labels(mock_service)
    assert [label['name'] for label in result] == ['Apple', 'Zebra']
    assert all(label['type'] == 'user' for label in result)


@test_params(
    [
        ({'messages': [{'id': 'm1'}]}, True),
        ({'messages': []}, False),
        ({}, False),
    ]
)
def label_has_recent_message(response, expected):
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = response
    result = gmail.label_has_recent_message(mock_service, 'Label_1', '2y')
    assert result is expected


@test
def label_has_recent_message_passes_label_id_and_age():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
    }
    gmail.label_has_recent_message(mock_service, 'Label_1', '30d')
    mock_service.users().messages().list.assert_called_with(
        userId='me',
        labelIds=['Label_1'],
        q='newer_than:30d',
        maxResults=1,
    )


@test
def find_old_labels_returns_old_labels_and_total():
    mock_creds = MagicMock()
    labels = [
        {'id': 'L1', 'name': 'Apple', 'type': 'user'},
        {'id': 'L2', 'name': 'Banana', 'type': 'user'},
        {'id': 'L3', 'name': 'Cherry', 'type': 'user'},
    ]
    has_recent = {'L1': False, 'L2': True, 'L3': False}
    with (
        patch('gmail_cleaner.gmail.build'),
        patch(
            'gmail_cleaner.gmail.list_user_labels',
            return_value=labels,
        ),
        patch(
            'gmail_cleaner.gmail.label_has_recent_message',
            side_effect=lambda _s, label_id, _a: has_recent[label_id],
        ),
    ):
        old, total = gmail.find_old_labels(mock_creds, '2y')
    assert [label['name'] for label in old] == ['Apple', 'Cherry']
    assert total == 3


@test
def search_messages_returns_ids_and_estimate():
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


@test
def search_messages_handles_empty_response():
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


@test
def search_messages_passes_query_and_max_results():
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


@test
def iter_message_headers_extracts_three_headers():
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
        results = list(gmail.iter_message_headers(mock_creds, ['m1']))
    assert results == [
        {
            'Date': 'Mon, 13 Apr 2026 14:30:00 -0400',
            'From': 'Alice <alice@example.com>',
            'Subject': 'Hi there',
        },
    ]


@test
def iter_message_headers_missing_headers_default_to_empty_string():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {'headers': []},
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        results = list(gmail.iter_message_headers(mock_creds, ['m1']))
    assert results == [{'Date': '', 'From': '', 'Subject': ''}]


@test
def iter_message_headers_uses_metadata_format():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {'headers': []},
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        list(gmail.iter_message_headers(mock_creds, ['m1']))
    mock_service.users().messages().get.assert_called_with(
        userId='me',
        id='m1',
        format='metadata',
        metadataHeaders=['Date', 'From', 'Subject'],
    )


@test
def iter_message_headers_builds_service_once():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {'headers': []},
    }
    with patch(
        'gmail_cleaner.gmail.build',
        return_value=mock_service,
    ) as mock_build:
        list(gmail.iter_message_headers(mock_creds, ['m1', 'm2', 'm3']))
    assert mock_build.call_count == 1


@test
def with_retry_returns_value_on_first_success():
    result = gmail.with_retry(lambda: 'ok')
    assert result == 'ok'


@test
def with_retry_retries_on_5xx():
    with patch('gmail_cleaner.gmail.time.sleep', lambda _s: None):
        func = MagicMock(
            side_effect=[
                HttpError(MagicMock(status=503), b''),
                'ok',
            ],
        )
        assert gmail.with_retry(func) == 'ok'
    assert func.call_count == 2


@test
def with_retry_retries_on_429():
    with patch('gmail_cleaner.gmail.time.sleep', lambda _s: None):
        func = MagicMock(
            side_effect=[
                HttpError(MagicMock(status=429), b''),
                'ok',
            ],
        )
        assert gmail.with_retry(func) == 'ok'


@test
def with_retry_does_not_retry_on_403():
    err = HttpError(MagicMock(status=403), b'')
    func = MagicMock(side_effect=err)
    with catch_exceptions() as excs:
        gmail.with_retry(func)
    assert type(excs[0]) is HttpError
    assert func.call_count == 1


@test
def with_retry_does_not_retry_on_value_error():
    func = MagicMock(side_effect=ValueError('bug'))
    with catch_exceptions() as excs:
        gmail.with_retry(func)
    assert type(excs[0]) is ValueError
    assert func.call_count == 1


@test
def with_retry_raises_after_all_attempts_fail():
    with patch('gmail_cleaner.gmail.time.sleep', lambda _s: None):
        err = HttpError(MagicMock(status=500), b'')
        func = MagicMock(side_effect=err)
        with catch_exceptions() as excs:
            gmail.with_retry(func)
    assert type(excs[0]) is HttpError
    assert func.call_count == 3


def _http_error_with_retry_after(value: str) -> HttpError:
    resp = MagicMock(status=429)
    resp.headers = {'retry-after': value}
    return HttpError(resp, b'')


@test
def retry_after_seconds_parses_integer():
    exc = _http_error_with_retry_after('30')
    assert gmail._retry_after_seconds(exc) == 30.0


@test
def retry_after_seconds_parses_http_date():
    from datetime import datetime, timedelta, timezone

    target = datetime.now(timezone.utc) + timedelta(seconds=45)
    header = target.strftime('%a, %d %b %Y %H:%M:%S GMT')
    result = gmail._retry_after_seconds(_http_error_with_retry_after(header))
    assert result is not None
    assert 30.0 < result < 60.0


@test
def retry_after_seconds_returns_none_when_missing():
    resp = MagicMock(status=429)
    resp.headers = {}
    assert gmail._retry_after_seconds(HttpError(resp, b'')) is None


@test
def retry_after_seconds_returns_none_for_non_http_error():
    assert gmail._retry_after_seconds(OSError('boom')) is None


@test
def retry_after_seconds_returns_none_for_garbage():
    assert (
        gmail._retry_after_seconds(_http_error_with_retry_after('??')) is None
    )


@test
def with_retry_honors_retry_after_header():
    sleeps: list[float] = []
    with patch(
        'gmail_cleaner.gmail.time.sleep',
        lambda seconds: sleeps.append(seconds),
    ):
        err = _http_error_with_retry_after('7')
        func = MagicMock(side_effect=[err, 'ok'])
        assert gmail.with_retry(func) == 'ok'
    assert sleeps == [7.0]


@test
def with_retry_falls_back_to_default_delay():
    sleeps: list[float] = []
    with patch(
        'gmail_cleaner.gmail.time.sleep',
        lambda seconds: sleeps.append(seconds),
    ):
        err = HttpError(MagicMock(status=500, headers={}), b'')
        func = MagicMock(side_effect=[err, 'ok'])
        assert gmail.with_retry(func) == 'ok'
    assert sleeps == [gmail._RETRY_DELAYS[0]]


@test
def batch_modify_sends_ids_and_label_changes():
    mock_service = MagicMock()
    gmail.batch_modify(
        mock_service,
        ['m1', 'm2'],
        add_label_ids=['L1'],
        remove_label_ids=['INBOX'],
    )
    mock_service.users().messages().batchModify.assert_called_with(
        userId='me',
        body={
            'ids': ['m1', 'm2'],
            'addLabelIds': ['L1'],
            'removeLabelIds': ['INBOX'],
        },
    )


@test
def batch_modify_omits_empty_label_fields():
    mock_service = MagicMock()
    gmail.batch_modify(mock_service, ['m1'], remove_label_ids=['INBOX'])
    body = mock_service.users().messages().batchModify.call_args.kwargs['body']
    assert body == {'ids': ['m1'], 'removeLabelIds': ['INBOX']}


@test
def list_filters_returns_filter_list():
    mock_service = MagicMock()
    filters = [
        {'id': 'f1', 'action': {'addLabelIds': ['L1']}},
        {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
    ]
    mock_service.users().settings().filters().list().execute.return_value = {
        'filter': filters,
    }
    assert gmail.list_filters(mock_service) == filters


@test
def list_filters_empty_response():
    mock_service = MagicMock()
    mock_service.users().settings().filters().list().execute.return_value = {}
    assert gmail.list_filters(mock_service) == []


@test
def delete_filter_calls_api():
    mock_service = MagicMock()
    gmail.delete_filter(mock_service, 'f1')
    mock_service.users().settings().filters().delete.assert_called_with(
        userId='me',
        id='f1',
    )


@test
def delete_filter_retries_on_5xx():
    with patch('gmail_cleaner.gmail.time.sleep', lambda _s: None):
        mock_service = MagicMock()
        err = HttpError(MagicMock(status=500), b'')
        mock_service.users().settings().filters().delete().execute.side_effect = [
            err,
            None,
        ]
        gmail.delete_filter(mock_service, 'f1')
    assert (
        mock_service.users().settings().filters().delete().execute.call_count
        == 2
    )


@test
def create_filter_calls_api_and_returns_created():
    mock_service = MagicMock()
    created = {'id': 'f9', 'criteria': {'from': 'x@y'}, 'action': {}}
    mock_service.users().settings().filters().create().execute.return_value = (
        created
    )
    body = {'criteria': {'from': 'x@y'}, 'action': {}}
    assert gmail.create_filter(mock_service, body) == created
    mock_service.users().settings().filters().create.assert_called_with(
        userId='me',
        body=body,
    )


@test
def create_label_calls_api_and_returns_created():
    mock_service = MagicMock()
    created = {'id': 'L9', 'name': 'MyLabel'}
    mock_service.users().labels().create().execute.return_value = created
    body = {'name': 'MyLabel'}
    assert gmail.create_label(mock_service, body) == created
    mock_service.users().labels().create.assert_called_with(
        userId='me',
        body=body,
    )


@test
def create_label_does_not_retry_on_5xx():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=503), b'')
    mock_service.users().labels().create().execute.side_effect = err
    with catch_exceptions() as excs:
        gmail.create_label(mock_service, {'name': 'X'})
    assert type(excs[0]) is HttpError
    assert mock_service.users().labels().create().execute.call_count == 1


@test
def create_filter_does_not_retry_on_5xx():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=503), b'')
    mock_service.users().settings().filters().create().execute.side_effect = (
        err
    )
    with catch_exceptions() as excs:
        gmail.create_filter(mock_service, {'criteria': {}, 'action': {}})
    assert type(excs[0]) is HttpError
    assert (
        mock_service.users().settings().filters().create().execute.call_count
        == 1
    )


@test
def get_filter_calls_api_and_returns_filter():
    mock_service = MagicMock()
    filt = {'id': 'f9', 'criteria': {}, 'action': {}}
    mock_service.users().settings().filters().get().execute.return_value = filt
    assert gmail.get_filter(mock_service, 'f9') == filt
    mock_service.users().settings().filters().get.assert_called_with(
        userId='me',
        id='f9',
    )


@test
def iter_message_ids_single_page():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
    }
    mock_service.users().messages().list_next.return_value = None
    assert list(gmail.iter_message_ids(mock_service, query='in:inbox')) == [
        'm1',
        'm2',
    ]


@test
def iter_message_ids_paginates():
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

    assert list(gmail.iter_message_ids(mock_service, query='in:inbox')) == [
        'm1',
        'm2',
    ]


@test
def iter_message_ids_empty():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    mock_service.users().messages().list_next.return_value = None
    assert list(gmail.iter_message_ids(mock_service, query='in:inbox')) == []


@test
def iter_message_ids_is_lazy():
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

    iterator = gmail.iter_message_ids(mock_service, query='in:inbox')
    # Drain only first page.
    assert next(iterator) == 'm1'
    # Second page must not have been fetched yet.
    assert second_request.execute.call_count == 0
    # Now drain the rest.
    assert list(iterator) == ['m2']
    assert second_request.execute.call_count == 1


@test_params(
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
    ]
)
def list_messages_kwargs_omits_none_values(kwargs, expected):
    assert gmail.list_messages_kwargs(**kwargs) == expected
