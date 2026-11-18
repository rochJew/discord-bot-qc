"""Base SQLite locale : parties analysées, coups, exercices, tentatives."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

from .analysis import GameAnalysis, MoveAnalysis
from .config import app_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT, url TEXT UNIQUE, pgn TEXT,
    white TEXT, black TEXT, user_color TEXT, result TEXT, user_result TEXT,
    user_rating INTEGER, opp_rating INTEGER, time_class TEXT,
    played_at INTEGER, analyzed_at INTEGER,
    accuracy REAL, blunders INTEGER, mistakes INTEGER, inaccuracies INTEGER, misses INTEGER,
    summary TEXT, ai_review TEXT
);
CREATE TABLE IF NOT EXISTS moves (
    game_id INTEGER, ply INTEGER, data TEXT, is_user INTEGER, classification TEXT,
    ai_explanation TEXT,
    PRIMARY KEY (game_id, ply)
);
CREATE TABLE IF NOT EXISTS motif_events (
    game_id INTEGER, ply INTEGER, theme TEXT, kind TEXT, side TEXT, severity REAL, ts INTEGER
);
CREATE TABLE IF NOT EXISTS exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fen TEXT, solution TEXT, theme TEXT, kind TEXT, source TEXT,
    game_id INTEGER, ply INTEGER, title TEXT, hint TEXT, explanation TEXT,
    created INTEGER, attempts INTEGER DEFAULT 0, successes INTEGER DEFAULT 0,
    streak INTEGER DEFAULT 0, next_due INTEGER DEFAULT 0,
    UNIQUE(fen, solution)
);
CREATE TABLE IF NOT EXISTS attempts (
    exercise_id INTEGER, theme TEXT, success INTEGER, ts INTEGER, hints INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS lessons_done (
    lesson_id TEXT PRIMARY KEY, ts INTEGER
);
"""


