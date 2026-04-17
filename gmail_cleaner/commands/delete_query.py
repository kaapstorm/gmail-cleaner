import functools

import typer

from gmail_cleaner import auth, cleanup
from gmail_cleaner.commands._progress import format_progress


def delete_query(
    query: str = typer.Argument(
        ...,
        help='A Gmail search query, e.g. "in:MySpace older_than:2y".',
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

    on_progress = functools.partial(format_progress, scan.estimate)
    deleted = cleanup.delete_messages_matching(
        creds,
        query,
        on_progress=on_progress,
    )
    typer.echo(f'Deleted {deleted:,} messages.', err=True)
