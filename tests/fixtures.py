import tempfile
from pathlib import Path

from unmagic import fixture


@fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as tmp_path:
        yield Path(tmp_path)
