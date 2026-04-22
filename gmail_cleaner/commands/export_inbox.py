import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator

import typer
from googleapiclient.errors import HttpError

from gmail_cleaner import auth, export

STDOUT_MARKER = '-'
PROGRESS_EVERY = 50


@contextmanager
def _open_output(path: str) -> Iterator[IO[str]]:
    if path == STDOUT_MARKER:
        yield sys.stdout
        return
    with Path(path).open('w', encoding='utf-8') as handle:
        yield handle


def _report(written):
    print(f'Exported {written:,} messages...', file=sys.stderr)


def export_inbox(
    output: str = typer.Argument(
        ...,
        help='Path to write JSONL output. Use "-" to write to stdout.',
    ),
) -> None:
    creds = auth.load_token()
    if creds is None:
        typer.echo('Not logged in', err=True)
        raise typer.Exit(1)

    def _on_error(message_id: str, exc: HttpError) -> None:
        print(f'skipped {message_id}: {exc}', file=sys.stderr)

    written = 0
    with _open_output(output) as handle:
        for record in export.iter_inbox_records(creds, on_error=_on_error):
            handle.write(json.dumps(record))
            handle.write('\n')
            written += 1
            if written % PROGRESS_EVERY == 0:
                _report(written)
    _report(written)
