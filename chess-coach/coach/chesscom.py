"""Récupération des parties via l'API publique de Chess.com (aucune connexion requise).

Docs : https://www.chess.com/news/view/published-data-api
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

API = "https://api.chess.com/pub/player/{user}"
HEADERS = {"User-Agent": "ChessCoach/1.0 (application d'entrainement personnelle)", "Accept": "application/json"}


class ChessComError(RuntimeError):
    pass


@dataclass
class OnlineGame:
    url: str
    pgn: str
    white: str
    black: str
    white_rating: int
    black_rating: int
    white_result: str
    black_result: str
    time_class: str
    end_time: int
    rated: bool

    def user_color(self, username: str) -> str | None:
        u = username.lower()
        if self.white.lower() == u:
            return "white"
        if self.black.lower() == u:
            return "black"
        return None

    def user_rating(self, username: str) -> int | None:
        c = self.user_color(username)
        return self.white_rating if c == "white" else self.black_rating if c == "black" else None

    def opponent(self, username: str) -> str:
        return self.black if self.user_color(username) == "white" else self.white

    def user_result(self, username: str) -> str:
        """'win' / 'loss' / 'draw'."""
        c = self.user_color(username)
        r = self.white_result if c == "white" else self.black_result
        if r == "win":
            return "win"
        if r in ("agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"):
            return "draw"
        return "loss"


def _get(url: str, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ChessComError("Joueur introuvable sur Chess.com (vérifie le pseudo).") from exc
        if exc.code == 429:
            raise ChessComError("Chess.com limite les requêtes : réessaie dans une minute.") from exc
        raise ChessComError(f"Erreur Chess.com ({exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ChessComError("Impossible de joindre Chess.com (connexion internet ?).") from exc
    except ValueError as exc:
        raise ChessComError("Réponse inattendue de Chess.com.") from exc


def parse_game(g: dict) -> OnlineGame | None:
    if g.get("rules", "chess") != "chess" or not g.get("pgn"):
        return None
    w, b = g.get("white", {}), g.get("black", {})
    return OnlineGame(
        url=g.get("url", ""),
        pgn=g["pgn"],
        white=w.get("username", "?"),
        black=b.get("username", "?"),
        white_rating=int(w.get("rating", 0) or 0),
        black_rating=int(b.get("rating", 0) or 0),
        white_result=w.get("result", ""),
        black_result=b.get("result", ""),
        time_class=g.get("time_class", ""),
        end_time=int(g.get("end_time", 0) or 0),
        rated=bool(g.get("rated", False)),
    )


def recent_games(username: str, limit: int = 30, max_archives: int = 3) -> list[OnlineGame]:
    """Les `limit` dernières parties (les plus récentes en premier)."""
    user = urllib.parse.quote(username.strip().lower())
    if not user:
        raise ChessComError("Indique ton pseudo Chess.com dans les paramètres.")
    archives = _get(API.format(user=user) + "/games/archives").get("archives", [])
    games: list[OnlineGame] = []
    for url in reversed(archives[-max_archives:]):
        data = _get(url)
        for g in data.get("games", []):
            og = parse_game(g)
            if og:
                games.append(og)
        if len(games) >= limit:
            break
    games.sort(key=lambda g: -g.end_time)
    return games[:limit]


def current_ratings(username: str) -> dict[str, int]:
    """Classements actuels {rapid, blitz, bullet, daily}."""
    user = urllib.parse.quote(username.strip().lower())
    data = _get(API.format(user=user) + "/stats")
    out = {}
    for key, name in (("chess_rapid", "rapid"), ("chess_blitz", "blitz"), ("chess_bullet", "bullet"), ("chess_daily", "daily")):
        if key in data and "last" in data[key]:
            out[name] = int(data[key]["last"].get("rating", 0))
    return out
