"""Coach IA (Claude) : reformule les faits du moteur en explications pédagogiques.

L'IA ne calcule rien elle-même : on lui transmet uniquement des faits vérifiés par
Stockfish (coups, lignes, évaluations, motifs détectés) et on lui interdit
d'inventer d'autres variantes. Sans clé API, l'application utilise les
explications générées localement (explain.py).
"""
from __future__ import annotations

import chess

from .analysis import CLASS_FR, MoveAnalysis
from .chessutil import san_fr
from .explain import explain

MODEL = "claude-opus-5-5"

SYSTEM_PROMPT = """Tu es un coach d'échecs francophone chaleureux et très pédagogue, qui s'adresse à un joueur \
d'environ {elo} Elo sur Chess.com dont l'objectif est d'atteindre {target} Elo.

Ton style : simple, naturel, direct, comme un streamer pédagogue qui commente une partie avec bienveillance. \
Tu tutoies. Tu utilises des images concrètes, des phrases courtes, un peu d'humour, jamais de condescendance. \
Tout terme technique (clouage, fourchette, pion passé, développement, tempo...) est expliqué en quelques mots \
la première fois qu'il apparaît.

Règles absolues :
- Tu t'appuies UNIQUEMENT sur les faits fournis par le moteur (coups, lignes, évaluations, motifs). \
N'invente jamais d'autre variante ni de coup qui n'apparaît pas dans les données.
- Utilise la notation française (R roi, D dame, T tour, F fou, C cavalier), comme dans les données.
- Ne donne pas d'évaluation chiffrée en centipions ; parle en mots (« tu es mieux », « c'est perdu »...).
- Ton but est d'apprendre au joueur à RÉFLÉCHIR : explique le raisonnement, les questions à se poser, \
pas seulement la bonne réponse.
"""

MOVE_PROMPT = """Voici un coup à expliquer.

Position avant le coup (FEN) : {fen}
Camp du joueur : {color}
Coup joué : {played} — classé « {cls} » (chances de gain : {wb:.0f}% avant, {wa:.0f}% après)
Meilleur coup selon Stockfish : {best}
Ligne principale du meilleur coup : {best_line}
Meilleure réponse adverse après le coup joué : {reply_line}
Phase de jeu : {phase}
Motifs détectés : {motifs}

Brouillon d'explication (faits fiables, à reformuler et enrichir) :
{draft}

Rédige l'explication avec exactement ces intertitres en gras, 2 à 4 phrases chacun :
**Ce qui s'est passé**
**Pourquoi c'est une erreur**
**Ce que ton adversaire pouvait faire**
**Le meilleur coup et son idée**
**Ce que tu devais chercher dans cette position**
**Le réflexe pour ne plus refaire cette erreur**
Termine par une phrase d'encouragement courte."""


class AICoach:
    def __init__(self, api_key: str, elo: int = 430, target: int = 1000):
        import anthropic  # import paresseux : l'app fonctionne sans le paquet

        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key or None)
        self.system = SYSTEM_PROMPT.format(elo=elo, target=target)

    def _call(self, messages: list[dict], max_tokens: int = 4000) -> str:
        anthropic = self._anthropic
        try:
            resp = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                system=self.system,
                messages=messages,
                output_config={"effort": "medium"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise RuntimeError("Clé API Anthropic invalide (voir Paramètres).") from exc
        except anthropic.RateLimitError as exc:
            raise RuntimeError("Trop de requêtes vers l'IA, réessaie dans un moment.") from exc
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"Erreur de l'API IA ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise RuntimeError("Impossible de joindre l'IA (connexion internet ?).") from exc
        if resp.stop_reason == "refusal":
            raise RuntimeError("L'IA n'a pas pu répondre à cette demande.")
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text:
            raise RuntimeError("Réponse vide de l'IA.")
        return text

    def explain_move(self, m: MoveAnalysis) -> str:
        board = chess.Board(m.fen_before)
        draft = explain(m)
        draft_txt = "\n".join(f"- {k}: {v}" for k, v in draft.items() if v)
        motifs = ", ".join(f"{mo['theme']}/{mo['kind']} {mo.get('facts', {})}" for mo in m.motifs) or "aucun"
        prompt = MOVE_PROMPT.format(
            fen=m.fen_before,
            color="Blancs" if m.color == "white" else "Noirs",
            played=san_fr(m.san),
            cls=CLASS_FR[m.classification],
            wb=m.win_before, wa=m.win_after,
            best=san_fr(m.best_san),
            best_line=" ".join(san_fr(x) for x in m.best_pv_san[:6]) or "-",
            reply_line=" ".join(san_fr(x) for x in m.reply_pv_san[:6]) or "-",
            phase=m.phase,
            motifs=motifs,
            draft=draft_txt,
        )
        _ = board
        return self._call([{"role": "user", "content": prompt}])

    def chat(self, history: list[dict], context: str) -> str:
        """Discussion libre avec le coach à propos d'une position / partie.

        `history` : liste de {"role": "user"|"assistant", "content": str}.
        `context` : faits moteur sur la position courante, ajoutés au premier message.
        """
        if not history:
            raise ValueError("Historique vide")
        msgs = [dict(h) for h in history]
        msgs[0] = {"role": "user", "content": f"Contexte (données du moteur, fiables) :\n{context}\n\nQuestion : {msgs[0]['content']}"}
        return self._call(msgs, max_tokens=3000)

    def game_review(self, summary_text: str, key_moments: list[MoveAnalysis]) -> str:
        moments = "\n".join(
            f"- {m.move_number}{'.' if m.color == 'white' else '...'}{san_fr(m.san)} ({CLASS_FR[m.classification]}), "
            f"meilleur : {san_fr(m.best_san)}, motifs : {', '.join(mo['kind'] for mo in m.motifs) or '-'}"
            for m in key_moments[:6]
        )
        prompt = (f"Bilan chiffré de la partie : {summary_text}\n\nMoments clés :\n{moments}\n\n"
                  "Fais un bilan de la partie en 3 parties : **Ce qui a bien marché**, **Ce qui a coûté la partie** "
                  "(les 2 ou 3 leçons principales), **Ton plan d'entraînement pour la semaine** (3 actions concrètes). "
                  "Maximum 250 mots.")
        return self._call([{"role": "user", "content": prompt}])


def markdown_to_html(text: str) -> str:
    """Conversion minimale **gras** / paragraphes -> HTML pour QTextBrowser."""
    import html
    import re

    out = []
    for para in text.split("\n"):
        p = html.escape(para.strip(), quote=False)
        if not p:
            continue
        p = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", p)
        if p.startswith("- "):
            p = "• " + p[2:]
        if p.startswith("#"):
            p = "<b>" + p.lstrip("# ") + "</b>"
        out.append(f"<p>{p}</p>")
    return "\n".join(out)
