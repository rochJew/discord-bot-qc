"""Explications pédagogiques en français, adaptées à un joueur ~400-1000 Elo.

Tout est construit à partir de faits vérifiés par Stockfish (coups, lignes,
matériel) : le texte ne peut donc pas « inventer » de variante. L'IA (optionnelle)
reformule ensuite ces faits dans un style plus naturel (voir llm.py).
"""
from __future__ import annotations

import chess

from .analysis import CLASS_FR, MoveAnalysis
from .chessutil import PIECE_FR, PIECE_FR_DEF, VALUES, hanging_pieces, san_fr, see

# ---------------------------------------------------------------------------
# Réflexes à retenir, par thème (la « règle d'or » associée à chaque erreur)
# ---------------------------------------------------------------------------
REFLEXES = {
    "piece_en_prise": "Avant de lâcher ta pièce, pose-toi deux questions : « Cette case est-elle attaquée ? » et « Est-elle protégée ? ». "
                      "Compte les attaquants et les défenseurs. S'il y a plus d'attaquants que de défenseurs, ta pièce tombe.",
    "capture_manquee": "À chaque coup, fais le tour des captures possibles. Une pièce adverse non protégée, c'est du matériel gratuit : "
                       "à notre niveau, la partie se gagne souvent juste en ramassant ce que l'adversaire laisse traîner.",
    "fourchette": "Repère les pièces qui ne sont pas protégées et celles qui sont alignées « à un saut de cavalier » de la même case. "
                  "Une fourchette, c'est toujours deux cibles en même temps : roi + dame, roi + tour, dame + tour...",
    "clouage": "Quand une pièce est devant une pièce plus importante (le roi, la dame), elle est « clouée » : elle ne peut pas bouger "
               "sans exposer ce qu'il y a derrière. Évite d'aligner ton roi et ta dame sur une même ligne ou diagonale ouverte.",
    "enfilade": "L'enfilade, c'est le clouage à l'envers : on attaque la grosse pièce, elle se pousse, et on prend celle de derrière. "
                "Méfie-toi quand ton roi ou ta dame est sur la même ligne qu'une autre de tes pièces non protégée.",
    "mat": "Échecs, captures, menaces : c'est la checklist à faire À CHAQUE COUP. Regarde d'abord tous les échecs possibles, "
           "les tiens et ceux de ton adversaire. Un roi avec peu de cases de fuite est toujours en danger.",
    "menaces": "Après chaque coup adverse, demande-toi : « Qu'est-ce qu'il veut faire ? Qu'est-ce qu'il attaque ? ». "
               "C'est LE réflexe qui fait passer de 400 à 1000 : ne jamais jouer ton plan sans avoir regardé sa menace.",
    "developpement": "Dans l'ouverture, chaque coup doit sortir une nouvelle pièce. Cavaliers et fous d'abord, puis roque. "
                     "Bouger deux fois la même pièce, c'est laisser l'adversaire prendre de l'avance en développement.",
    "centre": "Le centre (e4, d4, e5, d5), c'est comme le milieu d'un terrain de foot : celui qui le contrôle a plus de place "
              "et ses pièces vont partout plus vite. Commence par un pion central.",
    "securite_roi": "Roque tôt (idéalement dans les 10 premiers coups) et ne pousse pas les pions devant ton roi sans raison. "
                    "Un roi au centre avec des colonnes ouvertes, c'est une cible.",
    "ouverture": "Les 3 règles d'or de l'ouverture : 1) un pion au centre, 2) sors tes cavaliers et tes fous, 3) roque. "
                 "Ta dame sort APRÈS les pièces mineures, sinon elle se fait chasser et tu perds des temps.",
    "finale": "En finale, ton roi devient une pièce d'attaque : centralise-le. Pousse tes pions passés (ceux qu'aucun pion adverse "
              "ne peut arrêter) et rappelle-toi que les tours se placent derrière les pions passés.",
    "calcul": "Avant de jouer, imagine la meilleure réponse de ton adversaire, pas celle qui t'arrange. "
              "Joue le coup dans ta tête, puis regarde la position avec les yeux de ton adversaire.",
}

CCT = ("Méthode « Échecs – Captures – Menaces » : avant de jouer, regarde 1) tous les échecs, 2) toutes les captures, "
       "3) toutes les menaces — d'abord pour ton adversaire, puis pour toi.")


_FEM = {"dame", "tour"}


