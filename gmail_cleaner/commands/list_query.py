from email.utils import parsedate_to_datetime

import typer

from gmail_cleaner import auth, gmail

COUNT_CAP = 100
PREVIEW_LIMIT = 10


def _format_count(num_returned: int, estimate: int) -> str:
    if num_returned < COUNT_CAP:
        return f'{num_returned} matches'
    if estimate < COUNT_CAP:
        return f'{COUNT_CAP}+ matches'
    return f'About {estimate} matches'


def _format_date(raw: str) -> str:
    try:
        parsed = parsedate_to_datetime(raw)
    except TypeError, ValueError:
        return raw
    if parsed is None:
        return raw
    return parsed.strftime('%Y-%m-%d')


def list_query(
    query: str = typer.Argument(
        ...,
        help='A Gmail search query, e.g. "in:MySpace older_than:2y".',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in')
        raise typer.Exit(1)

    ids, estimate = gmail.search_messages(
        creds,
        query,
        max_results=COUNT_CAP,
    )
    typer.echo(_format_count(len(ids), estimate))
    typer.echo('')
    for headers in gmail.iter_message_headers(creds, ids[:PREVIEW_LIMIT]):
        date = _format_date(headers['Date'])
        typer.echo(f'{date}  {headers["From"]}  {headers["Subject"]}')
