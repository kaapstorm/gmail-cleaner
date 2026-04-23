import typer

from gmail_cleaner.commands.archive_query import archive_query
from gmail_cleaner.commands.create_filter import create_filter
from gmail_cleaner.commands.create_label import create_label
from gmail_cleaner.commands.delete_filter import delete_filter
from gmail_cleaner.commands.delete_label import delete_label
from gmail_cleaner.commands.delete_query import delete_query
from gmail_cleaner.commands.export_inbox import export_inbox
from gmail_cleaner.commands.get_filter import get_filter
from gmail_cleaner.commands.label_query import label_query
from gmail_cleaner.commands.list_filters import list_filters
from gmail_cleaner.commands.list_labels import list_labels
from gmail_cleaner.commands.list_query import list_query
from gmail_cleaner.commands.login import login
from gmail_cleaner.commands.logout import logout
from gmail_cleaner.commands.old_labels import old_labels
from gmail_cleaner.commands.whoami import whoami

app = typer.Typer(
    help='Command-line tools for cleaning up a Gmail mailbox.',
    no_args_is_help=True,
)
app.command(help='Authenticate with Google and save credentials.')(login)
app.command(help='Show the email address of the logged-in account.')(whoami)
app.command(help='Remove saved credentials.')(logout)
app.command(
    help='List user labels whose most recent message is older than --age.',
)(old_labels)
app.command(
    help='Show the count and first 10 messages matching a Gmail query.',
)(list_query)
app.command(
    help='Permanently delete all emails matching a Gmail query.',
)(delete_query)
app.command(
    help='Archive (remove INBOX label from) all emails matching a Gmail query.',
)(archive_query)
app.command(
    help='Apply a user label to all emails matching a Gmail query.',
)(label_query)
app.command(
    help='Permanently delete a label, its filters, and all emails it labels.',
)(delete_label)
app.command(
    help='Export inbox messages as JSONL for filter-optimization analysis.',
)(export_inbox)
app.command(help='List Gmail filters as JSONL.')(list_filters)
app.command(help='Fetch a single Gmail filter by ID as JSON.')(get_filter)
app.command(help='Create Gmail filters from a JSONL file (or stdin via "-").')(
    create_filter,
)
app.command(help='Delete Gmail filters by ID.')(delete_filter)
app.command(help='List user Gmail labels as JSONL.')(list_labels)
app.command(help='Create Gmail labels from a JSONL file (or stdin via "-").')(
    create_label,
)
