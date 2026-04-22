from typing import NamedTuple

from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from gmail_cleaner import gmail


class DeleteResult(NamedTuple):
    deleted: int
    missing: list[str]


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


def list_filters(creds: Credentials) -> list[dict]:
    service = gmail.build_service(creds)
    return gmail.list_filters(service)


def get_filter(creds: Credentials, filter_id: str) -> dict:
    service = gmail.build_service(creds)
    try:
        return gmail.get_filter(service, filter_id)
    except HttpError as exc:
        if getattr(exc.resp, 'status', None) == 404:
            raise FilterNotFound(filter_id) from exc
        raise


def create_filters(
    creds: Credentials,
    filter_dicts: list[dict],
) -> list[dict]:
    service = gmail.build_service(creds)
    created: list[dict] = []
    for filter_dict in filter_dicts:
        try:
            created.append(gmail.create_filter(service, filter_dict))
        except HttpError as exc:
            raise CreateFiltersError(created) from exc
    return created


def delete_filters(
    creds: Credentials,
    filter_ids: list[str],
) -> DeleteResult:
    service = gmail.build_service(creds)
    deleted = 0
    missing: list[str] = []
    for filter_id in filter_ids:
        try:
            gmail.delete_filter(service, filter_id)
            deleted += 1
        except HttpError as exc:
            if getattr(exc.resp, 'status', None) == 404:
                missing.append(filter_id)
                continue
            raise
    return DeleteResult(deleted=deleted, missing=missing)
