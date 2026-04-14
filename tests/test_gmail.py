from unittest.mock import MagicMock, patch

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
