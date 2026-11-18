"""Entraînement personnalisé : exercices tirés de TES parties + banque thématique.

- Chaque erreur importante d'une partie analysée devient un exercice « trouve mieux ».
- La banque (data/puzzles.json, générée et vérifiée par Stockfish) couvre les thèmes.
- La sélection privilégie les thèmes où tu fais le plus d'erreurs et utilise une
  répétition espacée (un exercice raté revient vite, un exercice réussi revient plus tard).
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path

import chess

from .chessutil import PIECE_FR, san_fr, win_percent
from .db import Database
from .explain import REFLEXES, describe_move_idea
from .motifs import THEMES
from .progress import weakest_themes

DATA = Path(__file__).resolve().parent / "data"

# Thèmes qui s'entraînent avec les exercices d'autres thèmes
THEME_POOLS = {
    "piece_en_prise": ["menaces", "capture_manquee"],
    "calcul": ["fourchette", "clouage", "enfilade", "mat", "capture_manquee"],
    "securite_roi": ["mat", "securite_roi"],
    "developpement": ["ouverture"],
    "centre": ["ouverture"],
    "ouverture": ["ouverture"],
}

THEME_HINTS = {
    "mat": "Il y a un mat ! Regarde d'abord tous les échecs possibles.",
    "fourchette": "Cherche un coup qui attaque deux choses en même temps.",
    "clouage": "Une pièce adverse est devant une pièce plus importante… cloue-la !",
    "enfilade": "Attaque la grosse pièce : quand elle bougera, celle de derrière sera à toi.",
    "capture_manquee": "Une pièce adverse n'est pas assez protégée. Compte attaquants et défenseurs.",
    "menaces": "Ton adversaire menace quelque chose. Quoi ? Trouve le coup qui règle le problème.",
    "finale": "En finale : roi actif, pion passé, et pense à l'opposition des rois.",
    "ouverture": "Centre, développement, roque : quel coup respecte ces principes ?",
    "securite_roi": "Ton roi est-il en sécurité ? Pense au roque et aux échecs adverses.",
}

# Quiz d'ouverture : plusieurs bonnes réponses possibles (principes)
OPENING_QUIZ = [
    {"fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", "good": ["e2e4", "d2d4", "g1f3", "c2c4"],
     "title": "Premier coup : prends le centre !",
     "why": "Un pion central (e4 ou d4) libère tes fous et ta dame et contrôle le centre."},
    {"fen": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", "good": ["g1f3", "b1c3", "f1c4", "d2d4"],
     "title": "Développe en attaquant",
     "why": "Cf3 sort une pièce ET attaque le pion e5 : un coup qui fait deux choses."},
    {"fen": "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3", "good": ["g8f6", "f8c5", "f8e7"],
     "title": "À ton tour de te développer",
     "why": "Sors ta pièce mineure côté roi (Cf6 ou Fc5) pour pouvoir roquer vite."},
    {"fen": "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK2R w KQkq - 1 5", "good": ["e1g1", "b1c3", "c2c3"],
     "title": "Le bon moment pour…",
     "why": "Ton roi est prêt à roquer : O-O met le roi à l'abri et active la tour."},
    {"fen": "rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", "good": ["f3e5", "b1c3", "d2d4", "f1c4"],
     "title": "Pense au centre",
     "why": "Plusieurs coups sont bons : Cxe5 prend un pion, Cc3 et d4 développent ou ouvrent le centre."},
    {"fen": "rnbqkbnr/ppp2ppp/8/3pp3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3", "good": ["e4d5", "f3e5", "b1c3"],
     "title": "Une capture ?",
     "why": "Fais le tour des captures : exd5 et Cxe5 gagnent chacun un pion central."},
    {"fen": "rnb1kbnr/pppp1ppp/8/4p3/4P2q/2N5/PPPP1PPP/R1BQKBNR w KQkq - 2 3", "good": ["g1f3", "d2d3", "g2g3", "d1e2", "d1f3"],
     "title": "La dame adverse sort trop tôt",
     "why": "Développe en l'attaquant : Cf3 sort une pièce et chasse la dame, tu gagnes du temps."},
    {"fen": "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 4 4", "good": ["d8e7", "g7g6"],
     "title": "Attention au Coup du Berger !",
     "why": "Dh5 et Fc4 visent f7 : mat en un coup sur Dxf7 ! Il faut défendre f7 (De7) ou chasser la dame (g6)."},
]


@dataclass
class Exercise:
    id: int
    fen: str
    solution: list[str]
    theme: str
    kind: str
    source: str
    title: str
    hint: str
    explanation: str
    game_id: int | None = None
    ply: int | None = None
    good: list[str] | None = None   # quiz : plusieurs bonnes réponses

    @property
    def board(self) -> chess.Board:
        return chess.Board(self.fen)

    @property
    def side(self) -> str:
        return "Blancs" if self.board.turn == chess.WHITE else "Noirs"


def _row_to_ex(r) -> Exercise:
    sol = json.loads(r["solution"]) if r["solution"].startswith("[") else [r["solution"]]
    good = None
    if r["kind"] == "quiz":
        good = json.loads(r["explanation"].split("\n", 1)[0]) if r["explanation"].startswith("[") else None
    return Exercise(r["id"], r["fen"], sol, r["theme"], r["kind"], r["source"], r["title"] or "", r["hint"] or "",
                    r["explanation"] or "", r["game_id"], r["ply"], good)


def import_bank(db: Database) -> int:
    """Copie la banque d'exercices dans la base (une seule fois)."""
    n = 0
    path = DATA / "puzzles.json"
    if path.exists():
        for p in json.loads(path.read_text(encoding="utf-8")):
            title = _bank_title(p)
            if db.add_exercise(p["fen"], json.dumps(p["solution"]), p["theme"], p.get("kind", ""), "banque",
                               title=title, hint=THEME_HINTS.get(p["theme"], "")):
                n += 1
    for q in OPENING_QUIZ:
        expl = json.dumps(q["good"]) + "\n" + q["why"]
        if db.add_exercise(q["fen"], json.dumps([q["good"][0]]), "ouverture", "quiz", "banque", title=q["title"],
                           hint=THEME_HINTS["ouverture"], explanation=expl):
            n += 1
    return n


