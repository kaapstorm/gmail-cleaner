import functools
from email.utils import parsedate_to_datetime

import typer
from google.oauth2.credentials import Credentials

from gmail_cleaner import auth, cleanup, gmail
from gmail_cleaner.commands._progress import report_progress


def _format_date(raw: str) -> str:
    try:
        parsed = parsedate_to_datetime(raw)
    except TypeError, ValueError:
        return raw
    if parsed is None:
        return raw
    return parsed.strftime('%Y-%m-%d')


def _echo_sample(creds: Credentials, sample_ids: list[str]) -> None:
    for message_id in sample_ids:
        headers = gmail.get_message_headers(creds, message_id)
        date = _format_date(headers['Date'])
        typer.echo(f'{date}  {headers["From"]}  {headers["Subject"]}')


def delete_query(
    query: str = typer.Argument(
        ...,
        help='A Gmail search query, e.g. "in:MySpace older_than:2y".',
    ),
    dry_run: bool = typer.Option(
        False,
        '--dry-run',
        help='Count matches and preview headers without deleting.',
    ),
    force: bool = typer.Option(
        False,
        '--force',
        help='Skip confirmation prompt.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    if dry_run:
        preview = cleanup.preview_query(creds, query=query)
        typer.echo('DRY RUN — nothing will be deleted.')
        typer.echo('')
        typer.echo(f'{preview.total:,} matches')
        if preview.sample_ids:
            typer.echo('')
            _echo_sample(creds, preview.sample_ids)
        return

    scan = cleanup.scan_for_messages(creds, query)
    if not scan.has_results:
        typer.echo('No matching messages')
        return

    if not force:
        typer.confirm(
            f'Permanently delete about {scan.estimate:,} emails matching '
            f"'{query}'?",
            abort=True,
        )

    on_progress = functools.partial(report_progress, scan.estimate)
    deleted = cleanup.delete_messages_matching(
        creds,
        query,
        on_progress=on_progress,
    )
    typer.echo(f'Deleted {deleted:,} messages.', err=True)
