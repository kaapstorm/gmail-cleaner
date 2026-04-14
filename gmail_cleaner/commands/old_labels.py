import re

import typer

from gmail_cleaner import auth, gmail

_AGE_RE = re.compile(r'^\d+[dmy]$')


def _validate_age(value: str) -> str:
    if not _AGE_RE.match(value):
        raise typer.BadParameter('must look like 30d, 6m, or 2y')
    return value


def old_labels(
    age: str = typer.Option(
        '2y',
        help=(
            'Maximum age of the most recent message for a label to be '
            'considered old. Format: <number><d|m|y>.'
        ),
        callback=_validate_age,
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    labels = gmail.list_user_labels(creds)
    old = [
        label
        for label in labels
        if not gmail.label_has_recent_message(creds, label['id'], age)
    ]
    for label in old:
        typer.echo(label['name'])
    typer.echo(
        f'{len(old)} of {len(labels)} labels have no messages '
        f'newer than {age}',
        err=True,
    )