class Database:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or (app_dir() / "coach.db"))
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def close(self):
        with self._lock:
            self.conn.close()

    def execute(self, sql: str, params=()):
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------------ parties
    def game_exists(self, url: str) -> int | None:
        rows = self.query("SELECT id FROM games WHERE url=?", (url,))
        return rows[0]["id"] if rows else None

    def save_analysis(self, ga: GameAnalysis, *, url: str = "", source: str = "pgn", user_rating: int | None = None,
                      opp_rating: int | None = None, time_class: str = "", played_at: int | None = None,
                      user_result: str = "", summary: str = "") -> int:
        counts = ga.counts()
        if not url:
            url = "local:" + hashlib.sha1(ga.pgn.encode("utf-8")).hexdigest()[:16]
        with self._lock:
            old = self.game_exists(url)
            if old:
                self.delete_game(old)
            cur = self.conn.execute(
                """INSERT INTO games (source,url,pgn,white,black,user_color,result,user_result,user_rating,opp_rating,
                   time_class,played_at,analyzed_at,accuracy,blunders,mistakes,inaccuracies,misses,summary)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (source, url, ga.pgn, ga.white, ga.black, ga.user_color, ga.result, user_result, user_rating, opp_rating,
                 time_class, played_at or int(time.time()), int(time.time()), ga.accuracy(), counts["blunder"],
                 counts["mistake"], counts["inaccuracy"], counts["miss"], summary))
            gid = cur.lastrowid
            now = int(time.time())
            sev = {"inaccuracy": 1, "mistake": 2, "miss": 2, "blunder": 3}
            for m in ga.moves:
                self.conn.execute("INSERT INTO moves (game_id,ply,data,is_user,classification) VALUES (?,?,?,?,?)",
                                  (gid, m.ply, json.dumps(m.to_dict(), ensure_ascii=False), int(m.is_user), m.classification))
                if m.is_user:
                    for mo in m.motifs:
                        w = sev.get(m.classification, 0.5 if mo["side"] == "principle" else 0)
                        if w:
                            self.conn.execute(
                                "INSERT INTO motif_events (game_id,ply,theme,kind,side,severity,ts) VALUES (?,?,?,?,?,?,?)",
                                (gid, m.ply, mo["theme"], mo["kind"], mo["side"], w, played_at or now))
            self.conn.commit()
        return gid

    def delete_game(self, gid: int):
        with self._lock:
            for t in ("moves", "motif_events"):
                self.conn.execute(f"DELETE FROM {t} WHERE game_id=?", (gid,))
            self.conn.execute("DELETE FROM games WHERE id=?", (gid,))
            self.conn.commit()

    def games(self, limit: int = 200) -> list[sqlite3.Row]:
        return self.query("SELECT * FROM games ORDER BY played_at DESC LIMIT ?", (limit,))

    def game(self, gid: int) -> sqlite3.Row | None:
        rows = self.query("SELECT * FROM games WHERE id=?", (gid,))
        return rows[0] if rows else None

    def load_moves(self, gid: int) -> list[MoveAnalysis]:
        rows = self.query("SELECT data FROM moves WHERE game_id=? ORDER BY ply", (gid,))
        return [MoveAnalysis(**json.loads(r["data"])) for r in rows]

    def load_analysis(self, gid: int) -> GameAnalysis | None:
        g = self.game(gid)
        if not g:
            return None
        from .analysis import parse_pgn
        headers = dict(parse_pgn(g["pgn"]).headers)
        return GameAnalysis(g["white"], g["black"], g["result"], g["user_color"], self.load_moves(gid), headers, g["pgn"])

    def set_ai_explanation(self, gid: int, ply: int, text: str):
        self.execute("UPDATE moves SET ai_explanation=? WHERE game_id=? AND ply=?", (text, gid, ply))

    def ai_explanation(self, gid: int, ply: int) -> str | None:
        rows = self.query("SELECT ai_explanation FROM moves WHERE game_id=? AND ply=?", (gid, ply))
        return rows[0]["ai_explanation"] if rows else None

    def set_ai_review(self, gid: int, text: str):
        self.execute("UPDATE games SET ai_review=? WHERE id=?", (text, gid))

    # ------------------------------------------------------------------ exercices
    def add_exercise(self, fen: str, solution: str, theme: str, kind: str = "", source: str = "partie", game_id: int | None = None,
                     ply: int | None = None, title: str = "", hint: str = "", explanation: str = "") -> int | None:
        with self._lock:
            cur = self.conn.execute(
                """INSERT OR IGNORE INTO exercises (fen,solution,theme,kind,source,game_id,ply,title,hint,explanation,created)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (fen, solution, theme, kind, source, game_id, ply, title, hint, explanation, int(time.time())))
            self.conn.commit()
            return cur.lastrowid if cur.rowcount else None

    def exercises(self, theme: str | None = None) -> list[sqlite3.Row]:
        if theme:
            return self.query("SELECT * FROM exercises WHERE theme=?", (theme,))
        return self.query("SELECT * FROM exercises")

    def record_attempt(self, ex_id: int, theme: str, success: bool, hints: int = 0):
        now = int(time.time())
        with self._lock:
            row = self.conn.execute("SELECT streak FROM exercises WHERE id=?", (ex_id,)).fetchone()
            streak = (row["streak"] + 1) if (row and success) else 0
            # Répétition espacée : 1 jour, 3 jours, 7 jours, 21 jours... ; raté = à revoir tout de suite
            delay = [0, 1, 3, 7, 21, 60][min(streak, 5)] * 86400 if success else 600
            self.conn.execute(
                "UPDATE exercises SET attempts=attempts+1, successes=successes+?, streak=?, next_due=? WHERE id=?",
                (int(success), streak, now + delay, ex_id))
            self.conn.execute("INSERT INTO attempts (exercise_id,theme,success,ts,hints) VALUES (?,?,?,?,?)",
                              (ex_id, theme, int(success), now, hints))
            self.conn.commit()

    def mark_lesson(self, lesson_id: str):
        self.execute("INSERT OR REPLACE INTO lessons_done (lesson_id, ts) VALUES (?,?)", (lesson_id, int(time.time())))

    def lessons_done(self) -> set[str]:
        return {r["lesson_id"] for r in self.query("SELECT lesson_id FROM lessons_done")}
