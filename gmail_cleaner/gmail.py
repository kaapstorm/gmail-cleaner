import time
from collections.abc import Iterable, Iterator
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable, TypeAlias, TypeVar

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# The googleapiclient Resource is dynamically generated from the discovery
# document and ships without type stubs, so we can't annotate it precisely.
# The alias exists for documentary value: a parameter typed Service is a
# Gmail API handle, not an arbitrary object.
Service: TypeAlias = Any

_RETRY_DELAYS = (2.5, 5.0)

T = TypeVar('T')


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, TimeoutError)):
        return True
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, 'status', None)
        return status == 429 or (status is not None and status >= 500)
    return False


def _retry_after_seconds(exc: BaseException) -> float | None:
    """Return the Retry-After delay advertised by the server, if any.

    Accepts integer seconds (``Retry-After: 30``) or an HTTP-date
    (``Retry-After: Wed, 21 Oct 2026 07:28:00 GMT``). Returns None
    when the header is absent, malformed, or the exception isn't an
    HttpError.
    """
    if not isinstance(exc, HttpError):
        return None
    headers = getattr(exc.resp, 'headers', None)
    if not headers:
        return None
    raw = headers.get('retry-after') or headers.get('Retry-After')
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if target is None:
        return None
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())


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


def _with_retry(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            return fn(*args, **kwargs)
        except (OSError, TimeoutError, HttpError) as exc:
            if not _is_retryable(exc) or attempt == len(_RETRY_DELAYS):
                raise
            server_delay = _retry_after_seconds(exc)
            delay = (
                server_delay
                if server_delay is not None
                else _RETRY_DELAYS[attempt]
            )
            time.sleep(delay)
    raise AssertionError('unreachable')  # pragma: no cover


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


def build_service(creds: Credentials) -> Service:
    return build('gmail', 'v1', credentials=creds)


def get_user_email(creds: Credentials) -> str:
    service = build_service(creds)
    profile = _with_retry(
        service.users().getProfile(userId='me').execute,
    )
    return profile['emailAddress']


def _list_user_labels(service: Service) -> list[dict]:
    response = _with_retry(
        service.users().labels().list(userId='me').execute,
    )
    user_labels = [
        label
        for label in response.get('labels', [])
        if label.get('type') == 'user'
    ]
    return sorted(user_labels, key=lambda label: label['name'])


def _label_has_recent_message(
    service: Service,
    label_id: str,
    age: str,
) -> bool:
    response = _with_retry(
        service.users()
        .messages()
        .list(
            userId='me',
            labelIds=[label_id],
            q=f'newer_than:{age}',
            maxResults=1,
        )
        .execute,
    )
    return bool(response.get('messages'))


def find_old_labels(
    creds: Credentials,
    age: str,
) -> tuple[list[dict], int]:
    service = build_service(creds)
    labels = _list_user_labels(service)
    old = [
        label
        for label in labels
        if not _label_has_recent_message(service, label['id'], age)
    ]
    return old, len(labels)


def search_messages(
    creds: Credentials,
    query: str,
    *,
    max_results: int,
) -> tuple[list[str], int]:
    service = build_service(creds)
    response = _with_retry(
        service.users()
        .messages()
        .list(
            userId='me',
            q=query,
            maxResults=max_results,
        )
        .execute,
    )
    ids = [m['id'] for m in response.get('messages', [])]
    estimate = response.get('resultSizeEstimate', 0)
    return ids, estimate


def _extract_headers(
    payload: dict,
    wanted: Iterable[str],
) -> dict[str, str]:
    """Return header name→value pairs from ``payload`` for headers in ``wanted``.

    Only includes headers present in the payload; callers apply their
    own default policy (e.g. ``''`` or ``None``) for missing entries.
    """
    wanted_set = set(wanted)
    return {
        header['name']: header['value']
        for header in payload.get('headers', []) or []
        if header['name'] in wanted_set
    }


_EXPORT_HEADERS = (
    'Date', 'From', 'To', 'Cc', 'Subject',
    'List-Id', 'List-Unsubscribe',
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
    record: dict = {
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


_WANTED_HEADERS = ('Date', 'From', 'Subject')


def _fetch_message_headers(
    service: Service,
    message_id: str,
) -> dict[str, str]:
    response = _with_retry(
        service.users()
        .messages()
        .get(
            userId='me',
            id=message_id,
            format='metadata',
            metadataHeaders=list(_WANTED_HEADERS),
        )
        .execute,
    )
    payload = response.get('payload', {}) or {}
    found = _extract_headers(payload, _WANTED_HEADERS)
    return {name: found.get(name, '') for name in _WANTED_HEADERS}


def iter_inbox_ids(creds: Credentials) -> Iterator[str]:
    """Yield the ID of every message currently in INBOX."""
    service = build_service(creds)
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


def iter_message_headers(
    creds: Credentials,
    message_ids: Iterable[str],
) -> Iterator[dict[str, str]]:
    """Yield header metadata for each id using a single Gmail client.

    Builds one service and reuses it across the iteration so callers
    rendering a preview don't pay for a rebuild per message.
    """
    service = build_service(creds)
    for message_id in message_ids:
        yield _fetch_message_headers(service, message_id)
