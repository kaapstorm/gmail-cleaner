import typer
from googleapiclient.discovery import build

from gmail_cleaner import auth


def whoami() -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)
    service = build('gmail', 'v1', credentials=creds)
    profile = service.users().getProfile(userId='me').execute()
    typer.echo(profile['emailAddress'])
