import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["CHESS_COACH_HOME"] = tempfile.mkdtemp(prefix="chesscoach-test-")

from coach.config import find_stockfish  # noqa: E402

SF = find_stockfish()
needs_engine = pytest.mark.skipif(SF is None, reason="Stockfish non installé")


@pytest.fixture(scope="session")
def engine():
    if SF is None:
        pytest.skip("Stockfish non installé")
    from coach.engine import Engine
    e = Engine(SF, threads=1)
    yield e
    e.close()


@pytest.fixture
def db(tmp_path):
    from coach.db import Database
    d = Database(tmp_path / "t.db")
    yield d
    d.close()
