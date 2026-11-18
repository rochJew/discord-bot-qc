"""Génère la banque d'exercices thématiques (coach/data/puzzles.json).

Principe : on joue des parties semi-aléatoires (coups « humains » de faible niveau),
et on garde les positions où le camp au trait a UN coup nettement meilleur que
tous les autres (écart vérifié par Stockfish en multipv). Le thème est déterminé
par les mêmes détecteurs que ceux utilisés pour analyser les parties.

Usage : python tools/generate_puzzles.py [stockfish_path] [minutes]
"""
import json
import random
import sys
import time
from pathlib import Path

import chess

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from coach.chessutil import hanging_pieces, see  # noqa: E402
from coach.config import find_stockfish  # noqa: E402
from coach.engine import Engine  # noqa: E402
from coach.motifs import _is_back_rank_mate, fork_targets, line_motif  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "coach" / "data" / "puzzles.json"
TARGET = {"mat": 30, "fourchette": 25, "clouage": 15, "enfilade": 10, "capture_manquee": 25, "menaces": 15, "finale": 15}


def semi_random_game(engine, rng):
    b = chess.Board()
    plies = rng.randint(8, 60)
    for _ in range(plies):
        if b.is_game_over():
            return None
        moves = list(b.legal_moves)
        if rng.random() < 0.35:
            mv = rng.choice(moves)  # coup « débutant » : crée des fautes tactiques
        else:
            lines = engine.analyse(b, depth=6, time=0.05, multipv=4)
            cands = [l.best for l in lines if l.best]
            mv = rng.choice(cands) if cands else rng.choice(moves)
        b.push(mv)
    return b


def classify(b, line1, line2):
    best = line1.best
    me = b.turn
    if line1.mate is not None and 0 < line1.mate <= 3:
        if line2 is not None and line2.mate is not None and 0 < line2.mate <= line1.mate + 1:
            return None  # plusieurs mats : pas unique
        kind = "back_rank" if _is_back_rank_mate(b, line1.pv[: 2 * line1.mate - 1]) else f"mate_in_{line1.mate}"
        return "mat", kind
    if line1.mate is not None:
        return None
    gap = line1.score_cp - (line2.score_cp if line2 else -10000)
    if gap < 250 or line1.score_cp < 150:
        return None
    if fork_targets(b, best):
        return "fourchette", "fork"
    lm = line_motif(b, best)
    if lm:
        return lm[0], lm[0]
    if b.is_capture(best) and see(b, best) >= 2:
        return "capture_manquee", "free_piece"
    # Une de mes pièces est attaquée et le coup la sauve / crée une contre-menace
    hang = hanging_pieces(b, me, 2)
    if hang:
        after = b.copy(); after.push(best)
        if not hanging_pieces(after, me, 2):
            return "menaces", "save_piece"
    # Matériel gagné au bout de la ligne
    return None


def endgame_positions(rng):
    """Finales simples roi+pions générées aléatoirement."""
    for _ in range(200):
        b = chess.Board(None)
        sqs = rng.sample(range(8, 56), 5)
        b.set_piece_at(rng.choice(range(0, 64)), chess.Piece(chess.KING, chess.WHITE))
        b.set_piece_at(rng.choice(range(0, 64)), chess.Piece(chess.KING, chess.BLACK))
        for i, s in enumerate(sqs[:rng.randint(1, 4)]):
            b.set_piece_at(s, chess.Piece(chess.PAWN, chess.WHITE if i % 2 == 0 else chess.BLACK))
        b.turn = rng.choice([chess.WHITE, chess.BLACK])
        if b.is_valid() and not b.is_game_over():
            yield b


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_stockfish()
    minutes = float(sys.argv[2]) if len(sys.argv) > 2 else 8
    rng = random.Random(1234)
    engine = Engine(path, threads=2)
    found = {k: [] for k in TARGET}
    seen = set()
    if OUT.exists():
        for p in json.loads(OUT.read_text(encoding="utf-8")):
            found.setdefault(p["theme"], []).append(p)
            seen.add(chess.Board(p["fen"]).board_fen())
    rng.seed(int(time.time()))
    deadline = time.time() + minutes * 60
    while time.time() < deadline and any(len(found[k]) < v for k, v in TARGET.items()):
        b = semi_random_game(engine, rng)
        if b is None:
            continue
        key = b.board_fen()
        if key in seen:
            continue
        seen.add(key)
        lines = engine.analyse(b, depth=14, time=0.4, multipv=2)
        if not lines or not lines[0].best:
            continue
        res = classify(b, lines[0], lines[1] if len(lines) > 1 else None)
        if not res:
            continue
        theme, kind = res
        if len(found.get(theme, [])) >= TARGET.get(theme, 0):
            continue
        n = 2 * lines[0].mate - 1 if theme == "mat" else 1
        sol = [m.uci() for m in lines[0].pv[:max(1, n)]]
        found[theme].append({"fen": b.fen(), "solution": sol, "theme": theme, "kind": kind})
        print(theme, kind, b.fen(), sol, flush=True)
    # Pièces en prise : positions où l'adversaire vient de laisser une pièce -> mêmes que capture_manquee,
    # côté défense on génère « sauve ta pièce » (menaces). Finales :
    for b in endgame_positions(rng):
        if len(found["finale"]) >= TARGET["finale"]:
            break
        lines = engine.analyse(b, depth=20, time=0.5, multipv=2)
        if len(lines) < 2 or not lines[0].best:
            continue
        l1, l2 = lines
        win1 = l1.score_cp >= 300
        draw_or_loss2 = l2.score_cp <= 80
        if win1 and draw_or_loss2:
            found["finale"].append({"fen": b.fen(), "solution": [l1.best.uci()], "theme": "finale", "kind": "pawn_endgame"})
            print("finale", b.fen(), l1.best, flush=True)
    engine.close()
    allp = [p for v in found.values() for p in v]
    OUT.write_text(json.dumps(allp, indent=1), encoding="utf-8")
    print({k: len(v) for k, v in found.items()})


if __name__ == "__main__":
    main()
