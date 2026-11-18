"""Interface Stockfish (protocole UCI via python-chess)."""
from __future__ import annotations

import subprocess
import sys
import threading
from dataclasses import dataclass, field

import chess
import chess.engine

MATE_CP = 10000


@dataclass
class EngineLine:
    score_cp: int          # du point de vue du camp au trait
    mate: int | None       # mat en N (positif = le camp au trait mate)
    pv: list[chess.Move] = field(default_factory=list)

    @property
    def best(self) -> chess.Move | None:
        return self.pv[0] if self.pv else None


class EngineError(RuntimeError):
    pass


class Engine:
    """Petit wrapper thread-safe autour de Stockfish."""

    def __init__(self, path: str, threads: int = 2, hash_mb: int = 128):
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(path, **kwargs)
        except Exception as exc:  # FileNotFoundError, PermissionError, EngineTerminatedError
            raise EngineError(f"Impossible de lancer Stockfish ({path}) : {exc}") from exc
        self._lock = threading.Lock()
        try:
            self._engine.configure({"Threads": threads, "Hash": hash_mb})
        except chess.engine.EngineError:
            pass
        self.name = self._engine.id.get("name", "Stockfish")

    def analyse(self, board: chess.Board, depth: int = 16, time: float | None = 1.0, multipv: int = 1) -> list[EngineLine]:
        if board.is_game_over():
            outcome = board.outcome()
            if outcome and outcome.winner is not None:
                # Le camp au trait est maté
                return [EngineLine(-MATE_CP, 0, [])]
            return [EngineLine(0, None, [])]
        limit = chess.engine.Limit(depth=depth, time=time) if time else chess.engine.Limit(depth=depth)
        with self._lock:
            infos = self._engine.analyse(board, limit, multipv=multipv)
        if isinstance(infos, dict):
            infos = [infos]
        lines = []
        for info in infos:
            score = info["score"].pov(board.turn)
            lines.append(EngineLine(score.score(mate_score=MATE_CP), score.mate(), list(info.get("pv", []))))
        return lines

    def best_move(self, board: chess.Board, depth: int = 14, time: float = 0.5) -> chess.Move | None:
        lines = self.analyse(board, depth, time)
        return lines[0].best if lines else None

    def eval_move(self, board: chess.Board, move: chess.Move, depth: int = 14, time: float = 0.5) -> int:
        """Évaluation (cp, point de vue du joueur qui joue `move`) après `move`."""
        b = board.copy()
        b.push(move)
        lines = self.analyse(b, depth, time)
        return -lines[0].score_cp

    def close(self) -> None:
        try:
            with self._lock:
                self._engine.quit()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
