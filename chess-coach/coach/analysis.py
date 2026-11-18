"""Analyse complète d'une partie : évaluation de chaque coup, classification, motifs."""
from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from typing import Callable

import chess
import chess.pgn

from .chessutil import game_phase, move_accuracy, win_percent
from .engine import Engine
from .motifs import detect_motifs

# Classification (du meilleur au pire)
CLASS_ORDER = ["best", "excellent", "good", "book", "inaccuracy", "mistake", "miss", "blunder"]
CLASS_FR = {
    "best": "Meilleur coup",
    "excellent": "Excellent",
    "good": "Bon coup",
    "book": "Théorie",
    "inaccuracy": "Imprécision",
    "mistake": "Erreur",
    "miss": "Occasion manquée",
    "blunder": "Gaffe",
}
CLASS_SYMBOL = {
    "best": "★", "excellent": "!", "good": "✓", "book": "📖",
    "inaccuracy": "?!", "mistake": "?", "miss": "✗", "blunder": "??",
}
CLASS_COLOR = {
    "best": "#5dbb63", "excellent": "#7cc576", "good": "#97af8b", "book": "#a88865",
    "inaccuracy": "#f0c15c", "mistake": "#e58f2a", "miss": "#e2703a", "blunder": "#ca3431",
}
ERROR_CLASSES = ("inaccuracy", "mistake", "miss", "blunder")


@dataclass
class MoveAnalysis:
    ply: int                    # 0 = premier coup des Blancs
    move_number: int
    color: str                  # "white" / "black"
    san: str
    uci: str
    fen_before: str
    fen_after: str
    is_user: bool
    eval_before: int            # cp, point de vue des Blancs
    eval_after: int             # cp, point de vue des Blancs
    mate_before: int | None     # mat en N, point de vue des Blancs (positif = Blancs matent)
    mate_after: int | None
    best_uci: str
    best_san: str
    best_pv_san: list[str]
    reply_pv_san: list[str]     # meilleure suite de l'adversaire après le coup joué
    win_before: float           # chances de gain du joueur (0-100) avec le meilleur coup
    win_after: float            # chances de gain du joueur après le coup joué
    wp_loss: float
    accuracy: float
    classification: str
    phase: str
    motifs: list[dict] = field(default_factory=list)
    explanation: str = ""

    @property
    def is_error(self) -> bool:
        return self.classification in ERROR_CLASSES

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GameAnalysis:
    white: str
    black: str
    result: str
    user_color: str | None
    moves: list[MoveAnalysis]
    headers: dict
    pgn: str

    def user_moves(self) -> list[MoveAnalysis]:
        return [m for m in self.moves if m.is_user]

    def accuracy(self, color: str | None = None) -> float:
        color = color or self.user_color or "white"
        ms = [m.accuracy for m in self.moves if m.color == color]
        return round(sum(ms) / len(ms), 1) if ms else 0.0

    def counts(self, color: str | None = None) -> dict[str, int]:
        color = color or self.user_color or "white"
        c = {k: 0 for k in CLASS_ORDER}
        for m in self.moves:
            if m.color == color:
                c[m.classification] += 1
        return c

    def key_moments(self, only_user: bool = True) -> list[MoveAnalysis]:
        res = [m for m in self.moves if m.is_error and (m.is_user or not only_user)]
        return sorted(res, key=lambda m: -m.wp_loss)


def parse_pgn(pgn_text: str) -> chess.pgn.Game:
    game = chess.pgn.read_game(io.StringIO(pgn_text))
    if game is None:
        raise ValueError("PGN illisible")
    if game.errors:
        raise ValueError(f"PGN invalide : {game.errors[0]}")
    return game


def _cp_white(score_cp: int, turn: chess.Color) -> int:
    return score_cp if turn == chess.WHITE else -score_cp


def _mate_white(mate: int | None, turn: chess.Color) -> int | None:
    if mate is None:
        return None
    return mate if turn == chess.WHITE else -mate


def classify(loss: float, played_is_best: bool, prev_opp_loss: float, best_gain_chance: bool) -> str:
    if played_is_best or loss < 0.5:
        return "best"
    if loss < 2:
        return "excellent"
    if loss < 5:
        return "good"
    if loss < 10:
        return "inaccuracy"
    if prev_opp_loss >= 10 and best_gain_chance and loss < 30:
        return "miss"
    if loss < 20:
        return "mistake"
    return "blunder"


