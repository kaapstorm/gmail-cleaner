import typer

from gmail_cleaner import auth, filters


def delete_filter(
    filter_ids: list[str] = typer.Argument(
        ...,
        help='One or more filter IDs to delete.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in', err=True)
        raise typer.Exit(1)

    input_ids = list(filter_ids)
    result = filters.delete_filters(creds, input_ids)
    missing = set(result.missing)
    for filter_id in input_ids:
        if filter_id in missing:
            typer.echo(f'not found {filter_id}', err=True)
        else:
            typer.echo(f'deleted {filter_id}', err=True)