def poss(name: str, owner: str = "ton") -> str:
    """Possessif accordé : ton cavalier / ta dame / son fou / sa tour."""
    if name in _FEM:
        owner = {"ton": "ta", "son": "sa", "Ton": "Ta", "Son": "Sa"}.get(owner, owner)
    return f"{owner} {name}"


def _targets(f: dict, squares: list[str], owner: str) -> str:
    names = f.get("targets", [])
    sqs = squares[1:] if len(squares) > len(names) else squares
    parts = [f"{poss(n, owner)} ({sq})" if i < len(sqs) and (sq := sqs[i]) else poss(n, owner) for i, n in enumerate(names)]
    return " et ".join(parts) if len(parts) <= 2 else ", ".join(parts[:-1]) + " et " + parts[-1]


def _sanfr(s: str) -> str:
    return san_fr(s) if s else s


def _line(moves: list[str], start_board: chess.Board | None = None, n: int = 5) -> str:
    """Formate une ligne de coups en notation française avec numéros."""
    if not moves:
        return ""
    out = []
    if start_board is None:
        return " ".join(_sanfr(m) for m in moves[:n])
    num = start_board.fullmove_number
    white = start_board.turn == chess.WHITE
    for i, mv in enumerate(moves[:n]):
        if white:
            out.append(f"{num}.{_sanfr(mv)}")
        else:
            out.append(f"{num}...{_sanfr(mv)}" if i == 0 else _sanfr(mv))
            num += 1
        white = not white
    return " ".join(out)


def describe_move_idea(board: chess.Board, move: chess.Move) -> list[str]:
    """Décrit en mots simples ce que fait un coup (l'idée derrière)."""
    if move not in board.legal_moves:
        return []
    me = board.turn
    piece = board.piece_at(move.from_square)
    ideas: list[str] = []
    after = board.copy(stack=False)
    after.push(move)
    if after.is_checkmate():
        return ["c'est échec et mat directement !"]
    if board.is_castling(move):
        ideas.append("il met ton roi à l'abri et relie tes tours (le roque, c'est deux coups utiles en un)")
    if board.is_capture(move):
        cap = board.piece_at(move.to_square)
        name = PIECE_FR_DEF[cap.piece_type] if cap else "le pion"
        g = see(board, move)
        if g >= 2:
            ideas.append(f"il capture {name} gratuitement (tu gagnes {g} points de matériel)")
        elif g >= 0:
            ideas.append(f"il prend {name} et l'échange est équilibré ou à ton avantage")
        else:
            ideas.append(f"il prend {name} (c'est un sacrifice calculé : la suite rapporte plus)")
    if move.promotion:
        ideas.append("il promeut un pion en " + PIECE_FR[move.promotion])
    if board.is_check():
        ideas.append("il pare l'échec")
    if after.is_check():
        ideas.append("il donne échec : ton adversaire est obligé de répondre, tu gardes l'initiative")
    # Pièces menacées avant, sauvées après
    hang_before = {sq for sq, _, _ in hanging_pieces(board, me, 2)}
    if hang_before and not after.is_check():
        hang_after = {sq for sq, _, _ in hanging_pieces(after, me, 2)}
        saved = [sq for sq in hang_before if sq not in hang_after and sq != move.from_square]
        if move.from_square in hang_before and move.to_square not in hang_after:
            ideas.append(f"il met {poss(PIECE_FR[piece.piece_type], 'ton')} à l'abri (il y avait une menace dessus)")
        for sq in saved[:1]:
            p = board.piece_at(sq)
            if p:
                ideas.append(f"il protège {poss(PIECE_FR[p.piece_type], 'ton')} en {chess.square_name(sq)}, qui était menacé(e)")
    back = 0 if me == chess.WHITE else 7
    if piece and piece.piece_type in (chess.KNIGHT, chess.BISHOP) and chess.square_rank(move.from_square) == back and not board.is_capture(move):
        ideas.append(f"il développe {poss(PIECE_FR[piece.piece_type], 'ton')} vers une case active")
    if piece and piece.piece_type == chess.PAWN and move.to_square in (chess.D4, chess.E4, chess.D5, chess.E5):
        ideas.append("il occupe le centre avec un pion")
    # Nouvelles attaques créées
    if not after.is_checkmate():
        targets = []
        for t in after.attacks(move.to_square):
            tp = after.piece_at(t)
            if tp and tp.color != me and tp.piece_type != chess.KING and tp.piece_type != chess.PAWN:
                if VALUES[tp.piece_type] > VALUES[piece.piece_type] or not after.attackers(not me, t):
                    targets.append(PIECE_FR_DEF[tp.piece_type])
        if targets and not board.is_capture(move):
            ideas.append("il attaque " + " et ".join(targets[:2]))
        before_thr = {sq for sq, _, _ in hanging_pieces(board, not me, 2)} if not board.is_check() else set()
        threats = [t for t in hanging_pieces(after, not me, 2) if t[0] not in before_thr]
        if threats and not targets:
            sq, g, _ = threats[0]
            tp = after.piece_at(sq)
            if tp:
                ideas.append(f"il crée une menace sur {PIECE_FR_DEF[tp.piece_type]} en {chess.square_name(sq)}")
    if piece and piece.piece_type == chess.KING and not board.is_castling(move):
        if board.fullmove_number > 25 or len(board.piece_map()) <= 12:
            ideas.append("il active ton roi : en finale, le roi est une pièce forte qui doit aller au centre")
    if piece and piece.piece_type == chess.ROOK and not ideas:
        f = chess.square_file(move.to_square)
        if not any(chess.square_file(s) == f for s in board.pieces(chess.PAWN, me)):
            ideas.append("il place ta tour sur une colonne ouverte, là où elle est la plus active")
    if not ideas:
        ideas.append("il améliore la position d'une pièce sans rien laisser à ton adversaire")
    return ideas


