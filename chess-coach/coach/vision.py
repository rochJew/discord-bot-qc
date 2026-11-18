"""Reconnaissance de l'échiquier à l'écran (Chess.com ou autre site).

Pipeline :
1. Capture d'écran (mss).
2. Localisation de l'échiquier : recherche d'une grande zone carrée formée de
   deux couleurs qui alternent en damier (ou zone choisie à la main).
3. Calibration sur la position de départ : on apprend l'apparence de chaque
   pièce (quel que soit le style de pièces) et l'orientation de l'échiquier.
4. Lecture d'une position : chaque case est comparée aux modèles appris
   (le fond de la case est neutralisé, donc les surlignages ne gênent pas).
5. Reconstitution des coups : parmi les coups LÉGAUX, on cherche celui qui
   mène à la position observée (les règles corrigent les erreurs de lecture).

Important : ce module ENREGISTRE la partie ; l'application n'affiche aucune
aide du moteur pendant que la partie est en cours (respect du fair-play).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import chess
import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

FEAT = 32
LABELS = [c + p for c in "wb" for p in "PNBRQK"]


def _label(piece: chess.Piece) -> str:
    return ("w" if piece.color == chess.WHITE else "b") + piece.symbol().upper()


def _piece(label: str) -> chess.Piece:
    return chess.Piece(chess.PIECE_SYMBOLS.index(label[1].lower()), label[0] == "w")


def grab_full() -> tuple[np.ndarray, int, int]:
    """Capture de tous les écrans : (image BGR, décalage x, décalage y)."""
    import mss
    with mss.mss() as sct:
        mon = sct.monitors[0]
        shot = np.array(sct.grab(mon))
    return shot[:, :, :3].copy(), mon["left"], mon["top"]


def grab_screen(region: tuple[int, int, int, int] | None = None) -> np.ndarray:
    """Capture l'écran (ou une zone x, y, w, h) en BGR."""
    import mss
    with mss.mss() as sct:
        if region:
            x, y, w, h = region
            mon = {"left": x, "top": y, "width": w, "height": h}
        else:
            mon = sct.monitors[0]
        shot = np.array(sct.grab(mon))
    return shot[:, :, :3].copy()


# ---------------------------------------------------------------------------
# Localisation de l'échiquier
# ---------------------------------------------------------------------------
@dataclass
class BoardRect:
    x: int
    y: int
    size: int

    def crop(self, img: np.ndarray) -> np.ndarray:
        return img[self.y:self.y + self.size, self.x:self.x + self.size]

    def as_tuple(self):
        return (self.x, self.y, self.size, self.size)


def _checker_score(img: np.ndarray, rect: BoardRect, c1: np.ndarray, c2: np.ndarray, tol: float) -> float:
    s = rect.size / 8
    good = 0
    for r in range(8):
        for c in range(8):
            # Échantillon dans un coin de la case (là où il y a rarement une pièce)
            y = int(rect.y + r * s + s * 0.12)
            x = int(rect.x + c * s + s * 0.5)
            patch = img[max(0, y - 1):y + 2, max(0, x - 1):x + 2].reshape(-1, 3).astype(float)
            if patch.size == 0:
                continue
            col = np.median(patch, axis=0)
            want, other = (c1, c2) if (r + c) % 2 == 0 else (c2, c1)
            if np.abs(col - want).max() < tol and np.abs(col - other).max() >= tol:
                good += 1
    return good / 64


