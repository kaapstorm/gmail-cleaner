import time
from collections.abc import Iterator
from typing import Any, Callable, TypeVar

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

_RETRY_DELAYS = (2.5, 5.0)
_LIST_PAGE_SIZE = 500

T = TypeVar('T')


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (OSError, TimeoutError)):
        return True
    if isinstance(exc, HttpError):
        status = getattr(exc.resp, 'status', None)
        return status == 429 or (status is not None and status >= 500)
    return False


def _with_retry(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    last_exc: BaseException | None = None
    for delay in (0.0, *_RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_retryable(exc):
                raise
            last_exc = exc
    assert last_exc is not None
    raise last_exc


def _iter_message_ids(service, query: str) -> Iterator[str]:
    request = (
        service.users()
        .messages()
        .list(userId='me', q=query, maxResults=_LIST_PAGE_SIZE)
    )
    while request is not None:
        response = request.execute()
        for m in response.get('messages', []):
            yield m['id']
        request = (
            service.users()
            .messages()
            .list_next(previous_request=request, previous_response=response)
        )


def build_service(creds: Credentials):
    return build('gmail', 'v1', credentials=creds)


def get_user_email(creds: Credentials) -> str:
    service = build_service(creds)
    profile = service.users().getProfile(userId='me').execute()
    return profile['emailAddress']


def _list_user_labels(service) -> list[dict]:
    response = service.users().labels().list(userId='me').execute()
    user_labels = [
        label
        for label in response.get('labels', [])
        if label.get('type') == 'user'
    ]
    return sorted(user_labels, key=lambda label: label['name'])


def _label_has_recent_message(
    service,
    label_id: str,
    age: str,
) -> bool:
    response = (
        service.users()
        .messages()
        .list(
            userId='me',
            labelIds=[label_id],
            q=f'newer_than:{age}',
            maxResults=1,
        )
        .execute()
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
    response = (
        service.users()
        .messages()
        .list(
            userId='me',
            q=query,
            maxResults=max_results,
        )
        .execute()
    )
    ids = [m['id'] for m in response.get('messages', [])]
    estimate = response.get('resultSizeEstimate', 0)
    return ids, estimate


_WANTED_HEADERS = ('Date', 'From', 'Subject')


def get_message_headers(
    creds: Credentials,
    message_id: str,
) -> dict[str, str]:
    service = build_service(creds)
    response = (
        service.users()
        .messages()
        .get(
            userId='me',
            id=message_id,
            format='metadata',
            metadataHeaders=list(_WANTED_HEADERS),
        )
        .execute()
    )
    found = {
        header['name']: header['value']
        for header in response.get('payload', {}).get('headers', [])
        if header['name'] in _WANTED_HEADERS
    }
    return {name: found.get(name, '') for name in _WANTED_HEADERS}
