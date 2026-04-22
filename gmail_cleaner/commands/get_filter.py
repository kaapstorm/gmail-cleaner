import json
import sys

import typer

from gmail_cleaner import auth, filters


def get_filter(
    filter_id: str = typer.Argument(..., help='ID of the filter to fetch.'),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    try:
        record = filters.get_filter(creds, filter_id)
    except filters.FilterNotFound as exc:
        typer.echo(f'Filter not found: {exc}', err=True)
        raise typer.Exit(1) from exc

    sys.stdout.write(json.dumps(record))
    sys.stdout.write('\n')
