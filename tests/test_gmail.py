from unittest.mock import MagicMock, patch

import pytest

from gmail_cleaner import gmail


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
        patch('gmail_cleaner.gmail.build'),
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