def _what_to_look_for(m: MoveAnalysis, themes: set[str]) -> str:
    if "mat" in themes:
        return ("Le roi adverse (ou le tien !) était fragile. Dans ce genre de position, la première chose à faire est de "
                "lister tous les échecs possibles. " + CCT)
    if themes & {"piece_en_prise", "menaces"}:
        return ("Ici, il fallait surtout vérifier la sécurité de tes pièces : lesquelles sont attaquées ? Lesquelles ne sont "
                "protégées par personne ? " + CCT)
    if themes & {"capture_manquee", "fourchette", "clouage", "enfilade"}:
        return ("Il y avait une opportunité tactique. Quand l'adversaire laisse des pièces non protégées ou alignées, "
                "cherche les coups qui attaquent DEUX choses à la fois. " + CCT)
    if m.phase == "ouverture":
        return ("On est dans l'ouverture : le plan, c'est centre, développement, roque. Avant chaque coup, demande-toi "
                "« Est-ce que ce coup sort une nouvelle pièce ou aide à contrôler le centre ? »")
    if m.phase == "finale":
        return ("En finale, le plan est simple : active ton roi, crée un pion passé et pousse-le. Les tactiques existent "
                "encore, donc garde le réflexe échecs-captures-menaces.")
    return ("Dans le milieu de jeu, cherche ta pièce la moins active et demande-toi comment l'améliorer, tout en gardant "
            "un œil sur ce que menace ton adversaire.")


