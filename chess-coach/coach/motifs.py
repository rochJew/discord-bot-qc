"""Détection des motifs tactiques et stratégiques derrière une erreur.

Chaque motif a un `theme` (catégorie suivie dans la progression) et un `kind`
(précision sur ce qui s'est passé) ainsi que des faits concrets (cases, pièces)
utilisés pour rédiger les explications du coach.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import chess

from .chessutil import PIECE_FR, VALUES, hanging_pieces, material_balance, see

THEMES = {
    "piece_en_prise": "Pièces laissées en prise",
    "capture_manquee": "Matériel gratuit non pris",
    "fourchette": "Fourchettes et attaques doubles",
    "clouage": "Clouages",
    "enfilade": "Enfilades",
    "mat": "Mats (manqués ou subis)",
    "menaces": "Repérer les menaces adverses",
    "developpement": "Développement des pièces",
    "centre": "Contrôle du centre",
    "securite_roi": "Sécurité du roi",
    "ouverture": "Principes d'ouverture",
    "finale": "Finales",
    "calcul": "Calcul et tactique",
}


@dataclass
class Motif:
    theme: str
    kind: str
    side: str                 # "allowed" (on a permis) / "missed" (on a raté) / "principle"
    squares: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


DIRS_ROOK = [(1, 0), (-1, 0), (0, 1), (0, -1)]
DIRS_BISHOP = [(1, 1), (1, -1), (-1, 1), (-1, -1)]


def _rays(piece_type: int):
    if piece_type == chess.ROOK:
        return DIRS_ROOK
    if piece_type == chess.BISHOP:
        return DIRS_BISHOP
    if piece_type == chess.QUEEN:
        return DIRS_ROOK + DIRS_BISHOP
    return []


def _walk(board: chess.Board, sq: chess.Square, d):
    f, r = chess.square_file(sq), chess.square_rank(sq)
    while True:
        f += d[0]
        r += d[1]
        if not (0 <= f < 8 and 0 <= r < 8):
            return
        yield chess.square(f, r)


def _is_defended(board: chess.Board, sq: chess.Square, color: chess.Color) -> bool:
    return bool(board.attackers(color, sq))


def _piece_safe(board: chess.Board, sq: chess.Square) -> bool:
    """La pièce sur `sq` ne peut pas être capturée avec profit par le camp au trait."""
    for mv in board.legal_moves:
        if mv.to_square == sq and see(board, mv) > 0:
            return False
    return True


def fork_targets(board: chess.Board, move: chess.Move) -> list[chess.Square]:
    """Si `move` crée une fourchette, renvoie les cases attaquées (sinon [])."""
    if move not in board.legal_moves:
        return []
    mover = board.piece_at(move.from_square)
    b = board.copy(stack=False)
    b.push(move)
    sq = move.to_square
    piece = b.piece_at(sq)
    if piece is None:
        return []
    enemy = not piece.color
    if not _piece_safe(b, sq) and not b.is_check():
        return []
    attacker_val = VALUES[piece.piece_type]
    targets = []
    for t in b.attacks(sq):
        tp = b.piece_at(t)
        if tp is None or tp.color != enemy:
            continue
        if tp.piece_type == chess.KING or VALUES[tp.piece_type] > attacker_val or not _is_defended(b, t, enemy):
            targets.append(t)
    if len(targets) < 2 or all(b.piece_type_at(t) == chess.PAWN for t in targets) or \
            sum(1 for t in targets if b.piece_type_at(t) != chess.PAWN) == 0:
        return []
    if sum(1 for t in targets if b.piece_type_at(t) == chess.PAWN) and sum(1 for t in targets if b.piece_type_at(t) != chess.PAWN) < 2:
        # Une pièce + un pion : on ne garde que si le pion protège quelque chose d'important (souvent le cas) -> attaque double
        pass
    # Si le roi est en échec mais que l'attaquant peut être pris, ce n'est pas une vraie fourchette
    if b.is_check() and not _piece_safe(b, sq):
        return []
    _ = mover
    return targets


def line_motif(board: chess.Board, move: chess.Move):
    """Détecte un clouage ou une enfilade créé(e) par une pièce à longue portée.

    Retourne (kind, [case_attaquant, case_devant, case_derrière]) ou None.
    """
    if move not in board.legal_moves:
        return None
    b = board.copy(stack=False)
    b.push(move)
    sq = move.to_square
    piece = b.piece_at(sq)
    if piece is None or piece.piece_type not in (chess.BISHOP, chess.ROOK, chess.QUEEN):
        return None
    if not _piece_safe(b, sq) and not b.is_check():
        return None
    enemy = not piece.color
    for d in _rays(piece.piece_type):
        first = second = None
        for s in _walk(b, sq, d):
            p = b.piece_at(s)
            if p is None:
                continue
            if first is None:
                if p.color != enemy:
                    break
                first = s
            else:
                if p.color == enemy:
                    second = s
                break
        if first is None or second is None:
            continue
        a, c = b.piece_at(first), b.piece_at(second)
        va, vc = VALUES[a.piece_type], VALUES[c.piece_type]
        if a.piece_type != chess.KING and vc > va and (c.piece_type == chess.KING or vc > VALUES[piece.piece_type] or not _is_defended(b, second, enemy)):
            if a.piece_type != chess.PAWN or c.piece_type == chess.KING:
                return ("clouage", [chess.square_name(sq), chess.square_name(first), chess.square_name(second)])
        if (a.piece_type == chess.KING or va > vc) and c.piece_type != chess.PAWN and (VALUES[c.piece_type] >= VALUES[piece.piece_type] or not _is_defended(b, second, enemy)):
            return ("enfilade", [chess.square_name(sq), chess.square_name(first), chess.square_name(second)])
    return None


def _play(board: chess.Board, pv: list[chess.Move], n: int) -> chess.Board:
    b = board.copy(stack=False)
    for mv in pv[:n]:
        if mv not in b.legal_moves:
            break
        b.push(mv)
    return b


def _captures_along(board: chess.Board, line: list[chess.Move], who: chess.Color) -> list[str]:
    """Liste des pièces capturées par `who` le long d'une ligne (ex : ['Dxg2 (pion)'])."""
    b = board.copy(stack=False)
    out = []
    for mv in line:
        if mv not in b.legal_moves:
            break
        if b.turn == who and b.is_capture(mv):
            cap = b.piece_at(mv.to_square)
            name = PIECE_FR[cap.piece_type] if cap else "pion"
            out.append(f"{b.san(mv)} ({name})")
        b.push(mv)
    return out


