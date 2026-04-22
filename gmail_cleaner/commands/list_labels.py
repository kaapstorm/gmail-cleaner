import json
import sys

import typer

from gmail_cleaner import auth, labels


def list_labels() -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in', err=True)
        raise typer.Exit(1)

    for record in labels.list_labels(creds):
        sys.stdout.write(json.dumps(record))
        sys.stdout.write('\n')
