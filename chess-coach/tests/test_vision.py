import os
import sys

import chess
import numpy as np
import pytest


from PySide6.QtWidgets import QApplication  # noqa: E402

from coach.ui.board import ChessBoardWidget, qimage_to_bgr  # noqa: E402
from coach.vision import GameTracker, PieceRecognizer, find_board  # noqa: E402

app = QApplication.instance() or QApplication([])


def render(board, flipped=False, size=560, last_move=None):
    w = ChessBoardWidget()
    w.set_board(board, last_move)
    w.set_flipped(flipped)
    return qimage_to_bgr(w.render_image(size))


def screen_with(board_img, x=230, y=120, W=1600, H=900):
    rng = np.random.default_rng(0)
    scr = np.full((H, W, 3), (33, 36, 39), np.uint8)
    scr[:60, :, :] = (60, 60, 60)
    scr[200:260, 1000:1500] = rng.integers(0, 255, (60, 500, 3), dtype=np.uint8)
    h, w = board_img.shape[:2]
    scr[y:y + h, x:x + w] = board_img
    return scr


@pytest.mark.parametrize("flipped", [False, True])
def test_find_calibrate_and_track(flipped):
    start = render(chess.Board(), flipped)
    scr = screen_with(start)
    rect = find_board(scr)
    assert rect is not None
    assert abs(rect.x - 230) <= 3 and abs(rect.y - 120) <= 3 and abs(rect.size - 560) <= 5
    rec = PieceRecognizer()
    assert rec.calibrate(rect.crop(scr)) is None
    assert rec.white_bottom == (not flipped)
    # Une vraie partie avec roque, prise en passant, promotion
    pgn_moves = "e4 d5 exd5 c5 dxc6 Nf6 cxb7 Bd7 bxa8=Q Qc7 Nf3 e5 Bc4 Bd6 O-O O-O".split()
    tracker = GameTracker()
    b = chess.Board()
    for san in pgn_moves:
        mv = b.parse_san(san)
        b.push(mv)
        img = screen_with(render(b, flipped, last_move=mv))
        obs = rec.read(rect.crop(img))
        assert obs == {sq: ("w" if p.color else "b") + p.symbol().upper() for sq, p in b.piece_map().items()}, san
        tracker.feed(obs)
        tracker.feed(obs)
    assert tracker.board.move_stack == b.move_stack


def test_tracker_skipped_frame():
    t = GameTracker()
    b = chess.Board()
    for san in ["e4", "e5"]:
        b.push_san(san)
    from coach.vision import placement
    obs = placement(b)
    t.feed(obs)
    assert t.feed(obs) and len(t.board.move_stack) == 2


def test_brown_theme_small_board():
    from PySide6.QtGui import QColor

    def rnd(board, last=None):
        w = ChessBoardWidget()
        w.light, w.dark = QColor("#f0d9b5"), QColor("#b58863")
        w.set_board(board, last)
        return qimage_to_bgr(w.render_image(400))

    scr = screen_with(rnd(chess.Board()), x=700, y=300)
    rect = find_board(scr)
    assert rect is not None and abs(rect.size - 400) <= 5
    rec = PieceRecognizer()
    assert rec.calibrate(rect.crop(scr)) is None
    b = chess.Board()
    t = GameTracker()
    for san in "d4 Nf6 c4 e6 Nc3 Bb4 Qc2 O-O a3 Bxc3+ Qxc3".split():
        mv = b.parse_san(san)
        b.push(mv)
        obs = rec.read(rect.crop(screen_with(rnd(b, mv), x=700, y=300)))
        t.feed(obs)
        t.feed(obs)
    assert t.board.fen() == b.fen()
