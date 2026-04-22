from unittest.mock import MagicMock, patch

import pytest

from gmail_cleaner import export


@pytest.mark.parametrize(
    'raw, expected',
    [
        (None, None),
        ('', None),
        (
            'Mon, 13 Apr 2026 14:30:00 -0400',
            '2026-04-13T14:30:00-04:00',
        ),
        # Unparseable garbage: falls back to raw string.
        ('not a real date', 'not a real date'),
        # Parseable but invalid month: falls back to raw string.
        ('Mon, 99 Abc 2026 14:30:00 -0400', 'Mon, 99 Abc 2026 14:30:00 -0400'),
    ],
)
def test_parse_iso_date(raw, expected):
    assert export._parse_iso_date(raw) == expected


@pytest.mark.parametrize(
    'payload, expected',
    [
        # Bare text/plain — no attachments possible.
        ({'mimeType': 'text/plain'}, []),
        # Multipart with one attachment and one body part.
        (
            {
                'mimeType': 'multipart/mixed',
                'parts': [
                    {'mimeType': 'text/plain', 'filename': ''},
                    {
                        'mimeType': 'application/pdf',
                        'filename': 'menu.pdf',
                        'body': {'size': 48213},
                    },
                ],
            },
            [
                {
                    'filename': 'menu.pdf',
                    'mime_type': 'application/pdf',
                    'size': 48213,
                },
            ],
        ),
        # Nested multipart/alternative inside multipart/mixed.
        (
            {
                'mimeType': 'multipart/mixed',
                'parts': [
                    {
                        'mimeType': 'multipart/alternative',
                        'filename': '',
                        'parts': [
                            {'mimeType': 'text/plain', 'filename': ''},
                            {'mimeType': 'text/html', 'filename': ''},
                        ],
                    },
                    {
                        'mimeType': 'image/png',
                        'filename': 'pic.png',
                        'body': {'size': 101},
                    },
                ],
            },
            [
                {
                    'filename': 'pic.png',
                    'mime_type': 'image/png',
                    'size': 101,
                },
            ],
        ),
        # Parts present but none have a filename — empty list.
        (
            {
                'mimeType': 'multipart/alternative',
                'parts': [
                    {'mimeType': 'text/plain', 'filename': ''},
                    {'mimeType': 'text/html', 'filename': ''},
                ],
            },
            [],
        ),
    ],
)
def test_extract_attachments(payload, expected):
    assert export._extract_attachments(payload) == expected


def test_extract_attachments_indeterminate_returns_none():
    payload = {'mimeType': 'multipart/mixed'}
    assert export._extract_attachments(payload) is None


def _make_message(
    headers=None, *, labels=None, snippet='...', payload_extra=None
):
    payload = {'headers': headers or [], 'mimeType': 'text/plain'}
    if payload_extra:
        payload.update(payload_extra)
    return {
        'id': 'mid',
        'threadId': 'tid',
        'labelIds': labels or [],
        'snippet': snippet,
        'payload': payload,
    }


def test_fetch_message_export_full_record():
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = _make_message(
        headers=[
            {'name': 'Date', 'value': 'Mon, 13 Apr 2026 14:30:00 -0400'},
            {'name': 'From', 'value': 'Alice <alice@example.com>'},
            {'name': 'To', 'value': 'me@example.com, other@example.com'},
            {'name': 'Cc', 'value': 'cc@example.com'},
            {'name': 'Subject', 'value': 'Re: lunch'},
            {'name': 'List-Id', 'value': '<news.example.com>'},
            {'name': 'List-Unsubscribe', 'value': '<mailto:u@example.com>'},
        ],
        labels=['INBOX', 'IMPORTANT'],
        snippet='Sounds good',
        payload_extra={
            'mimeType': 'multipart/mixed',
            'parts': [
                {'mimeType': 'text/plain', 'filename': ''},
                {
                    'mimeType': 'application/pdf',
                    'filename': 'menu.pdf',
                    'body': {'size': 48213},
                },
            ],
        },
    )
    result = export.fetch_message_export(mock_service, 'mid')
    assert result == {
        'id': 'mid',
        'thread_id': 'tid',
        'date': '2026-04-13T14:30:00-04:00',
        'from': 'Alice <alice@example.com>',
        'to': ['me@example.com', 'other@example.com'],
        'cc': ['cc@example.com'],
        'subject': 'Re: lunch',
        'list_id': '<news.example.com>',
        'list_unsubscribe': '<mailto:u@example.com>',
        'labels': ['INBOX', 'IMPORTANT'],
        'snippet': 'Sounds good',
        'attachments': [
            {
                'filename': 'menu.pdf',
                'mime_type': 'application/pdf',
                'size': 48213,
            },
        ],
    }