def _is_back_rank_mate(board: chess.Board, pv: list[chess.Move]) -> bool:
    b = board.copy(stack=False)
    for mv in pv:
        if mv not in b.legal_moves:
            return False
        b.push(mv)
    if not b.is_checkmate():
        return False
    king = b.king(b.turn)
    if king is None:
        return False
    rank = chess.square_rank(king)
    if rank not in (0, 7):
        return False
    last = b.peek()
    return chess.square_rank(last.to_square) == rank


def _threat_before(board: chess.Board, mover: chess.Color):
    """Ce que l'adversaire menaçait AVANT notre coup (s'il pouvait rejouer)."""
    return hanging_pieces(board, mover, min_gain=2)


def detect_motifs(pos: chess.Board, played: chess.Move, best: chess.Move, before_line, after_line, cls: str) -> list[Motif]:
    mover = pos.turn
    after = pos.copy()
    after.push(played)
    motifs: list[Motif] = []
    is_error = cls in ("inaccuracy", "mistake", "miss", "blunder")
    reply = after_line.pv[0] if after_line.pv else None

    if is_error:
        # ---- Ce que notre coup a permis -------------------------------------------------
        if after_line.mate is not None and after_line.mate > 0:
            kind = "allowed_back_rank_mate" if _is_back_rank_mate(after, after_line.pv) else "allowed_mate"
            motifs.append(Motif("mat", kind, "allowed", [], {"mate_in": after_line.mate}))
            motifs.append(Motif("securite_roi", "king_exposed", "allowed"))

        mate_allowed = any(m.theme == "mat" for m in motifs)
        hanging_now = [] if mate_allowed else hanging_pieces(after, mover, 2)
        hanging_before = {sq for sq, _, _ in _threat_before(pos, mover)}
        for sq, gain, cap in hanging_now[:1]:
            p = after.piece_at(sq)
            if p is None:
                continue
            facts = {"piece": PIECE_FR[p.piece_type], "square": chess.square_name(sq), "gain": gain,
                     "capture": after.san(cap), "attacker": chess.square_name(cap.from_square)}
            if sq == played.to_square:
                motifs.append(Motif("piece_en_prise", "moved_piece_hanging", "allowed", [chess.square_name(sq)], facts))
            elif sq in hanging_before or (played.from_square != sq and pos.piece_at(sq) and sq in {s for s, _, _ in hanging_pieces(pos, mover, 2)}):
                motifs.append(Motif("menaces", "ignored_threat", "allowed", [chess.square_name(sq)], facts))
            else:
                motifs.append(Motif("piece_en_prise", "left_hanging", "allowed", [chess.square_name(sq)], facts))

        if reply is not None and not mate_allowed:
            tgts = fork_targets(after, reply)
            if tgts:
                p = after.piece_at(reply.from_square)
                motifs.append(Motif("fourchette", "allowed_fork", "allowed",
                                    [chess.square_name(reply.to_square)] + [chess.square_name(t) for t in tgts],
                                    {"piece": PIECE_FR[p.piece_type], "move": after.san(reply),
                                     "targets": [PIECE_FR[after.piece_at(t).piece_type] for t in tgts]}))
            lm = line_motif(after, reply)
            if lm:
                motifs.append(Motif(lm[0], "allowed_" + ("pin" if lm[0] == "clouage" else "skewer"), "allowed", lm[1],
                                    {"move": after.san(reply), "front": PIECE_FR[after.piece_at(chess.parse_square(lm[1][1])).piece_type],
                                     "back": PIECE_FR[after.piece_at(chess.parse_square(lm[1][2])).piece_type]}))
            # Fourchette au 2e coup de la ligne adverse (ex : échange puis fourchette)
            if len(after_line.pv) >= 3 and not tgts:
                b2 = _play(after, after_line.pv, 2)
                mv3 = after_line.pv[2]
                tg2 = fork_targets(b2, mv3) if mv3 in b2.legal_moves else []
                if tg2:
                    p = b2.piece_at(mv3.from_square)
                    motifs.append(Motif("fourchette", "allowed_fork", "allowed",
                                        [chess.square_name(mv3.to_square)] + [chess.square_name(t) for t in tg2],
                                        {"piece": PIECE_FR[p.piece_type], "move": b2.san(mv3), "delayed": True,
                                         "targets": [PIECE_FR[b2.piece_at(t).piece_type] for t in tg2]}))

        # ---- Ce que nous avons raté -------------------------------------------------------
        if best != played and best in pos.legal_moves:
            if before_line.mate is not None and before_line.mate > 0:
                kind = "missed_back_rank_mate" if _is_back_rank_mate(pos, before_line.pv) else "missed_mate"
                motifs.append(Motif("mat", kind, "missed", [], {"mate_in": before_line.mate, "move": pos.san(best)}))
            if pos.is_capture(best):
                g = see(pos, best)
                if g >= 2:
                    cap = pos.piece_at(best.to_square)
                    motifs.append(Motif("capture_manquee", "missed_free_piece", "missed", [chess.square_name(best.to_square)],
                                        {"piece": PIECE_FR[cap.piece_type] if cap else "pion", "move": pos.san(best), "gain": g}))
            tgts = fork_targets(pos, best)
            if tgts:
                p = pos.piece_at(best.from_square)
                motifs.append(Motif("fourchette", "missed_fork", "missed",
                                    [chess.square_name(best.to_square)] + [chess.square_name(t) for t in tgts],
                                    {"piece": PIECE_FR[p.piece_type], "move": pos.san(best),
                                     "targets": [PIECE_FR[pos.piece_at(t).piece_type] for t in tgts]}))
            lm = line_motif(pos, best)
            if lm:
                motifs.append(Motif(lm[0], "missed_" + ("pin" if lm[0] == "clouage" else "skewer"), "missed", lm[1],
                                    {"move": pos.san(best), "front": PIECE_FR[pos.piece_at(chess.parse_square(lm[1][1])).piece_type],
                                     "back": PIECE_FR[pos.piece_at(chess.parse_square(lm[1][2])).piece_type]}))
            # Promotion manquée
            bp = pos.piece_at(best.from_square)
            if bp and bp.piece_type == chess.PAWN and (best.promotion or chess.square_rank(best.to_square) == (6 if mover == chess.WHITE else 1)):
                motifs.append(Motif("finale", "missed_promotion", "missed", [chess.square_name(best.to_square)], {"move": pos.san(best)}))

        # Bilan matériel des deux lignes
        start = material_balance(pos, mover)
        best_mat = material_balance(_play(pos, before_line.pv, 10), mover) - start
        played_line = [played] + list(after_line.pv)
        played_mat = material_balance(_play(pos, played_line, 11), mover) - start
        lost = _captures_along(pos, played_line[:11], not mover)
        if best_mat - played_mat >= 2 and not any(m.theme in ("piece_en_prise", "capture_manquee", "fourchette", "clouage", "enfilade", "menaces", "mat") for m in motifs):
            motifs.append(Motif("calcul", "material_swing", "allowed", [], {"best_mat": best_mat, "played_mat": played_mat, "lost": lost}))

    # ---- Principes (ouverture / roi / centre / finale) --------------------------------
    motifs.extend(_principles(pos, played, best, is_error))

    if is_error and not any(m.side in ("allowed", "missed") for m in motifs):
        from .chessutil import game_phase
        if game_phase(pos) == "finale":
            motifs.append(Motif("finale", "endgame_technique", "missed", [], {"move": pos.san(best) if best in pos.legal_moves else ""}))
        else:
            motifs.append(Motif("calcul", "positional", "missed", [], {"move": pos.san(best) if best in pos.legal_moves else ""}))
    # Dédoublonnage
    seen, uniq = set(), []
    for m in motifs:
        key = (m.theme, m.kind)
        if key not in seen:
            seen.add(key)
            uniq.append(m)
    return uniq