def find_board(img: np.ndarray) -> BoardRect | None:
    """Trouve automatiquement un échiquier à couleurs unies dans une capture BGR."""
    if cv2 is None:
        raise RuntimeError("opencv-python est requis pour la reconnaissance d'écran")
    h, w = img.shape[:2]
    scale = min(1.0, 1400 / max(h, w))
    small = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else img
    sh, sw = small.shape[:2]
    q = (small // 8).reshape(-1, 3)
    keys = q[:, 0].astype(np.int32) * 1024 + q[:, 1].astype(np.int32) * 32 + q[:, 2].astype(np.int32)
    uniq, counts = np.unique(keys, return_counts=True)
    order = np.argsort(-counts)[:14]
    colors = [np.array([(k // 1024) * 8 + 4, ((k // 32) % 32) * 8 + 4, (k % 32) * 8 + 4], float) for k in uniq[order]]
    best: tuple[float, BoardRect] | None = None
    tol = 26
    for i in range(len(colors)):
        for j in range(i + 1, len(colors)):
            c1, c2 = colors[i], colors[j]
            if np.abs(c1 - c2).max() < 30:
                continue
            m1 = np.all(np.abs(small.astype(np.int16) - c1) < tol, axis=2)
            m2 = np.all(np.abs(small.astype(np.int16) - c2) < tol, axis=2)
            if m1.mean() < 0.01 or m2.mean() < 0.01:
                continue
            mask = ((m1 | m2) * 255).astype(np.uint8)
            k = max(3, int(min(sh, sw) / 60))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                x, y, cw, ch = cv2.boundingRect(cnt)
                if cw < 0.15 * min(sh, sw) or abs(cw - ch) > 0.08 * max(cw, ch):
                    continue
                if cv2.contourArea(cnt) < 0.75 * cw * ch:
                    continue
                size = int(round(min(cw, ch)))
                rect = BoardRect(x, y, size)
                score = _checker_score(small, rect, c1, c2, tol)
                score = max(score, _checker_score(small, rect, c2, c1, tol))
                if score > 0.7 and (best is None or score * size > best[0]):
                    best = (score * size, rect)
    if best is None:
        return None
    r = best[1]
    return BoardRect(int(round(r.x / scale)), int(round(r.y / scale)), int(round(r.size / scale)))


# ---------------------------------------------------------------------------
# Reconnaissance des pièces
# ---------------------------------------------------------------------------
def _square_feature(sq_img: np.ndarray):
    """(occupé ?, vecteur de forme, « noirceur » de la pièce).

    - occupation : pixels qui diffèrent nettement de la couleur de fond de la case ;
    - forme : contours (Canny) flous, indépendants de la couleur de la case et des surlignages ;
    - couleur : proportion de pixels très sombres au centre (élevée pour les pièces noires).
    """
    h, w = sq_img.shape[:2]
    m = int(min(h, w) * 0.06)
    crop = sq_img[m:h - m, m:w - m]
    crop = cv2.resize(crop, (FEAT, FEAT), interpolation=cv2.INTER_AREA)
    c16 = crop.astype(np.int16)
    border = np.concatenate([c16[0], c16[-1], c16[:, 0], c16[:, -1]])
    bg = np.median(border, axis=0)
    diff = np.abs(c16 - bg).max(axis=2)
    mask = diff > 40
    occ = mask[3:-3, 3:-3].mean()
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    big = cv2.resize(gray, (FEAT * 2, FEAT * 2), interpolation=cv2.INTER_LINEAR)
    edges = cv2.Canny(big, 60, 160)
    edges = cv2.GaussianBlur(edges.astype(np.float32), (7, 7), 0)
    edges = cv2.resize(edges, (FEAT, FEAT), interpolation=cv2.INTER_AREA).ravel()
    n = float(np.linalg.norm(edges)) or 1.0
    q = FEAT // 4
    center = gray[q:-q, q:-q]
    darkness = float((center < 85).mean())
    return occ > 0.07, edges / n, darkness


class PieceRecognizer:
    def __init__(self):
        self.templates: dict[str, list[np.ndarray]] = {}
        self.white_bottom = True
        self.dark_threshold = 0.3

    @property
    def calibrated(self) -> bool:
        return all(lbl in self.templates for lbl in LABELS)

    def _squares(self, board_img: np.ndarray):
        size = board_img.shape[0]
        s = size / 8
        for r in range(8):
            for c in range(8):
                y0, y1 = int(round(r * s)), int(round((r + 1) * s))
                x0, x1 = int(round(c * s)), int(round((c + 1) * s))
                if self.white_bottom:
                    sq = chess.square(c, 7 - r)
                else:
                    sq = chess.square(7 - c, r)
                yield sq, board_img[y0:y1, x0:x1]

    def calibrate(self, board_img: np.ndarray) -> str | None:
        """Apprend les pièces depuis la position de départ. Retourne un message d'erreur ou None."""
        size = min(board_img.shape[:2])
        board_img = board_img[:size, :size]
        s = size / 8
        feats = {}
        for r in range(8):
            for c in range(8):
                crop = board_img[int(r * s):int((r + 1) * s), int(c * s):int((c + 1) * s)]
                feats[(r, c)] = _square_feature(crop)
        for (r, c), (occ, _, _) in feats.items():
            expected = r in (0, 1, 6, 7)
            if occ != expected:
                return ("La position de départ n'est pas reconnue. Affiche l'échiquier au tout début de la partie "
                        "(avant le premier coup) puis relance la calibration.")
        top = np.mean([feats[(r, c)][2] for r in (0, 1) for c in range(8)])
        bottom = np.mean([feats[(r, c)][2] for r in (6, 7) for c in range(8)])
        if abs(top - bottom) < 0.05:
            return "Impossible de distinguer les pièces blanches des noires sur cette capture."
        self.white_bottom = bottom < top  # les pièces noires sont plus sombres
        self.dark_threshold = float((top + bottom) / 2)
        start = chess.Board()
        self.templates = {}
        for r in range(8):
            for c in range(8):
                sq = chess.square(c, 7 - r) if self.white_bottom else chess.square(7 - c, r)
                p = start.piece_at(sq)
                if p:
                    self.templates.setdefault(_label(p), []).append(feats[(r, c)][1])
        return None

    def read(self, board_img: np.ndarray) -> dict[int, str]:
        """Lit la position : {case: 'wP' / 'bK' ...} (cases vides absentes)."""
        if not self.calibrated:
            raise RuntimeError("Calibration nécessaire")
        size = min(board_img.shape[:2])
        board_img = board_img[:size, :size]
        out = {}
        for sq, crop in self._squares(board_img):
            occ, feat, dark = _square_feature(crop)
            if not occ:
                continue
            color = "b" if dark > self.dark_threshold else "w"
            best_lbl, best_d = None, 1e18
            for lbl, temps in self.templates.items():
                if lbl[0] != color:
                    continue
                for t in temps:
                    d = float(np.sum((feat - t) ** 2))
                    if d < best_d:
                        best_lbl, best_d = lbl, d
            out[sq] = best_lbl
        return out

    def save(self, path: Path):
        data = {"white_bottom": self.white_bottom, "dark_threshold": self.dark_threshold,
                "templates": {k: [t.tolist() for t in v] for k, v in self.templates.items()}}
        path.write_text(json.dumps(data), encoding="utf-8")

    def load(self, path: Path) -> bool:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
        self.white_bottom = data.get("white_bottom", True)
        self.dark_threshold = data.get("dark_threshold", 0.3)
        self.templates = {k: [np.array(t, np.float32) for t in v] for k, v in data["templates"].items()}
        return self.calibrated


def placement(board: chess.Board) -> dict[int, str]:
    return {sq: _label(p) for sq, p in board.piece_map().items()}


def mismatch(a: dict[int, str], b: dict[int, str]) -> int:
    keys = set(a) | set(b)
    return sum(1 for k in keys if a.get(k) != b.get(k))


class GameTracker:
    """Reconstitue la partie coup par coup à partir des positions lues."""

    def __init__(self, board: chess.Board | None = None):
        self.board = board or chess.Board()
        self._pending: dict[int, str] | None = None
        self._pending_count = 0

    def feed(self, obs: dict[int, str], stable_frames: int = 2) -> list[chess.Move]:
        """Ajoute une observation ; renvoie les coups nouvellement reconnus."""
        if obs == self._pending:
            self._pending_count += 1
        else:
            self._pending, self._pending_count = obs, 1
        if self._pending_count < stable_frames:
            return []
        current = placement(self.board)
        cur_mis = mismatch(current, obs)
        if cur_mis == 0:
            return []
        # Un coup
        scored = []
        for mv in self.board.legal_moves:
            b = self.board.copy(stack=False)
            b.push(mv)
            scored.append((mismatch(placement(b), obs), mv))
        scored.sort(key=lambda t: t[0])
        if scored and scored[0][0] == 0:
            return self._push([scored[0][1]])
        if scored and scored[0][0] <= 1 and (len(scored) == 1 or scored[1][0] > scored[0][0]) and cur_mis >= 2:
            return self._push([scored[0][1]])
        # Deux coups (une image ratée)
        best2 = None
        for mv in self.board.legal_moves:
            b = self.board.copy(stack=False)
            b.push(mv)
            for mv2 in b.legal_moves:
                b2 = b.copy(stack=False)
                b2.push(mv2)
                m = mismatch(placement(b2), obs)
                if m == 0:
                    if best2 is not None:
                        return []  # ambigu
                    best2 = (mv, mv2)
        if best2:
            return self._push(list(best2))
        return []

    def _push(self, moves: list[chess.Move]) -> list[chess.Move]:
        for mv in moves:
            self.board.push(mv)
        return moves

    def is_new_game(self, obs: dict[int, str]) -> bool:
        return len(self.board.move_stack) > 4 and mismatch(placement(chess.Board()), obs) == 0

    def pgn(self, white: str = "Moi", black: str = "Adversaire") -> str:
        import chess.pgn
        game = chess.pgn.Game.from_board(self.board)
        game.headers["Event"] = "Partie enregistrée à l'écran"
        game.headers["Site"] = "Capture d'écran"
        game.headers["White"] = white
        game.headers["Black"] = black
        return str(game)
