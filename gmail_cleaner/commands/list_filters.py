import json
import sys

import typer

from gmail_cleaner import auth, filters


def list_filters(
    id: str = typer.Option(
        None,
        '--id',
        help='Return the filter with this ID instead of listing all.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    try:
        records = filters.list_filters(creds, filter_id=id)
    except filters.FilterNotFound as exc:
        typer.echo(f'Filter not found: {exc}', err=True)
        raise typer.Exit(1) from exc

    for record in records:
        sys.stdout.write(json.dumps(record))
        sys.stdout.write('\n')
