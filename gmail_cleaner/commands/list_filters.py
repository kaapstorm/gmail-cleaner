import json
import sys

import typer

from gmail_cleaner import auth, filters


def list_filters() -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    for record in filters.list_filters(creds):
        sys.stdout.write(json.dumps(record))
        sys.stdout.write('\n')
