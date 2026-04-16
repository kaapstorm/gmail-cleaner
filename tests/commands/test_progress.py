import io
from contextlib import redirect_stderr

from gmail_cleaner.commands._progress import format_progress


def test_format_progress_writes_running_count_to_stderr():
    buf = io.StringIO()
    with redirect_stderr(buf):
        format_progress(1523, 500)
    assert 'Deleted 500 of ~1,523 messages' in buf.getvalue()