def _motif_sentences(m: MoveAnalysis, board: chess.Board) -> tuple[list[str], list[str]]:
    """Retourne (pourquoi, ce_que_l_adversaire_pouvait_faire)."""
    why: list[str] = []
    opp: list[str] = []
    after = chess.Board(m.fen_after)
    reply_line = _line(m.reply_pv_san, after, 5)
    for mo in m.motifs:
        k, f = mo["kind"], mo.get("facts", {})
        if k in ("allowed_mate", "allowed_back_rank_mate"):
            n = f.get("mate_in", 1)
            why.append(f"Ce coup laisse un mat en {n} ! Ton roi n'a plus assez de défenseurs ni de cases de fuite.")
            if k == "allowed_back_rank_mate":
                why.append("C'est le fameux « mat du couloir » : ton roi est enfermé sur sa dernière rangée par ses propres pions. "
                           "Une petite case de sortie (un « luft », par exemple h3 ou g3) aurait tout changé.")
            opp.append(f"Ton adversaire peut jouer {reply_line} et c'est mat.")
        elif k == "moved_piece_hanging":
            why.append(f"Tu as posé {poss(f['piece'], 'ton')} en {f['square']}, mais cette case est attaquée et pas assez protégée. "
                       f"Résultat : tu perds {f['gain']} point{'s' if f['gain'] > 1 else ''} de matériel.")
            opp.append(f"Il lui suffit de prendre avec {_sanfr(f['capture'])}.")
        elif k == "left_hanging":
            why.append(f"En jouant ce coup, tu as laissé {poss(f['piece'], 'ton')} en {f['square']} sans protection suffisante "
                       f"(ou tu as enlevé la pièce qui le défendait).")
            opp.append(f"Il peut simplement le capturer : {_sanfr(f['capture'])}, et tu perds {f['gain']} points.")
        elif k == "ignored_threat":
            why.append(f"Il y avait DÉJÀ une menace sur {poss(f['piece'], 'ton')} en {f['square']} avant ton coup, et ton coup ne règle pas le problème. "
                       "Tu as joué ton idée sans regarder ce que voulait ton adversaire.")
            opp.append(f"Il n'a plus qu'à le prendre : {_sanfr(f['capture'])}.")
        elif k == "allowed_fork":
            tg = _targets(f, mo.get("squares", []), "ton")
            why.append(f"Ce coup permet une fourchette : une seule pièce adverse va attaquer {tg} en même temps.")
            opp.append(f"Avec {_sanfr(f['move'])}, {poss(f['piece'], 'son')} attaque {tg}. Tu ne peux pas tout sauver.")
        elif k == "allowed_pin":
            why.append(f"Ce coup te met sur une ligne dangereuse : {poss(f['front'], 'ton')} va se retrouver cloué(e) devant {poss(f['back'], 'ton')}.")
            opp.append(f"Avec {_sanfr(f['move'])}, il cloue {poss(f['front'], 'ton')} : s'il bouge, c'est {poss(f['back'], 'ton')} qui tombe.")
        elif k == "allowed_skewer":
            why.append(f"{poss(f['front'], 'Ton')} et {poss(f['back'], 'ton')} sont alignés : c'est une enfilade qui t'attend.")
            opp.append(f"Avec {_sanfr(f['move'])}, il attaque {poss(f['front'], 'ton')} ; quand il bouge, {poss(f['back'], 'ton')} tombe.")
        elif k in ("missed_mate", "missed_back_rank_mate"):
            why.append(f"Tu avais un mat en {f['mate_in']} ! Il commençait par {_sanfr(f['move'])}.")
            if k == "missed_back_rank_mate":
                why.append("C'était un mat du couloir : le roi adverse était coincé derrière ses pions sur sa dernière rangée.")
        elif k == "missed_free_piece":
            why.append(f"Il y avait {('un ' if f['piece'] in ('pion', 'cavalier', 'fou', 'roi') else 'une ')}{f['piece']} "
                       f"à prendre avec {_sanfr(f['move'])} : tu gagnais {f['gain']} points sans rien donner en échange.")
        elif k == "missed_fork":
            tg = _targets(f, mo.get("squares", []), "son")
            why.append(f"Tu pouvais faire une fourchette avec {_sanfr(f['move'])} : {poss(f['piece'], 'ton')} attaquait {tg} en même temps.")
        elif k == "missed_pin":
            why.append(f"Tu pouvais clouer {poss(f['front'], 'son')} devant {poss(f['back'], 'son')} avec {_sanfr(f['move'])}.")
        elif k == "missed_skewer":
            why.append(f"Tu pouvais faire une enfilade avec {_sanfr(f['move'])} : attaquer {poss(f['front'], 'son')} pour gagner {poss(f['back'], 'son')} derrière.")
        elif k == "missed_promotion":
            why.append(f"Ton pion était tout près de devenir une dame : {_sanfr(f['move'])} était la clé.")
        elif k == "material_swing":
            lost = f.get("lost") or []
            if lost:
                why.append("Ce coup a l'air normal, mais il a un défaut tactique : la suite te fait perdre du matériel ("
                           + ", ".join(_sanfr(x) for x in lost[:3]) + ").")
            else:
                why.append("Ce coup a un défaut tactique : la suite te fait perdre du matériel.")
            if reply_line:
                opp.append(f"La meilleure suite pour lui : {reply_line}.")
        elif k == "early_queen":
            why.append("Tu sors ta dame très tôt. Elle va se faire chasser par les pièces adverses qui, elles, se développent "
                       "en l'attaquant : tu perds du temps.")
        elif k == "same_piece_twice":
            why.append(f"Tu rejoues {poss(f.get('piece', 'pièce'), 'ton')} alors que d'autres pièces dorment encore à la maison. "
                       "Dans l'ouverture, un coup = une nouvelle pièce.")
        elif k == "knight_on_rim":
            why.append("« Cavalier sur le bord, cavalier mort » : sur le bord, il contrôle moitié moins de cases qu'au centre.")
        elif k == "king_walk":
            why.append("Ton roi bouge sans roquer : il perd le droit de roquer et reste exposé au centre.")
        elif k == "weakening_pawn_move":
            why.append(f"Le coup {_sanfr(f.get('move', ''))} affaiblit les pions devant ton roi : la diagonale vers ton roi s'ouvre.")
        elif k == "neglected_center":
            why.append(f"Tu joues sur le côté alors que {_sanfr(f['move'])} prenait le centre.")
        elif k == "should_develop":
            why.append(f"Il fallait plutôt développer une pièce ({_sanfr(f['move'])}).")
        elif k == "should_castle":
            why.append(f"C'était le bon moment pour roquer ({_sanfr(f['move'])}).")
        elif k == "endgame_technique":
            why.append("C'est une erreur de technique de finale : il y avait une façon plus précise de convertir ou de tenir la position.")
        elif k == "positional":
            why.append("Ce n'est pas une erreur tactique évidente, mais ton coup est moins utile que le meilleur coup : "
                       "ton adversaire récupère de l'avantage.")
    if not opp and reply_line and m.is_error:
        opp.append(f"Sa meilleure réponse : {reply_line}.")
    return why, opp


