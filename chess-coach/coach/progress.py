"""Suivi de progression : statistiques, maîtrise des notions, Elo estimé."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .db import Database
from .motifs import THEMES

# Correspondance approximative précision moyenne -> niveau Elo Chess.com (rapide).
# Heuristique calibrée sur les ordres de grandeur publics (≈50-55% à 400, ≈70% à 1000).
ACC_TO_ELO = [(40, 150), (50, 350), (55, 450), (60, 600), (65, 750), (70, 950), (75, 1150), (80, 1400), (85, 1700), (90, 2000)]


def _interp(x: float, table) -> float:
    if x <= table[0][0]:
        return table[0][1]
    for (x0, y0), (x1, y1) in zip(table, table[1:]):
        if x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return table[-1][1]


def estimate_elo(accuracy: float, blunders_per_game: float) -> int:
    """Elo de performance estimé à partir de la précision et du nombre de gaffes."""
    base = _interp(accuracy, ACC_TO_ELO)
    # À bas niveau, ce sont les gaffes qui décident : on plafonne selon leur fréquence
    # (≈3-4 gaffes/partie vers 400 Elo, ≈1-2 vers 1000).
    base = min(base, 1500 - 280 * blunders_per_game)
    return int(round(max(100, min(2500, base)) / 10) * 10)


@dataclass
class ThemeStatus:
    theme: str
    label: str
    errors: float          # poids d'erreurs cumulé (récent)
    errors_per_game: float
    attempts: int
    success_rate: float | None
    mastery: int           # 0-100
    status: str            # "maîtrisé" / "en progrès" / "à travailler" / "à découvrir"


@dataclass
class Progress:
    games: int
    avg_accuracy: float
    recent_accuracy: float
    blunders_per_game: float
    estimated_elo: int
    chesscom_rating: int | None
    history: list[dict] = field(default_factory=list)   # par partie : date, accuracy, blunders, rating
    themes: list[ThemeStatus] = field(default_factory=list)
    top_errors: list[tuple[str, int]] = field(default_factory=list)
    exercises_done: int = 0
    exercises_success: float = 0.0

    @property
    def weaknesses(self) -> list[ThemeStatus]:
        ws = [t for t in self.themes if t.status in ("à travailler", "en progrès") and (t.errors > 0 or t.attempts)]
        return sorted(ws, key=lambda t: t.mastery)[:4]

    @property
    def strengths(self) -> list[ThemeStatus]:
        return sorted([t for t in self.themes if t.status == "maîtrisé"], key=lambda t: -t.mastery)[:4]


def compute_progress(db: Database, recent: int = 10) -> Progress:
    games = db.query("SELECT * FROM games ORDER BY played_at ASC")
    n = len(games)
    history = [
        {"id": g["id"], "date": g["played_at"], "accuracy": g["accuracy"] or 0, "blunders": g["blunders"] or 0,
         "mistakes": g["mistakes"] or 0, "rating": g["user_rating"], "result": g["user_result"]}
        for g in games
    ]
    avg_acc = sum(h["accuracy"] for h in history) / n if n else 0.0
    last = history[-recent:]
    rec_acc = sum(h["accuracy"] for h in last) / len(last) if last else 0.0
    bpg = sum(h["blunders"] for h in last) / len(last) if last else 0.0
    est = estimate_elo(rec_acc, bpg) if last else 0
    rating = next((h["rating"] for h in reversed(history) if h["rating"]), None)

    # Erreurs par thème (pondérées : les parties récentes comptent plus)
    game_ids = [g["id"] for g in games]
    recency = {gid: 0.5 + 0.5 * (i + 1) / max(1, n) for i, gid in enumerate(game_ids)}
    weight = defaultdict(float)
    raw_count = defaultdict(int)
    for r in db.query("SELECT game_id, theme, severity FROM motif_events"):
        weight[r["theme"]] += r["severity"] * recency.get(r["game_id"], 1.0)
        raw_count[r["theme"]] += 1
    att = defaultdict(lambda: [0, 0])
    for r in db.query("SELECT theme, success FROM attempts ORDER BY ts DESC LIMIT 400"):
        a = att[r["theme"]]
        if a[0] < 25:  # 25 dernières tentatives par thème
            a[0] += 1
            a[1] += r["success"]
    themes = []
    for theme, label in THEMES.items():
        e = weight.get(theme, 0.0)
        epg = e / n if n else 0.0
        attempts, succ = att[theme] if theme in att else (0, 0)
        sr = succ / attempts if attempts else None
        # Score de maîtrise : 100 = aucune erreur et exercices réussis
        game_score = max(0.0, 100 - epg * 60) if n else None
        if game_score is None and sr is None:
            mastery, status = 0, "à découvrir"
        else:
            parts = []
            if game_score is not None:
                parts.append((game_score, 0.6 if sr is not None else 1.0))
            if sr is not None:
                parts.append((sr * 100, 0.4 if game_score is not None else 1.0))
            mastery = int(sum(v * w for v, w in parts) / sum(w for _, w in parts))
            if attempts < 3 and raw_count.get(theme, 0) == 0 and n < 3:
                status = "à découvrir"
            elif mastery >= 80:
                status = "maîtrisé"
            elif mastery >= 55:
                status = "en progrès"
            else:
                status = "à travailler"
        themes.append(ThemeStatus(theme, label, round(e, 1), round(epg, 2), attempts, sr, mastery, status))
    top = sorted(((THEMES[t], c) for t, c in raw_count.items() if t in THEMES), key=lambda x: -x[1])[:6]
    ex = db.query("SELECT COUNT(*) AS n, AVG(success) AS s FROM attempts")[0]
    return Progress(n, round(avg_acc, 1), round(rec_acc, 1), round(bpg, 2), est, rating, history, themes, top,
                    ex["n"] or 0, round((ex["s"] or 0) * 100, 1))


def weakest_themes(db: Database, k: int = 3) -> list[str]:
    p = compute_progress(db)
    ws = [t.theme for t in p.weaknesses]
    if not ws:
        # Pas encore de données : le programme de base pour un joueur ~400
        ws = ["piece_en_prise", "menaces", "fourchette", "mat"]
    return ws[:k]


def elo_goal_text(current: int, target: int = 1000) -> str:
    gap = target - current
    if gap <= 0:
        return "Objectif atteint ! On vise plus haut ?"
    if current < 600:
        return ("Prochaine étape : 600. Pour y arriver, une seule priorité : ne plus laisser de pièces en prise "
                "et prendre celles que l'adversaire laisse.")
    if current < 800:
        return ("Prochaine étape : 800. Travaille les fourchettes, les clouages et les mats simples, et roque toujours tôt.")
    return ("Dernière ligne droite vers 1000 : repère les menaces adverses à chaque coup et apprends à construire un plan.")
