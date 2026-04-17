import sys
from email.utils import parsedate_to_datetime

import typer
from google.oauth2.credentials import Credentials

from gmail_cleaner import gmail


def report_progress(total_estimate: int, deleted: int) -> None:
    """Write a running delete count to stderr.

    Called repeatedly during long-running deletes. Output goes to
    stderr so it doesn't pollute stdout for callers piping the
    command's output.
    """
    print(
        f'Deleted {deleted:,} of ~{total_estimate:,} messages...',
        file=sys.stderr,
    )


def format_date(raw: str) -> str:
    try:
        parsed = parsedate_to_datetime(raw)
    except TypeError, ValueError:
        return raw
    if parsed is None:
        return raw
    return parsed.strftime('%Y-%m-%d')


def echo_sample(creds: Credentials, sample_ids: list[str]) -> None:
    for headers in gmail.iter_message_headers(creds, sample_ids):
        date = format_date(headers['Date'])
        typer.echo(f'{date}  {headers["From"]}  {headers["Subject"]}')
