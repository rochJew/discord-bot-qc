import json

import chess

from coach.chesscom import parse_game
from coach.lessons import LESSONS
from coach.progress import compute_progress, estimate_elo
from coach.service import analyse_and_store
from coach.training import OPENING_QUIZ, check_move, get_exercise, import_bank, select_exercises
from tests.test_analysis import SCHOLAR, _load


def test_bank_is_valid():
    import os
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "coach", "data", "puzzles.json")
    bank = json.load(open(path, encoding="utf-8"))
    assert len(bank) >= 60
    for p in bank:
        b = chess.Board(p["fen"])
        assert b.is_valid()
        for u in p["solution"]:
            mv = chess.Move.from_uci(u)
            assert mv in b.legal_moves, p
            b.push(mv)
        if p["theme"] == "mat":
            assert b.is_checkmate(), p
    for q in OPENING_QUIZ:
        b = chess.Board(q["fen"])
        assert all(chess.Move.from_uci(u) in b.legal_moves for u in q["good"])


def test_lessons_valid():
    for lesson in LESSONS:
        for st in lesson.steps:
            b = chess.Board(st.fen)
            assert b.is_valid(), (lesson.id, st.fen)
            for san in st.moves:
                b.push_san(san)


def test_full_pipeline(db, engine):
    from coach.config import Settings
    s = Settings(chesscom_username="MonPseudo", analysis_depth=10, analysis_time=0.1, engine_threads=1)
    s.stockfish_path = ""
    gid = analyse_and_store(db, s, _load("sample_game.pgn"), played_at=1, user_rating=431, opp_rating=445)
    gid2 = analyse_and_store(db, s, SCHOLAR.replace("Moi", "MonPseudo"), played_at=2, user_rating=425)
    assert gid != gid2
    g = db.game(gid)
    assert g["user_color"] == "white" and g["user_result"] == "loss" and g["blunders"] >= 1
    assert len(db.load_moves(gid)) == 14
    # Réanalyser la même partie remplace l'ancienne
    gid3 = analyse_and_store(db, s, _load("sample_game.pgn"), played_at=1)
    assert len(db.games()) == 2 and db.game(gid) is None and db.game(gid3)
    # Exercices personnels créés à partir des erreurs
    perso = [r for r in db.exercises() if r["source"] == "partie"]
    assert perso
    import_bank(db)
    assert len(db.exercises()) > len(perso)
    sel = select_exercises(db, 10, seed=1)
    assert len(sel) == 10 and sum(e.source == "partie" for e in sel) >= 1
    # Exercice « mat » de la banque : le bon coup est accepté, un mauvais refusé
    ex = next(e for e in select_exercises(db, 50, "mat", seed=2) if e.theme == "mat")
    b = ex.board
    good = chess.Move.from_uci(ex.solution[0])
    assert check_move(ex, b, good, 0).status in ("correct", "solved")
    bad = next(m for m in b.legal_moves if m != good and not b.gives_check(m))
    assert check_move(ex, b, bad, 0, engine).status == "wrong"
    db.record_attempt(ex.id, ex.theme, True)
    assert get_exercise(db, ex.id).id == ex.id
    p = compute_progress(db)
    assert p.games == 2 and p.exercises_done == 1 and p.chesscom_rating == 425
    assert any(t.theme == "mat" and t.errors > 0 for t in p.themes)
    assert p.weaknesses


def test_estimate_elo_monotonic():
    assert estimate_elo(50, 4) < estimate_elo(65, 2) < estimate_elo(80, 0.5)
    assert 250 <= estimate_elo(55, 3.5) <= 600


def test_chesscom_parse():
    g = parse_game({"url": "https://www.chess.com/game/live/1", "pgn": "[White \"a\"]\n\n1. e4 *", "rules": "chess",
                    "time_class": "rapid", "end_time": 5, "rated": True,
                    "white": {"username": "Moi", "rating": 432, "result": "win"},
                    "black": {"username": "Bob", "rating": 450, "result": "resigned"}})
    assert g.user_color("moi") == "white" and g.user_result("moi") == "win" and g.user_result("bob") == "loss"
    assert g.user_rating("bob") == 450 and g.opponent("Moi") == "Bob"
    assert parse_game({"rules": "chess960", "pgn": "x"}) is None


def test_llm_mocked(monkeypatch, engine):
    """Le coach IA reçoit les faits du moteur et renvoie le texte du modèle (client simulé)."""
    from coach import llm
    from coach.analysis import analyse_game

    captured = {}

    class Block:
        type = "text"
        text = "**Ce qui s'est passé**\nTu as laissé un mat."

    class Resp:
        stop_reason = "end_turn"
        content = [Block()]

    class Msgs:
        def create(self, **kw):
            captured.update(kw)
            return Resp()

    coach = llm.AICoach.__new__(llm.AICoach)
    import anthropic
    coach._anthropic = anthropic
    coach.system = llm.SYSTEM_PROMPT.format(elo=430, target=1000)
    coach.client = type("C", (), {"beta": type("B", (), {"messages": Msgs()})()})()
    ga = analyse_game(SCHOLAR, engine, user_name="moi", depth=10, time_per_move=None)
    out = coach.explain_move(ga.moves[5])
    assert "mat" in out
    assert captured["model"] == "claude-opus-5-5"
    prompt = captured["messages"][0]["content"]
    assert "Cf6" in prompt and "Dxf7" in prompt
    assert "<b>Ce qui s'est passé</b>" in llm.markdown_to_html(out)