def analyse_game(
    pgn_text: str,
    engine: Engine,
    user_name: str | None = None,
    user_color: str | None = None,
    depth: int = 16,
    time_per_move: float = 1.0,
    progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> GameAnalysis:
    game = parse_pgn(pgn_text)
    headers = dict(game.headers)
    white, black = headers.get("White", "?"), headers.get("Black", "?")
    if user_color is None and user_name:
        if white.lower() == user_name.lower():
            user_color = "white"
        elif black.lower() == user_name.lower():
            user_color = "black"

    board = game.board()
    moves = list(game.mainline_moves())
    positions = [board.copy()]
    for mv in moves:
        board.push(mv)
        positions.append(board.copy())

    # Une analyse par position : l'éval après le coup N = l'éval avant le coup N+1
    lines = []
    total = len(positions)
    for i, pos in enumerate(positions):
        if should_stop and should_stop():
            raise InterruptedError("Analyse annulée")
        lines.append(engine.analyse(pos, depth=depth, time=time_per_move, multipv=1)[0])
        if progress:
            progress(i + 1, total)

    result: list[MoveAnalysis] = []
    prev_loss_by_ply: dict[int, float] = {}
    for i, mv in enumerate(moves):
        pos = positions[i]
        after = positions[i + 1]
        turn = pos.turn
        before_line, after_line = lines[i], lines[i + 1]
        # Point de vue du joueur qui joue
        cp_best = before_line.score_cp
        cp_after = -after_line.score_cp
        best = before_line.best or mv
        played_is_best = best == mv
        w_before = win_percent(cp_best)
        w_after = w_before if played_is_best else min(w_before, win_percent(cp_after))
        loss = max(0.0, w_before - w_after)
        prev_opp_loss = prev_loss_by_ply.get(i - 1, 0.0)
        best_gain_chance = w_before >= 60
        cls = classify(loss, played_is_best, prev_opp_loss, best_gain_chance)
        # Mat manqué : on avait un mat forcé et on ne l'a plus
        if before_line.mate is not None and before_line.mate > 0 and not played_is_best:
            if not (after_line.mate is not None and after_line.mate < 0) and cls in ("best", "excellent", "good"):
                cls = "inaccuracy" if w_after > 90 else "mistake"
        # Permettre un mat forcé alors qu'on pouvait l'éviter = gaffe
        if after_line.mate is not None and after_line.mate > 0 and not (before_line.mate is not None and before_line.mate < 0):
            cls = "blunder" if after_line.mate <= 3 or loss >= 5 else ("mistake" if cls not in ("blunder",) else cls)
        prev_loss_by_ply[i] = loss

        color = "white" if turn == chess.WHITE else "black"
        is_user = (user_color == color) if user_color else True
        best_pv_san = _pv_san(pos, before_line.pv[:8])
        reply_pv_san = _pv_san(after, after_line.pv[:6])
        motifs = []
        if cls in ERROR_CLASSES or (is_user and pos.fullmove_number <= 12):
            motifs = detect_motifs(pos, mv, best, before_line, after_line, cls)
        result.append(MoveAnalysis(
            ply=i,
            move_number=pos.fullmove_number,
            color=color,
            san=pos.san(mv),
            uci=mv.uci(),
            fen_before=pos.fen(),
            fen_after=after.fen(),
            is_user=is_user,
            eval_before=_cp_white(before_line.score_cp, turn),
            eval_after=_cp_white(after_line.score_cp, after.turn),
            mate_before=_mate_white(before_line.mate, turn),
            mate_after=_mate_white(after_line.mate, after.turn),
            best_uci=best.uci(),
            best_san=pos.san(best) if best in pos.legal_moves else "",
            best_pv_san=best_pv_san,
            reply_pv_san=reply_pv_san,
            win_before=round(w_before, 1),
            win_after=round(w_after, 1),
            wp_loss=round(loss, 1),
            accuracy=round(move_accuracy(w_before, w_after), 1),
            classification=cls,
            phase=game_phase(pos),
            motifs=[m.to_dict() for m in motifs],
        ))
    return GameAnalysis(white, black, headers.get("Result", "*"), user_color, result, headers, pgn_text)


def _pv_san(board: chess.Board, pv: list[chess.Move]) -> list[str]:
    b = board.copy()
    out = []
    for mv in pv:
        if mv not in b.legal_moves:
            break
        out.append(b.san(mv))
        b.push(mv)
    return out
