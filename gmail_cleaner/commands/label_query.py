import functools

import typer

from gmail_cleaner import auth, cleanup
from gmail_cleaner.commands._progress import echo_sample, report_progress


def label_query(
    query: str = typer.Argument(
        ...,
        help='A Gmail search query, e.g. "subject:[Solutions] in:inbox".',
    ),
    label: str = typer.Option(
        ...,
        '--label',
        help='Name of the user label to apply. Must already exist.',
    ),
    dry_run: bool = typer.Option(
        False,
        '--dry-run',
        help='Count matches and preview headers without labeling.',
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

    found = cleanup.find_label(creds, label)
    if found is None:
        typer.echo(f'Label not found: {label}', err=True)
        raise typer.Exit(1)

    if dry_run:
        preview = cleanup.preview_query(creds, query=query)
        typer.echo('DRY RUN — nothing will be labeled.')
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
            f"Apply label '{label}' to about {scan.estimate:,} emails "
            f"matching '{query}'?",
            abort=True,
        )

    on_progress = functools.partial(report_progress, 'Labeled', scan.estimate)
    labeled = cleanup.label_messages_matching(
        creds,
        query,
        found.label['id'],
        on_progress=on_progress,
    )
    typer.echo(f'Labeled {labeled:,} messages.', err=True)
