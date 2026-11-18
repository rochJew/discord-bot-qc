import chess

from coach.engine import EngineLine
from coach.motifs import _is_back_rank_mate, detect_motifs, fork_targets, line_motif


def test_knight_fork():
    b = chess.Board("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1")
    t = fork_targets(b, chess.Move.from_uci("d5c7"))
    assert set(t) == {chess.E8, chess.A8}


def test_no_fork_when_piece_hangs():
    # Le cavalier en c7 serait pris par la dame d8 : pas de vraie fourchette
    b = chess.Board("r2qk3/8/8/3N4/8/8/8/4K3 w - - 0 1")
    assert fork_targets(b, chess.Move.from_uci("d5c7")) == []


def test_pin_and_skewer():
    b = chess.Board("4k3/8/2n5/8/8/3B4/8/4K3 w - - 0 1")
    assert line_motif(b, chess.Move.from_uci("d3b5"))[0] == "clouage"
    b = chess.Board("4q1k1/8/8/4n3/8/8/8/R5K1 w - - 0 1")
    assert line_motif(b, chess.Move.from_uci("a1e1"))[0] == "clouage"
    b = chess.Board("8/8/1q6/8/3k3B/8/8/4K3 w - - 0 1")
    assert line_motif(b, chess.Move.from_uci("h4f2"))[0] == "enfilade"


def test_back_rank():
    b = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
    assert _is_back_rank_mate(b, [chess.Move.from_uci("d1d8")])


def test_detect_hanging_piece_and_principles():
    # Les Blancs jouent Fc4-b5?? : le fou n'est pas protégé et le pion a6 le prend
    pos = chess.Board()
    for san in ["e4", "a6", "Bc4", "e5"]:
        pos.push_san(san)
    played = chess.Move.from_uci("c4b5")
    best = chess.Move.from_uci("g1f3")
    before = EngineLine(30, None, [best])
    after = EngineLine(300, None, [chess.Move.from_uci("a6b5")])
    ms = detect_motifs(pos, played, best, before, after, "blunder")
    kinds = {m.kind for m in ms}
    assert "moved_piece_hanging" in kinds
    assert "same_piece_twice" in kinds


def test_detect_missed_mate():
    pos = chess.Board("6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1")
    best = chess.Move.from_uci("d1d8")
    played = chess.Move.from_uci("h2h3")
    ms = detect_motifs(pos, played, best, EngineLine(10000, 1, [best]), EngineLine(-500, None, []), "mistake")
    assert any(m.kind == "missed_back_rank_mate" for m in ms)
