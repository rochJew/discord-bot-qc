"""Outils d'échecs : valeurs des pièces, noms français, échange statique (SEE)."""
from __future__ import annotations

import math

import chess

VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}

PIECE_FR = {
    chess.PAWN: "pion", chess.KNIGHT: "cavalier", chess.BISHOP: "fou",
    chess.ROOK: "tour", chess.QUEEN: "dame", chess.KING: "roi",
}
# Article défini adapté (le/la)
PIECE_FR_DEF = {
    chess.PAWN: "le pion", chess.KNIGHT: "le cavalier", chess.BISHOP: "le fou",
    chess.ROOK: "la tour", chess.QUEEN: "la dame", chess.KING: "le roi",
}
PIECE_FR_INDEF = {
    chess.PAWN: "un pion", chess.KNIGHT: "un cavalier", chess.BISHOP: "un fou",
    chess.ROOK: "une tour", chess.QUEEN: "une dame", chess.KING: "le roi",
}
COLOR_FR = {chess.WHITE: "les Blancs", chess.BLACK: "les Noirs"}

# Lettres françaises pour la notation (R D T F C)
SAN_FR = str.maketrans({"K": "R", "Q": "D", "R": "T", "B": "F", "N": "C"})


def san_fr(san: str) -> str:
    """Convertit une notation SAN anglaise en notation française (Cf3, Dxd5...)."""
    return san.translate(SAN_FR)


def piece_value(piece_type: int) -> int:
    return VALUES[piece_type]


def material(board: chess.Board, color: chess.Color) -> int:
    return sum(VALUES[p] * len(board.pieces(p, color)) for p in range(1, 6))


def material_balance(board: chess.Board, color: chess.Color) -> int:
    return material(board, color) - material(board, not color)


def _least_valuable_attacker(board: chess.Board, square: chess.Square, color: chess.Color):
    best_sq, best_val = None, 1000
    for sq in board.attackers(color, square):
        p = board.piece_at(sq)
        if p is None:
            continue
        # Une pièce clouée sur son roi ne peut pas capturer hors de la ligne
        if board.is_pinned(color, sq) and not (board.pin(color, sq) & chess.BB_SQUARES[square]):
            continue
        v = VALUES[p.piece_type]
        if v < best_val:
            best_sq, best_val = sq, v
    return best_sq


def see(board: chess.Board, move: chess.Move) -> int:
    """Évaluation statique de l'échange pour une capture (en points de pion).

    Retourne le gain matériel attendu pour le camp qui joue `move` si les deux
    camps continuent d'échanger sur la case avec leur pièce la moins chère,
    chacun pouvant s'arrêter quand ça l'arrange.
    """
    if board.is_en_passant(move):
        captured_val = 1
    else:
        cap = board.piece_at(move.to_square)
        captured_val = VALUES[cap.piece_type] if cap else 0
    mover = board.piece_at(move.from_square)
    if mover is None:
        return 0
    b = board.copy(stack=False)
    b.push(move)
    gain = [captured_val]
    on_square = VALUES[mover.piece_type] if not move.promotion else VALUES[move.promotion]
    if move.promotion:
        gain[0] += VALUES[move.promotion] - 1
    side = b.turn
    target = move.to_square
    while True:
        att = _least_valuable_attacker(b, target, side)
        if att is None:
            break
        att_piece = b.piece_at(att)
        if att_piece.piece_type == chess.KING and b.attackers(not side, target):
            break  # le roi ne peut pas reprendre sur une case défendue
        gain.append(on_square - gain[-1])
        on_square = VALUES[att_piece.piece_type]
        promo = chess.QUEEN if att_piece.piece_type == chess.PAWN and chess.square_rank(target) in (0, 7) else None
        try:
            b.push(chess.Move(att, target, promotion=promo))
        except Exception:
            break
        side = b.turn
        if len(gain) > 32:
            break
    # Minimax arrière : chacun peut refuser de continuer l'échange
    for i in range(len(gain) - 1, 0, -1):
        gain[i - 1] = -max(-gain[i - 1], gain[i])
    return gain[0]


def hanging_pieces(board: chess.Board, color: chess.Color, min_gain: int = 2):
    """Pièces de `color` que l'adversaire peut gagner tout de suite (gain SEE >= min_gain).

    Retourne une liste (case, gain, coup de capture) triée par gain décroissant.
    Le plateau est analysé comme si c'était au tour de l'adversaire.
    """
    b = board.copy(stack=False)
    if b.turn == color:
        if b.is_check():
            return []
        b.push(chess.Move.null())
    res = {}
    for mv in b.legal_moves:
        if not b.is_capture(mv):
            continue
        g = see(b, mv)
        if g >= min_gain:
            sq = mv.to_square
            if sq not in res or res[sq][0] < g:
                res[sq] = (g, mv)
    return sorted(((sq, g, mv) for sq, (g, mv) in res.items()), key=lambda t: -t[1])


def win_percent(cp: float) -> float:
    """Chances de gain (0-100) à partir d'une évaluation en centipions (formule Lichess)."""
    cp = max(-1500.0, min(1500.0, cp))
    return 50 + 50 * (2 / (1 + math.exp(-0.00368208 * cp)) - 1)


def move_accuracy(win_before: float, win_after: float) -> float:
    """Précision d'un coup (0-100), formule Lichess."""
    diff = max(0.0, win_before - win_after)
    acc = 103.1668 * math.exp(-0.04354 * diff) - 3.1669
    return max(0.0, min(100.0, acc))


def game_phase(board: chess.Board) -> str:
    """ouverture / milieu / finale (heuristique simple)."""
    non_pawn = sum(VALUES[p] * len(board.pieces(p, c)) for p in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN) for c in chess.COLORS)
    if board.fullmove_number <= 10 and non_pawn >= 56:
        return "ouverture"
    if non_pawn <= 26 or (not board.pieces(chess.QUEEN, chess.WHITE) and not board.pieces(chess.QUEEN, chess.BLACK) and non_pawn <= 32):
        return "finale"
    return "milieu"
