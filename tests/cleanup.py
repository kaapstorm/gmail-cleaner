from unittest.mock import MagicMock, patch

from googleapiclient.errors import HttpError
from testsweet import catch_exceptions, test

from gmail_cleaner import cleanup


@test
def delete_message_batches_groups_by_1000():
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


@test
def delete_message_batches_empty_is_noop():
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


@test
def delete_message_batches_consumes_generator():
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


@test
def delete_message_batches_retries_failed_batch():
    with patch('gmail_cleaner.gmail.time.sleep', lambda _s: None):
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


@test
def delete_message_batches_propagates_after_retries():
    with patch('gmail_cleaner.gmail.time.sleep', lambda _s: None):
        mock_service = MagicMock()
        err = HttpError(MagicMock(status=500), b'')
        mock_service.users().messages().batchDelete().execute.side_effect = err
        with catch_exceptions() as excs:
            cleanup._delete_message_batches(
                mock_service,
                (f'm{i}' for i in range(600)),  # forces 2 batches
                on_progress=lambda _d: None,
            )
    assert type(excs[0]) is HttpError


@test
def scan_for_messages_returns_estimate_and_has_results():
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


@test
def scan_for_messages_empty_first_page_no_token():
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


@test
def scan_for_messages_empty_first_page_with_token():
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


@test
def scan_for_messages_messages_present_estimate_zero():
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


@test
def delete_messages_matching_paginates_and_deletes():
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


@test
def delete_messages_matching_empty():
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


@test
def modify_message_batches_groups_by_1000():
    mock_service = MagicMock()
    ids = [f'm{i}' for i in range(1500)]
    progress: list[int] = []
    total = cleanup._modify_message_batches(
        mock_service,
        ids,
        remove_label_ids=['INBOX'],
        on_progress=progress.append,
    )
    batch_modify = mock_service.users().messages().batchModify
    assert batch_modify.call_count == 2
    body_1 = batch_modify.call_args_list[0].kwargs['body']
    body_2 = batch_modify.call_args_list[1].kwargs['body']
    assert len(body_1['ids']) == 1000
    assert body_1['removeLabelIds'] == ['INBOX']
    assert 'addLabelIds' not in body_1
    assert len(body_2['ids']) == 500
    assert progress == [1000, 1500]
    assert total == 1500


@test
def modify_message_batches_empty_is_noop():
    mock_service = MagicMock()
    total = cleanup._modify_message_batches(
        mock_service,
        iter([]),
        add_label_ids=['L1'],
        on_progress=lambda _d: None,
    )
    mock_service.users().messages().batchModify.assert_not_called()
    assert total == 0


@test
def archive_messages_matching_removes_inbox_label():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
    }
    mock_service.users().messages().list_next.return_value = None
    with patch(
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        archived = cleanup.archive_messages_matching(
            creds,
            'in:inbox',
            on_progress=lambda _d: None,
        )
    assert archived == 2
    body = mock_service.users().messages().batchModify.call_args.kwargs['body']
    assert body['removeLabelIds'] == ['INBOX']
    assert body['ids'] == ['m1', 'm2']


@test
def label_messages_matching_adds_label():
    creds = MagicMock()
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        'messages': [{'id': 'm1'}, {'id': 'm2'}],
    }
    mock_service.users().messages().list_next.return_value = None
    with patch(
        'gmail_cleaner.gmail.build_service',
        return_value=mock_service,
    ):
        labeled = cleanup.label_messages_matching(
            creds,
            'subject:[Solutions]',
            'Label_134',
            on_progress=lambda _d: None,
        )
    assert labeled == 2
    body = mock_service.users().messages().batchModify.call_args.kwargs['body']
    assert body['addLabelIds'] == ['Label_134']
    assert 'removeLabelIds' not in body


@test
def delete_label_by_id_calls_api():
    mock_service = MagicMock()
    cleanup._delete_label_by_id(mock_service, 'Label_1')
    mock_service.users().labels().delete.assert_called_with(
        userId='me',
        id='Label_1',
    )


@test
def delete_label_by_id_retries_on_5xx():
    with patch('gmail_cleaner.gmail.time.sleep', lambda _s: None):
        mock_service = MagicMock()
        err = HttpError(MagicMock(status=500), b'')
        mock_service.users().labels().delete().execute.side_effect = [
            err,
            None,
        ]
        cleanup._delete_label_by_id(mock_service, 'Label_1')
    assert mock_service.users().labels().delete().execute.call_count == 2


@test
def find_label_returns_none_when_not_found():
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


@test
def find_label_returns_label_estimate_and_has_messages():
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


@test
def delete_label_completely_deletes_messages_filters_and_label():
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


@test
def delete_label_completely_handles_filters_without_action():
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


@test
def delete_label_completely_zero_matching_filters():
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


@test
def delete_label_completely_zero_messages_still_cleans_up():
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
