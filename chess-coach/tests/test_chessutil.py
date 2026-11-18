import chess

from coach.chessutil import hanging_pieces, san_fr, see, win_percent


def test_see_basic():
    # Pion e5 défendu par d6 : Cxe5 perd le cavalier contre un pion
    b = chess.Board("rnbqkbnr/ppp2ppp/3p4/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3")
    assert see(b, chess.Move.from_uci("f3e5")) == 1 - 3
    # Prise d'une pièce non défendue
    b = chess.Board("4k3/8/8/3n4/8/8/8/3QK3 w - - 0 1")
    assert see(b, chess.Move.from_uci("d1d5")) == 3
    # Échange égal cavalier contre cavalier
    b = chess.Board("4k3/2p5/3n4/8/4N3/8/8/4K3 w - - 0 1")
    assert see(b, chess.Move.from_uci("e4d6")) == 0


def test_hanging():
    b = chess.Board("4k3/8/8/3n4/8/8/8/3QK3 b - - 0 1")
    h = hanging_pieces(b, chess.BLACK)
    assert h and h[0][0] == chess.D5 and h[0][1] == 3


def test_win_percent_and_san():
    assert abs(win_percent(0) - 50) < 1e-9
    assert win_percent(300) > 70 and win_percent(-300) < 30
    assert san_fr("Nxe5+") == "Cxe5+" and san_fr("Qh5") == "Dh5" and san_fr("O-O") == "O-O" and san_fr("exd8=Q") == "exd8=D"
