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
    result = gmail.list_user_labels(mock_service)
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
    result = gmail.label_has_recent_message(mock_service, 'Label_1', '2y')
    assert result is expected


def test_label_has_recent_message_passes_label_id_and_age():
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


def test_find_old_labels_returns_old_labels_and_total():
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


def test_iter_message_headers_extracts_three_headers():
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


def test_iter_message_headers_missing_headers_default_to_empty_string():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = {
        'payload': {'headers': []},
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        results = list(gmail.iter_message_headers(mock_creds, ['m1']))
    assert results == [{'Date': '', 'From': '', 'Subject': ''}]


def test_iter_message_headers_uses_metadata_format():
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


def test_iter_message_headers_builds_service_once():
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


def test_with_retry_returns_value_on_first_success():
    result = gmail.with_retry(lambda: 'ok')
    assert result == 'ok'


@use(no_sleep)
def test_with_retry_retries_on_5xx():
    func = MagicMock(
        side_effect=[
            HttpError(MagicMock(status=503), b''),
            'ok',
        ],
    )
    assert gmail.with_retry(func) == 'ok'
    assert func.call_count == 2


@use(no_sleep)
def test_with_retry_retries_on_429():
    func = MagicMock(
        side_effect=[
            HttpError(MagicMock(status=429), b''),
            'ok',
        ],
    )
    assert gmail.with_retry(func) == 'ok'


def test_with_retry_does_not_retry_on_403():
    err = HttpError(MagicMock(status=403), b'')
    func = MagicMock(side_effect=err)
    with pytest.raises(HttpError):
        gmail.with_retry(func)
    assert func.call_count == 1


def test_with_retry_does_not_retry_on_value_error():
    func = MagicMock(side_effect=ValueError('bug'))
    with pytest.raises(ValueError):
        gmail.with_retry(func)
    assert func.call_count == 1


@use(no_sleep)
def test_with_retry_raises_after_all_attempts_fail():
    err = HttpError(MagicMock(status=500), b'')
    func = MagicMock(side_effect=err)
    with pytest.raises(HttpError):
        gmail.with_retry(func)
    assert func.call_count == 3


def _http_error_with_retry_after(value: str) -> HttpError:
    resp = MagicMock(status=429)
    resp.headers = {'retry-after': value}
    return HttpError(resp, b'')


def test_retry_after_seconds_parses_integer():
    exc = _http_error_with_retry_after('30')
    assert gmail._retry_after_seconds(exc) == 30.0


def test_retry_after_seconds_parses_http_date():
    from datetime import datetime, timedelta, timezone

    target = datetime.now(timezone.utc) + timedelta(seconds=45)
    header = target.strftime('%a, %d %b %Y %H:%M:%S GMT')
    result = gmail._retry_after_seconds(_http_error_with_retry_after(header))
    assert result is not None
    assert 30.0 < result < 60.0


def test_retry_after_seconds_returns_none_when_missing():
    resp = MagicMock(status=429)
    resp.headers = {}
    assert gmail._retry_after_seconds(HttpError(resp, b'')) is None


def test_retry_after_seconds_returns_none_for_non_http_error():
    assert gmail._retry_after_seconds(OSError('boom')) is None


def test_retry_after_seconds_returns_none_for_garbage():
    assert (
        gmail._retry_after_seconds(_http_error_with_retry_after('??')) is None
    )


def test_with_retry_honors_retry_after_header(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(
        'gmail_cleaner.gmail.time.sleep',
        lambda seconds: sleeps.append(seconds),
    )
    err = _http_error_with_retry_after('7')
    func = MagicMock(side_effect=[err, 'ok'])
    assert gmail.with_retry(func) == 'ok'
    assert sleeps == [7.0]


def test_with_retry_falls_back_to_default_delay(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(
        'gmail_cleaner.gmail.time.sleep',
        lambda seconds: sleeps.append(seconds),
    )
    err = HttpError(MagicMock(status=500, headers={}), b'')
    func = MagicMock(side_effect=[err, 'ok'])
    assert gmail.with_retry(func) == 'ok'
    assert sleeps == [gmail._RETRY_DELAYS[0]]


def test_list_filters_returns_filter_list():
    mock_service = MagicMock()
    filters = [
        {'id': 'f1', 'action': {'addLabelIds': ['L1']}},
        {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
    ]
    mock_service.users().settings().filters().list().execute.return_value = {
        'filter': filters,
    }
    assert gmail.list_filters(mock_service) == filters


def test_list_filters_empty_response():
    mock_service = MagicMock()
    mock_service.users().settings().filters().list().execute.return_value = {}
    assert gmail.list_filters(mock_service) == []


def test_delete_filter_calls_api():
    mock_service = MagicMock()
    gmail.delete_filter(mock_service, 'f1')
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
    gmail.delete_filter(mock_service, 'f1')
    assert (
        mock_service.users().settings().filters().delete().execute.call_count
        == 2
    )


def test_create_filter_calls_api_and_returns_created():
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


def test_create_label_calls_api_and_returns_created():
    mock_service = MagicMock()
    created = {'id': 'L9', 'name': 'MyLabel'}
    mock_service.users().labels().create().execute.return_value = created
    body = {'name': 'MyLabel'}
    assert gmail.create_label(mock_service, body) == created
    mock_service.users().labels().create.assert_called_with(
        userId='me',
        body=body,
    )


def test_create_label_does_not_retry_on_5xx():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=503), b'')
    mock_service.users().labels().create().execute.side_effect = err
    with pytest.raises(HttpError):
        gmail.create_label(mock_service, {'name': 'X'})
    assert mock_service.users().labels().create().execute.call_count == 1


def test_create_filter_does_not_retry_on_5xx():
    mock_service = MagicMock()
    err = HttpError(MagicMock(status=503), b'')
    mock_service.users().settings().filters().create().execute.side_effect = (
        err
    )
    with pytest.raises(HttpError):
        gmail.create_filter(mock_service, {'criteria': {}, 'action': {}})
    assert (
        mock_service.users().settings().filters().create().execute.call_count
        == 1
    )


def test_get_filter_calls_api_and_returns_filter():
    mock_service = MagicMock()
    filt = {'id': 'f9', 'criteria': {}, 'action': {}}
    mock_service.users().settings().filters().get().execute.return_value = filt
    assert gmail.get_filter(mock_service, 'f9') == filt
    mock_service.users().settings().filters().get.assert_called_with(
        userId='me',
        id='f9',
    )