def explain(m: MoveAnalysis) -> dict:
    """Construit l'explication structurée d'un coup analysé."""
    board = chess.Board(m.fen_before)
    num = f"{m.move_number}{'.' if m.color == 'white' else '...'}"
    title = f"{num}{_sanfr(m.san)} — {CLASS_FR[m.classification]}"
    themes = {mo["theme"] for mo in m.motifs}
    sections: dict[str, str] = {"titre": title}

    if not m.is_error:
        if m.classification == "best":
            sections["resume"] = "Exactement le coup de l'ordinateur. Bien joué !"
        else:
            sections["resume"] = f"Bon coup. Le meilleur était {_sanfr(m.best_san)}, mais la différence est minime."
        tips = [mo for mo in m.motifs if mo["side"] == "principle"]
        if tips:
            why, _ = _motif_sentences(m, board)
            sections["conseil"] = " ".join(why)
            sections["retenir"] = REFLEXES.get(tips[0]["theme"], "")
        return sections

    severity = {"inaccuracy": "se dégrade un peu", "mistake": "se dégrade nettement", "miss": "",
                "blunder": "s'effondre"}[m.classification]
    if m.classification == "miss":
        sections["resume"] = (f"Ton adversaire venait de faire une erreur, et tu pouvais en profiter avec {_sanfr(m.best_san)}. "
                              f"Avec {_sanfr(m.san)}, tu laisses passer l'occasion "
                              f"(tes chances de gagner passent de {m.win_before:.0f}% à {m.win_after:.0f}%).")
    else:
        sections["resume"] = (f"Avec {_sanfr(m.san)}, ta position {severity} : tes chances de gagner passent de "
                              f"{m.win_before:.0f}% à {m.win_after:.0f}%.")
    why, opp = _motif_sentences(m, board)
    sections["pourquoi"] = " ".join(why) if why else "Ce coup laisse l'initiative à ton adversaire."
    sections["adversaire"] = " ".join(opp) if opp else ""
    best_mv = chess.Move.from_uci(m.best_uci) if m.best_uci else None
    ideas = describe_move_idea(board, best_mv) if best_mv else []
    best_line = _line(m.best_pv_san, board, 5)
    sections["meilleur"] = (f"Le meilleur coup était {_sanfr(m.best_san)} : " + ", ".join(ideas[:3]) + "."
                            + (f" La suite principale : {best_line}." if len(m.best_pv_san) > 1 else ""))
    sections["idee"] = _strategic_idea(m, themes, ideas)
    sections["chercher"] = _what_to_look_for(m, themes)
    main_theme = _main_theme(m)
    sections["retenir"] = REFLEXES.get(main_theme, REFLEXES["calcul"])
    return sections


def _main_theme(m: MoveAnalysis) -> str:
    priority = ["mat", "menaces", "piece_en_prise", "fourchette", "clouage", "enfilade", "capture_manquee", "finale",
                "securite_roi", "ouverture", "developpement", "centre", "calcul"]
    themes = [mo["theme"] for mo in m.motifs]
    for t in priority:
        if t in themes:
            return t
    return "calcul"