def test_fetch_message_export_missing_headers_use_sensible_defaults():
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = _make_message(
        headers=[],
        labels=['INBOX'],
        snippet='hi',
    )
    result = export.fetch_message_export(mock_service, 'mid')
    assert result['date'] is None
    assert result['from'] is None
    assert result['to'] == []
    assert result['cc'] == []
    assert result['subject'] is None
    assert result['list_id'] is None
    assert result['list_unsubscribe'] is None
    assert result['attachments'] == []


def test_fetch_message_export_indeterminate_attachments_uses_has_attachments():
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = _make_message(
        payload_extra={'mimeType': 'multipart/mixed'},
    )
    result = export.fetch_message_export(mock_service, 'mid')
    assert 'attachments' not in result
    assert result['has_attachments'] is True


def test_fetch_message_export_uses_metadata_format_and_header_allowlist():
    mock_service = MagicMock()
    mock_service.users().messages().get().execute.return_value = (
        _make_message()
    )
    export.fetch_message_export(mock_service, 'mid')
    mock_service.users().messages().get.assert_called_with(
        userId='me',
        id='mid',
        format='metadata',
        metadataHeaders=[
            'Date',
            'From',
            'To',
            'Cc',
            'Subject',
            'List-Id',
            'List-Unsubscribe',
        ],
    )


def test_iter_inbox_ids_paginates_until_exhausted():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.side_effect = [
        {'messages': [{'id': 'a'}, {'id': 'b'}], 'nextPageToken': 'p2'},
        {'messages': [{'id': 'c'}]},
    ]
    assert list(export.iter_inbox_ids(mock_service)) == ['a', 'b', 'c']


def test_iter_inbox_ids_handles_empty_inbox():
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {}
    assert list(export.iter_inbox_ids(mock_service)) == []


def test_iter_inbox_ids_passes_query_and_page_token():
    mock_service = MagicMock()
    list_mock = mock_service.users().messages().list
    list_mock().execute.side_effect = [
        {'messages': [{'id': 'a'}], 'nextPageToken': 'tok'},
        {'messages': [{'id': 'b'}]},
    ]
    list(export.iter_inbox_ids(mock_service))
    calls = list_mock.call_args_list
    # Filter out the accessor calls (no kwargs) from our two paginated calls.
    paginated = [call for call in calls if call.kwargs]
    assert paginated[0].kwargs == {'userId': 'me', 'q': 'in:inbox'}
    assert paginated[1].kwargs == {
        'userId': 'me',
        'q': 'in:inbox',
        'pageToken': 'tok',
    }


def test_iter_inbox_records_yields_records_and_reports_errors():
    from googleapiclient.errors import HttpError

    mock_creds = MagicMock()
    mock_service = MagicMock()

    def _fetch(_svc, mid):
        if mid == 'b':
            raise HttpError(MagicMock(status=404), b'')
        return {'id': mid}

    errors: list[tuple[str, HttpError]] = []

    def _on_error(message_id, exc):
        errors.append((message_id, exc))

    with (
        patch(
            'gmail_cleaner.gmail.build_service',
            return_value=mock_service,
        ),
        patch(
            'gmail_cleaner.export.iter_inbox_ids',
            return_value=iter(['a', 'b', 'c']),
        ),
        patch(
            'gmail_cleaner.export.fetch_message_export',
            side_effect=_fetch,
        ),
    ):
        records = list(
            export.iter_inbox_records(mock_creds, on_error=_on_error),
        )
    assert [r['id'] for r in records] == ['a', 'c']
    assert [mid for mid, _exc in errors] == ['b']