def _bank_title(p: dict) -> str:
    side = "Blancs" if chess.Board(p["fen"]).turn == chess.WHITE else "Noirs"
    k = p.get("kind", "")
    if p["theme"] == "mat":
        if k == "back_rank":
            return f"Mat du couloir — les {side} jouent"
        n = k.rsplit("_", 1)[-1] if k.startswith("mate_in") else "?"
        return f"Mat en {n} — les {side} jouent"
    return f"{THEMES.get(p['theme'], p['theme'])} — les {side} jouent"


def exercises_from_game(db: Database, game_id: int) -> int:
    """Transforme les erreurs importantes d'une partie en exercices personnels."""
    from .explain import _main_theme
    n = 0
    g = db.game(game_id)
    opp = (g["black"] if g["user_color"] == "white" else g["white"]) if g else "?"
    for m in db.load_moves(game_id):
        if not m.is_user or m.classification not in ("mistake", "miss", "blunder") or not m.best_uci:
            continue
        theme = _main_theme(m)
        sol = [m.best_uci]
        if m.mate_before is not None:
            # mat : on garde toute la séquence
            b = chess.Board(m.fen_before)
            sol = []
            for san in m.best_pv_san[:5]:
                try:
                    mv = b.parse_san(san)
                except ValueError:
                    break
                sol.append(mv.uci())
                b.push(mv)
            sol = sol[: len(sol) if len(sol) % 2 == 1 else len(sol) - 1] or [m.best_uci]
            if not b.is_checkmate():
                sol = [m.best_uci]
        title = f"Ta partie contre {opp} — coup {m.move_number} : trouve mieux que {san_fr(m.san)}"
        expl = f"Dans la partie, tu as joué {san_fr(m.san)} ({m.classification}). Le meilleur coup était {san_fr(m.best_san)}."
        if db.add_exercise(m.fen_before, json.dumps(sol), theme, m.classification, "partie", game_id, m.ply, title,
                           THEME_HINTS.get(theme, "Échecs, captures, menaces : fais le tour !"), expl):
            n += 1
    return n


