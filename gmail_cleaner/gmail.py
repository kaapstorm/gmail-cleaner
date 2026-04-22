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


def with_retry(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
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


def build_service(creds: Credentials) -> Service:
    return build('gmail', 'v1', credentials=creds)


def get_user_email(creds: Credentials) -> str:
    service = build_service(creds)
    profile = with_retry(
        service.users().getProfile(userId='me').execute,
    )
    return profile['emailAddress']


def list_user_labels(service: Service) -> list[dict]:
    response = with_retry(
        service.users().labels().list(userId='me').execute,
    )
    user_labels = [
        label
        for label in response.get('labels', [])
        if label.get('type') == 'user'
    ]
    return sorted(user_labels, key=lambda label: label['name'])


def create_label(service: Service, label_dict: dict) -> dict:
    # No with_retry: POST is not idempotent, and a 5xx retry that
    # actually succeeded would leave duplicate labels.
    return (
        service.users().labels().create(userId='me', body=label_dict).execute()
    )


def label_has_recent_message(
    service: Service,
    label_id: str,
    age: str,
) -> bool:
    response = with_retry(
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
    labels = list_user_labels(service)
    old = [
        label
        for label in labels
        if not label_has_recent_message(service, label['id'], age)
    ]
    return old, len(labels)


def search_messages(
    creds: Credentials,
    query: str,
    *,
    max_results: int,
) -> tuple[list[str], int]:
    service = build_service(creds)
    response = with_retry(
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


def extract_headers(
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


_WANTED_HEADERS = ('Date', 'From', 'Subject')


def fetch_message_headers(
    service: Service,
    message_id: str,
) -> dict[str, str]:
    response = with_retry(
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
    found = extract_headers(payload, _WANTED_HEADERS)
    return {name: found.get(name, '') for name in _WANTED_HEADERS}


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
        yield fetch_message_headers(service, message_id)


def list_filters(service: Service) -> list[dict]:
    response = with_retry(
        service.users().settings().filters().list(userId='me').execute,
    )
    return response.get('filter', [])


def delete_filter(service: Service, filter_id: str) -> None:
    with_retry(
        service.users()
        .settings()
        .filters()
        .delete(userId='me', id=filter_id)
        .execute,
    )


def create_filter(service: Service, filter_dict: dict) -> dict:
    # No with_retry: POST is not idempotent, and Gmail filters have no
    # client-supplied key to dedupe on. A 5xx that actually created the
    # filter would, on retry, produce a silent duplicate.
    return (
        service.users()
        .settings()
        .filters()
        .create(userId='me', body=filter_dict)
        .execute()
    )


def get_filter(service: Service, filter_id: str) -> dict:
    return with_retry(
        service.users()
        .settings()
        .filters()
        .get(userId='me', id=filter_id)
        .execute,
    )
