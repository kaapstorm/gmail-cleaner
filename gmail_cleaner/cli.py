import typer

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
