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


def test_delete_message_batches_groups_by_1000():
    mock_service = MagicMock()
    ids = [f'm{i}' for i in range(1500)]
    progress: list[int] = []
    total = cleanup._delete_message_batches(
        mock_service,
        ids,
        on_progress=progress.append,
    )
    batch_delete = mock_service.users().messages().batchDelete
    assert batch_delete.call_count == 2
    assert len(batch_delete.call_args_list[0].kwargs['body']['ids']) == 1000
    assert len(batch_delete.call_args_list[1].kwargs['body']['ids']) == 500
    assert progress == [1000, 1500]
    assert total == 1500


def test_delete_message_batches_empty_is_noop():
    mock_service = MagicMock()
    progress: list[int] = []
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
        'gmail_cleaner.gmail.build_service',
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
        'gmail_cleaner.gmail.build_service',
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
        'gmail_cleaner.gmail.build_service',
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
        'gmail_cleaner.gmail.build_service',
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
    progress: list[int] = []
    with patch(
        'gmail_cleaner.gmail.build_service',
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
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        deleted = cleanup.delete_messages_matching(
            creds,
            'in:inbox',
            on_progress=lambda _d: None,
        )
    assert deleted == 0
    mock_service.users().messages().batchDelete.assert_not_called()


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


def test_find_label_returns_none_when_not_found():
    creds = MagicMock()
    mock_service = MagicMock()
    with (
        patch(
            'gmail_cleaner.gmail.build_service',
            return_value=mock_service,
        ),
        patch(
            'gmail_cleaner.gmail.list_user_labels',
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
            'gmail_cleaner.gmail.build_service',
            return_value=mock_service,
        ),
        patch(
            'gmail_cleaner.gmail.list_user_labels',
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
            'gmail_cleaner.gmail.build_service',
            return_value=mock_service,
        ),
        patch('gmail_cleaner.gmail.list_filters', return_value=filters),
        patch('gmail_cleaner.gmail.delete_filter') as del_filter,
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
            'gmail_cleaner.gmail.build_service',
            return_value=mock_service,
        ),
        patch('gmail_cleaner.gmail.list_filters', return_value=filters),
        patch('gmail_cleaner.gmail.delete_filter') as del_filter,
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
            'gmail_cleaner.gmail.build_service',
            return_value=mock_service,
        ),
        patch(
            'gmail_cleaner.gmail.list_filters',
            return_value=[
                {'id': 'f2', 'action': {'addLabelIds': ['L2']}},
            ],
        ),
        patch('gmail_cleaner.gmail.delete_filter') as del_filter,
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
            'gmail_cleaner.gmail.build_service',
            return_value=mock_service,
        ),
        patch('gmail_cleaner.gmail.list_filters', return_value=[]),
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
