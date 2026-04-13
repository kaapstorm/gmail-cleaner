import typer

from gmail_cleaner import auth


def logout() -> None:
    auth.delete_token()
    typer.echo('Logged out')
