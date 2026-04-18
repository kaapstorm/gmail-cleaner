from collections.abc import Iterator
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from gmail_cleaner.gmail import (
    Service,
    _extract_headers,
    _with_retry,
    build_service,
)

OnError = Callable[[str, HttpError], None]


def _parse_iso_date(raw: str | None) -> str | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return raw
    if parsed is None:
        return raw
    return parsed.isoformat()


def _collect_attachment_parts(parts: list[dict], out: list[dict]) -> None:
    for part in parts:
        filename = part.get('filename') or ''
        if filename:
            body = part.get('body', {}) or {}
            out.append(
                {
                    'filename': filename,
                    'mime_type': part.get('mimeType', ''),
                    'size': body.get('size', 0),
                },
            )
        nested = part.get('parts')
        if nested:
            _collect_attachment_parts(nested, out)


def _extract_attachments(payload: dict) -> list[dict] | None:
    """Return attachment descriptors, or ``None`` if indeterminate.

    - When ``payload.parts`` is present, walks it recursively and
      returns a list of ``{filename, mime_type, size}`` dicts for
      parts that declare a non-empty ``filename``.
    - When ``parts`` is absent and ``mimeType`` is not ``multipart/*``,
      returns ``[]`` (single-part message, no attachments possible).
    - When ``parts`` is absent and ``mimeType`` is ``multipart/*``,
      the representation is indeterminate and the function returns
      ``None`` so the caller can decide how to proceed.
    """
    mime_type = payload.get('mimeType', '')
    parts = payload.get('parts')
    if parts is None:
        if mime_type.startswith('multipart/'):
            return None
        return []
    attachments: list[dict] = []
    _collect_attachment_parts(parts, attachments)
    return attachments


_EXPORT_HEADERS = (
    'Date',
    'From',
    'To',
    'Cc',
    'Subject',
    'List-Id',
    'List-Unsubscribe',
)


def _split_addresses(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [part.strip() for part in raw.split(',') if part.strip()]


def fetch_message_export(service: Service, message_id: str) -> dict:
    """Fetch a single message and return its export record."""
    response = _with_retry(
        service.users()
        .messages()
        .get(
            userId='me',
            id=message_id,
            format='metadata',
            metadataHeaders=list(_EXPORT_HEADERS),
        )
        .execute,
    )
    payload = response.get('payload', {}) or {}
    headers = _extract_headers(payload, _EXPORT_HEADERS)
    record = {
        'id': response.get('id', message_id),
        'thread_id': response.get('threadId'),
        'date': _parse_iso_date(headers.get('Date')),
        'from': headers.get('From') or None,
        'to': _split_addresses(headers.get('To')),
        'cc': _split_addresses(headers.get('Cc')),
        'subject': headers.get('Subject') or None,
        'list_id': headers.get('List-Id') or None,
        'list_unsubscribe': headers.get('List-Unsubscribe') or None,
        'labels': list(response.get('labelIds', [])),
        'snippet': response.get('snippet', ''),
    }
    attachments = _extract_attachments(payload)
    if attachments is None:
        record['has_attachments'] = True
    else:
        record['attachments'] = attachments
    return record


def iter_inbox_ids(service: Service) -> Iterator[str]:
    """Yield the ID of every message currently in INBOX."""
    page_token: str | None = None
    while True:
        kwargs: dict[str, Any] = {'userId': 'me', 'q': 'in:inbox'}
        if page_token:
            kwargs['pageToken'] = page_token
        response = _with_retry(
            service.users().messages().list(**kwargs).execute,
        )
        for message in response.get('messages', []) or []:
            yield message['id']
        page_token = response.get('nextPageToken')
        if not page_token:
            return


def iter_inbox_records(
    creds: Credentials,
    *,
    on_error: OnError,
) -> Iterator[dict]:
    """Yield an export record for every message currently in INBOX.

    Builds one Gmail service and threads it through the id paginator
    and the per-message fetch. Messages that raise ``HttpError`` are
    reported via ``on_error(message_id, exc)`` and skipped; the
    iteration continues.
    """
    service = build_service(creds)
    for message_id in iter_inbox_ids(service):
        try:
            yield fetch_message_export(service, message_id)
        except HttpError as exc:
            on_error(message_id, exc)
