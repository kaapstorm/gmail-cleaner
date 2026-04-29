import io
from contextlib import redirect_stderr

from gmail_cleaner.commands._progress import report_progress


def test_report_progress_writes_running_count_to_stderr():
    buf = io.StringIO()
    with redirect_stderr(buf):
        report_progress('Deleted', 1523, 500)
    assert 'Deleted 500 of ~1,523 messages' in buf.getvalue()


def test_report_progress_uses_supplied_verb():
    buf = io.StringIO()
    with redirect_stderr(buf):
        report_progress('Archived', 10, 7)
    assert 'Archived 7 of ~10 messages' in buf.getvalue()