def _undeveloped_minors(board: chess.Board, color: chess.Color) -> int:
    home = [chess.B1, chess.G1, chess.C1, chess.F1] if color == chess.WHITE else [chess.B8, chess.G8, chess.C8, chess.F8]
    n = 0
    for sq in home:
        p = board.piece_at(sq)
        if p and p.color == color and p.piece_type in (chess.KNIGHT, chess.BISHOP):
            n += 1
    return n


def _principles(pos: chess.Board, played: chess.Move, best: chess.Move, is_error: bool) -> list[Motif]:
    out: list[Motif] = []
    mover = pos.turn
    piece = pos.piece_at(played.from_square)
    if piece is None or pos.is_check():
        return out
    opening = pos.fullmove_number <= 10
    queens_on = bool(pos.pieces(chess.QUEEN, chess.WHITE) or pos.pieces(chess.QUEEN, chess.BLACK))
    capture = pos.is_capture(played)
    gives_check = pos.gives_check(played)
    attacked = bool(pos.attackers(not mover, played.from_square))
    to_name = chess.square_name(played.to_square)

    if opening and piece.piece_type == chess.QUEEN and pos.fullmove_number <= 6 and not capture and _undeveloped_minors(pos, mover) >= 3:
        out.append(Motif("ouverture", "early_queen", "principle", [to_name], {"move": pos.san(played)}))

    if opening and not capture and not gives_check and not attacked and piece.piece_type in (chess.KNIGHT, chess.BISHOP, chess.QUEEN):
        own = pos.move_stack[(0 if mover == chess.WHITE else 1)::2]
        moved_before = any(m.to_square == played.from_square for m in own)
        if moved_before and _undeveloped_minors(pos, mover) >= 2:
            out.append(Motif("developpement", "same_piece_twice", "principle", [to_name], {"piece": PIECE_FR[piece.piece_type]}))

    if piece.piece_type == chess.KNIGHT and opening and chess.square_file(played.to_square) in (0, 7) and not capture:
        out.append(Motif("developpement", "knight_on_rim", "principle", [to_name], {}))

    if piece.piece_type == chess.KING and not pos.is_castling(played) and queens_on and not pos.is_check() and pos.has_castling_rights(mover):
        out.append(Motif("securite_roi", "king_walk", "principle", [to_name], {}))

    if piece.piece_type == chess.PAWN and opening and chess.square_file(played.from_square) in (5, 6) and not capture:
        king = pos.king(mover)
        if king is not None and chess.square_file(king) >= 4 and (is_error or chess.square_file(played.from_square) == 5):
            out.append(Motif("securite_roi", "weakening_pawn_move", "principle", [to_name], {"move": pos.san(played)}))

    if is_error and opening and best in pos.legal_moves and best != played:
        bp = pos.piece_at(best.from_square)
        center = {chess.D4, chess.E4, chess.D5, chess.E5}
        if bp and bp.piece_type == chess.PAWN and best.to_square in center and piece.piece_type == chess.PAWN and chess.square_file(played.from_square) in (0, 1, 6, 7):
            out.append(Motif("centre", "neglected_center", "principle", [chess.square_name(best.to_square)], {"move": pos.san(best)}))
        back = 0 if mover == chess.WHITE else 7
        if bp and bp.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(best.from_square) == back and \
                (piece.piece_type in (chess.QUEEN, chess.ROOK, chess.KING) or (piece.piece_type == chess.PAWN and chess.square_file(played.from_square) in (0, 1, 6, 7))):
            out.append(Motif("developpement", "should_develop", "principle", [chess.square_name(best.to_square)], {"move": pos.san(best)}))
        if pos.is_castling(best) and not pos.is_castling(played):
            out.append(Motif("securite_roi", "should_castle", "principle", [], {"move": pos.san(best)}))
    return out
