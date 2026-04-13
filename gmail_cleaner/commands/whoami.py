import typer

from gmail_cleaner import auth, gmail


def whoami() -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)
    typer.echo(gmail.get_user_email(creds))
