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
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().labels().list().execute.return_value = {
        'labels': [
            {'id': 'Label_2', 'name': 'Zebra', 'type': 'user'},
            {'id': 'INBOX', 'name': 'INBOX', 'type': 'system'},
            {'id': 'Label_1', 'name': 'Apple', 'type': 'user'},
        ],
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        result = gmail.list_user_labels(mock_creds)
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
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = response
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        result = gmail.label_has_recent_message(
            mock_creds,
            'Label_1',
            '2y',
        )
    assert result is expected


def test_label_has_recent_message_passes_label_id_and_age():
    mock_creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}],
    }
    with patch('gmail_cleaner.gmail.build', return_value=mock_service):
        gmail.label_has_recent_message(mock_creds, 'Label_1', '30d')
    mock_service.users().messages().list.assert_called_with(
        userId='me',
        labelIds=['Label_1'],
        q='newer_than:30d',
        maxResults=1,
    )


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