def _strategic_idea(m: MoveAnalysis, themes: set[str], ideas: list[str]) -> str:
    if themes & {"mat"}:
        return "Ici tout tourne autour de la sécurité des rois : le roi le plus exposé décide de la partie."
    if themes & {"piece_en_prise", "menaces", "capture_manquee"}:
        return ("L'idée de fond est simple : le matériel. À ce niveau, celui qui garde ses pièces et ramasse celles de "
                "l'autre gagne presque toujours. Chaque pièce doit être protégée ou hors de portée.")
    if themes & {"fourchette", "clouage", "enfilade"}:
        return ("Les tactiques naissent de deux choses : des pièces non protégées et des pièces mal placées (alignées ou à "
                "portée de cavalier). Le meilleur coup exploite (ou évite) exactement ça.")
    if m.phase == "ouverture":
        return ("Dans l'ouverture, on fait la course au développement : la personne qui sort ses pièces et met son roi à "
                "l'abri le plus vite aura l'initiative au milieu de jeu.")
    if m.phase == "finale":
        return "En finale, l'activité du roi et les pions passés valent souvent plus qu'un petit gain de matériel."
    return ("Au milieu de jeu, un bon plan consiste à améliorer sa pire pièce, viser une faiblesse adverse (pion isolé, roi "
            "mal protégé) et ne jamais laisser de pièce sans protection.")


def explanation_text(m: MoveAnalysis) -> str:
    """Version texte (HTML léger) de l'explication, pour l'interface."""
    s = explain(m)
    labels = [
        ("resume", None),
        ("pourquoi", "Pourquoi c'est une erreur"),
        ("adversaire", "Ce que ton adversaire pouvait faire"),
        ("meilleur", "Le meilleur coup"),
        ("idee", "L'idée stratégique"),
        ("chercher", "Ce que tu devais chercher"),
        ("conseil", "Petit conseil"),
        ("retenir", "Le réflexe à retenir"),
    ]
    parts = [f"<h3>{s['titre']}</h3>"]
    for key, label in labels:
        if s.get(key):
            if label:
                parts.append(f"<p><b>{label}</b><br>{s[key]}</p>")
            else:
                parts.append(f"<p>{s[key]}</p>")
    return "\n".join(parts)


def game_summary(analysis) -> dict:
    """Bilan pédagogique d'une partie entière (pour l'utilisateur)."""
    from collections import Counter

    from .motifs import THEMES
    user = analysis.user_moves()
    errors = [m for m in user if m.is_error]
    counts = analysis.counts()
    acc = analysis.accuracy()
    themes = Counter(mo["theme"] for m in errors for mo in m.motifs)
    for m in user:
        for mo in m.motifs:
            if mo["side"] == "principle" and not m.is_error:
                themes[mo["theme"]] += 0.5
    top = [t for t, _ in themes.most_common(3)]
    lines = []
    lines.append(f"Précision : {acc:.0f}%. Gaffes : {counts['blunder']}, erreurs : {counts['mistake']}, "
                 f"occasions manquées : {counts['miss']}, imprécisions : {counts['inaccuracy']}.")
    if counts["blunder"] == 0 and counts["mistake"] == 0:
        lines.append("Aucune grosse erreur : c'est exactement comme ça qu'on monte au classement. Bravo !")
    elif counts["blunder"] >= 3:
        lines.append("Plusieurs gaffes dans cette partie : la priorité absolue, c'est de vérifier la sécurité de tes pièces "
                     "avant chaque coup (échecs, captures, menaces).")
    first_big = next((m for m in user if m.classification in ("blunder", "mistake", "miss")), None)
    if first_big:
        lines.append(f"Le tournant : {first_big.move_number}{'.' if first_big.color == 'white' else '...'}"
                     f"{_sanfr(first_big.san)} ({CLASS_FR[first_big.classification].lower()}).")
    if top:
        lines.append("Les thèmes à travailler d'après cette partie : " + ", ".join(THEMES.get(t, t) for t in top) + ".")
    # Ouverture : roque ?
    castled = any(chess.Board(m.fen_before).is_castling(chess.Move.from_uci(m.uci)) for m in user)
    if not castled and len(user) >= 15:
        lines.append("Tu n'as pas roqué dans cette partie : pense à mettre ton roi à l'abri dans les 10 premiers coups.")
    return {"text": " ".join(lines), "top_themes": top, "accuracy": acc, "counts": counts}
