import functools

import typer

from gmail_cleaner import auth, cleanup
from gmail_cleaner.commands._progress import echo_sample, report_progress


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
        typer.echo('Not logged in', err=True)
        raise typer.Exit(1)

    if dry_run:
        preview = cleanup.preview_query(creds, query=query)
        typer.echo('DRY RUN — nothing will be deleted.')
        typer.echo('')
        typer.echo(f'{preview.total:,} matches')
        if preview.sample_ids:
            typer.echo('')
            echo_sample(creds, preview.sample_ids)
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
