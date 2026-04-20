from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from gmail_cleaner.gmail import (
    _create_filter,
    _get_filter,
    _list_filters,
    build_service,
)


class CreateFiltersError(Exception):
    """Raised when a batch create fails mid-way.

    Carries the filters that were created before the failure so the
    caller can report them and decide how to proceed. The triggering
    API error is preserved as ``__cause__``.
    """

    def __init__(self, created: list[dict]) -> None:
        super().__init__(f'create failed after {len(created)} filter(s)')
        self.created = created


class FilterNotFound(Exception):
    """Raised when a filter ID is not found in Gmail."""


def list_filters(
    creds: Credentials,
    filter_id: str | None = None,
) -> list[dict]:
    service = build_service(creds)
    if filter_id is None:
        return _list_filters(service)
    try:
        return [_get_filter(service, filter_id)]
    except HttpError as exc:
        if getattr(exc.resp, 'status', None) == 404:
            raise FilterNotFound(filter_id) from exc
        raise


def create_filters(
    creds: Credentials,
    filter_dicts: list[dict],
) -> list[dict]:
    service = build_service(creds)
    created: list[dict] = []
    for filter_dict in filter_dicts:
        try:
            created.append(_create_filter(service, filter_dict))
        except HttpError as exc:
            raise CreateFiltersError(created) from exc
    return created
