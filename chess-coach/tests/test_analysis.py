import chess

from coach.analysis import analyse_game
from coach.explain import explain, explanation_text, game_summary

SCHOLAR = '[White "Adv"]\n[Black "Moi"]\n[Result "1-0"]\n\n1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0'


def _load(name):
    import os
    with open(os.path.join(os.path.dirname(__file__), "data", name), encoding="utf-8") as f:
        return f.read()


def test_scholars_mate(engine):
    ga = analyse_game(SCHOLAR, engine, user_name="moi", depth=12, time_per_move=None)
    assert ga.user_color == "black"
    nf6 = ga.moves[5]
    assert nf6.san == "Nf6" and nf6.classification == "blunder"
    assert any(m["kind"] == "allowed_mate" for m in nf6.motifs)
    assert nf6.best_san in ("g6", "Qe7", "Qf6")
    # Le coup du mat est le meilleur
    assert ga.moves[6].classification == "best"
    text = explanation_text(nf6)
    assert "mat" in text and "Dxf7" in text
    assert game_summary(ga)["counts"]["blunder"] >= 1


def test_sample_game(engine):
    ga = analyse_game(_load("sample_game.pgn"), engine, user_name="MonPseudo", depth=12, time_per_move=None)
    assert ga.user_color == "white"
    by_san = {m.san: m for m in ga.moves}
    assert by_san["e4"].classification in ("best", "excellent", "good")
    assert by_san["Be2"].classification == "blunder"          # permet Cf3#
    assert any(m["theme"] == "mat" for m in by_san["Be2"].motifs)
    assert by_san["Nxf7"].classification in ("blunder", "mistake")
    assert by_san["Nd4"].is_user is False
    for m in ga.moves:
        s = explain(m)
        assert s["titre"]
        if m.is_error:
            assert s["meilleur"] and s["retenir"]
    assert 0 < ga.accuracy() <= 100


def test_engine_mate_eval(engine):
    b = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
    line = engine.analyse(b, depth=10, time=None)[0]
    assert line.mate == 1 and line.best == chess.Move.from_uci("d1d8")