def select_exercises(db: Database, count: int = 10, theme: str | None = None, seed: int | None = None) -> list[Exercise]:
    """Choisit une série d'exercices adaptée : thèmes faibles + révisions dues + exercices perso."""
    rng = random.Random(seed)
    now = int(time.time())
    rows = db.query("SELECT * FROM exercises")
    if theme:
        pool_themes = set(THEME_POOLS.get(theme, [theme])) | {theme}
        rows = [r for r in rows if r["theme"] in pool_themes]
    else:
        weak = weakest_themes(db, 3)
        focus = set()
        for t in weak:
            focus |= set(THEME_POOLS.get(t, [t])) | {t}

    def score(r) -> float:
        s = rng.random()
        if r["next_due"] and r["next_due"] > now:
            s -= 5  # pas encore à réviser
        if r["source"] == "partie":
            s += 2.0  # tes propres positions d'abord
        if r["attempts"] == 0:
            s += 0.8
        elif r["successes"] < r["attempts"]:
            s += 1.2  # déjà raté : à retravailler
        if not theme and r["theme"] in focus:
            s += 1.5
        return s

    rows = sorted(rows, key=score, reverse=True)
    out = [_row_to_ex(r) for r in rows[:count]]
    rng.shuffle(out)
    return out


def get_exercise(db: Database, ex_id: int) -> Exercise | None:
    rows = db.query("SELECT * FROM exercises WHERE id=?", (ex_id,))
    return _row_to_ex(rows[0]) if rows else None


@dataclass
class CheckResult:
    status: str        # "correct" (étape suivante / fini), "solved", "wrong"
    message: str
    reply: chess.Move | None = None  # coup de l'adversaire à jouer automatiquement


def check_move(ex: Exercise, board: chess.Board, move: chess.Move, step: int, engine=None) -> CheckResult:
    """Vérifie le coup proposé à l'étape `step` (0 = premier coup du joueur)."""
    expected = ex.solution[step] if step < len(ex.solution) else None
    b = board.copy()
    b.push(move)
    ok = move.uci() == expected
    if not ok and b.is_checkmate():
        ok = True  # n'importe quel mat est accepté
    if not ok and ex.good and step == 0 and move.uci() in ex.good:
        ok = True
    if not ok and engine is not None and expected and ex.theme != "mat":
        # Coup alternatif aussi fort que la solution ?
        try:
            exp_mv = chess.Move.from_uci(expected)
            v_exp = engine.eval_move(board, exp_mv, depth=12, time=0.4)
            v_mine = engine.eval_move(board, move, depth=12, time=0.4)
            if win_percent(v_exp) - win_percent(v_mine) < 3 and v_mine > -100:
                ok = True
        except Exception:
            pass
    if not ok:
        return CheckResult("wrong", _wrong_feedback(board, move))
    nxt = step + 1
    if b.is_checkmate() or nxt >= len(ex.solution) or move.uci() != expected:
        return CheckResult("solved", "Bravo, c'est la bonne idée !")
    reply = chess.Move.from_uci(ex.solution[nxt])
    return CheckResult("correct", "Bien vu ! Continue…", reply)


def _wrong_feedback(board: chess.Board, move: chess.Move) -> str:
    """Explique simplement pourquoi le coup proposé ne marche pas."""
    from .chessutil import hanging_pieces
    b = board.copy()
    b.push(move)
    me = board.turn
    for mv in b.legal_moves:
        bb = b.copy()
        bb.push(mv)
        if bb.is_checkmate():
            return f"Attention : après ce coup, ton adversaire a un mat avec {san_fr(b.san(mv))} !"
    hang = hanging_pieces(b, me, 2)
    if hang:
        sq, g, cap = hang[0]
        p = b.piece_at(sq)
        return (f"Pas tout à fait : ton {PIECE_FR[p.piece_type]} en {chess.square_name(sq)} peut être pris "
                f"({san_fr(b.san(cap))}). Cherche encore !")
    return "Ce n'est pas le meilleur coup ici. Refais le tour : échecs, captures, menaces."


def solution_explanation(ex: Exercise) -> str:
    b = ex.board
    mv = chess.Move.from_uci(ex.solution[0])
    san = san_fr(b.san(mv))
    ideas = describe_move_idea(b, mv)
    txt = f"La solution : <b>{san}</b> — " + ", ".join(ideas[:3]) + "."
    if len(ex.solution) > 1:
        bb = b.copy()
        sans = []
        for u in ex.solution:
            m = chess.Move.from_uci(u)
            if m not in bb.legal_moves:
                break
            sans.append(san_fr(bb.san(m)))
            bb.push(m)
        txt += " Séquence complète : " + " ".join(sans) + "."
    if ex.kind == "quiz" and ex.explanation:
        txt = ex.explanation.split("\n", 1)[-1] + " " + txt
    elif ex.explanation:
        txt = ex.explanation + " " + txt
    reflex = REFLEXES.get(ex.theme)
    if reflex:
        txt += f"<br><br><b>À retenir :</b> {reflex}"
    return txt
