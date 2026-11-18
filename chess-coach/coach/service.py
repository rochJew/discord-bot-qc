"""Opérations de haut niveau (sans interface) : analyser et enregistrer une partie."""
from __future__ import annotations

from .analysis import analyse_game
from .config import Settings, find_stockfish
from .db import Database
from .engine import Engine, EngineError
from .explain import game_summary
from .training import exercises_from_game


def require_engine(settings: Settings) -> str:
    path = find_stockfish(settings)
    if not path:
        raise EngineError("Stockfish est introuvable. Va dans Paramètres pour le télécharger ou indiquer son emplacement.")
    return path


def analyse_and_store(db: Database, settings: Settings, pgn: str, *, url: str = "", source: str = "pgn",
                      user_color: str | None = None, user_rating: int | None = None, opp_rating: int | None = None,
                      time_class: str = "", played_at: int | None = None, user_result: str = "",
                      progress=None, should_stop=None) -> int:
    path = require_engine(settings)
    with Engine(path, threads=settings.engine_threads) as eng:
        ga = analyse_game(pgn, eng, user_name=settings.chesscom_username or None, user_color=user_color,
                          depth=settings.analysis_depth, time_per_move=settings.analysis_time,
                          progress=progress, should_stop=should_stop)
    if not user_result and ga.user_color:
        r = ga.result
        user_result = "draw" if r == "1/2-1/2" else ("win" if (r == "1-0") == (ga.user_color == "white") else "loss") if r in ("1-0", "0-1") else ""
    summary = game_summary(ga)["text"]
    gid = db.save_analysis(ga, url=url, source=source, user_rating=user_rating, opp_rating=opp_rating,
                           time_class=time_class, played_at=played_at, user_result=user_result, summary=summary)
    exercises_from_game(db, gid)
    return gid
