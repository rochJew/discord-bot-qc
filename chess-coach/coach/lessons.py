"""Programme de cours : de 400 à 1000 Elo, notion par notion.

Chaque leçon contient des étapes ; chaque étape a un texte et une position
(FEN, éventuellement une suite de coups à rejouer) avec des flèches.
Flèches : (case_départ, case_arrivée, couleur) — couleurs : "g" vert, "r" rouge, "b" bleu, "y" jaune.
"""
from __future__ import annotations

from dataclasses import dataclass, field

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


@dataclass
class Step:
    text: str
    fen: str = START
    moves: list[str] = field(default_factory=list)   # coups SAN (anglais) à rejouer depuis fen
    arrows: list[tuple[str, str, str]] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


@dataclass
class Lesson:
    id: str
    title: str
    level: str          # "400-600", "600-800", "800-1000"
    theme: str          # thème d'entraînement associé
    summary: str
    steps: list[Step]
    key_points: list[str]


LESSONS: list[Lesson] = [
    Lesson(
        "ecm", "La méthode Échecs – Captures – Menaces", "400-600", "menaces",
        "LE réflexe qui fait le plus progresser : vérifier la position avant chaque coup.",
        [
            Step("À 400 Elo, la majorité des parties se décident sur une pièce laissée en prise ou une menace pas vue. "
                 "La bonne nouvelle : ça se corrige avec une routine simple, à faire à CHAQUE coup."),
            Step("Étape 1 – Après le coup de ton adversaire, demande-toi : « Qu'est-ce qu'il veut faire ? ». "
                 "Ici, les Blancs viennent de jouer Cg5. Le cavalier et le fou visent tous les deux f7, une case défendue "
                 "seulement par le roi. Menace : Cxf7, qui attaque la dame et la tour en même temps !",
                 "r1bqkb1r/pppp1ppp/2n2n2/4p1N1/2B1P3/8/PPPP1PPP/RNBQK2R b KQkq - 5 4",
                 arrows=[("g5", "f7", "r"), ("c4", "f7", "r")], highlights=["f7"]),
            Step("Étape 2 – Seulement ensuite, cherche TES coups en commençant par les plus forcés : "
                 "les Échecs, puis les Captures, puis les Menaces. Ici, d5 ! bloque la diagonale du fou et contre-attaque.",
                 "r1bqkb1r/pppp1ppp/2n2n2/4p1N1/2B1P3/8/PPPP1PPP/RNBQK2R b KQkq - 5 4",
                 arrows=[("d7", "d5", "g"), ("d5", "c4", "b")]),
            Step("Étape 3 – Avant de lâcher ta pièce : « Après mon coup, quels échecs, captures et menaces aura mon "
                 "adversaire ? ». Si l'une de ses réponses te fait perdre du matériel, cherche un autre coup. "
                 "C'est le « blunder check » : 10 secondes qui sauvent des dizaines de parties."),
        ],
        ["Après chaque coup adverse : « Qu'est-ce qu'il menace ? »",
         "Pour toi : Échecs, puis Captures, puis Menaces.",
         "Avant de jouer : vérifie les réponses forcées de l'adversaire."],
    ),
    Lesson(
        "valeur", "Valeur des pièces et pièces en prise", "400-600", "piece_en_prise",
        "Compter les attaquants et les défenseurs pour ne plus rien donner gratuitement.",
        [
            Step("Valeurs à connaître par cœur : pion = 1, cavalier = 3, fou = 3, tour = 5, dame = 9. "
                 "Le roi n'a pas de prix : on ne peut pas le perdre."),
            Step("Une pièce est « en prise » quand elle peut être capturée sans que tu récupères autant. "
                 "Ici, Cxe5 ?? gagne un pion… mais dxe5 reprend le cavalier : tu as donné 3 pour 1.",
                 "rnbqkbnr/ppp2ppp/3p4/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",
                 arrows=[("f3", "e5", "r"), ("d6", "e5", "r")], highlights=["e5"]),
            Step("La règle du comptage : compte combien de pièces ATTAQUENT une case et combien la DÉFENDENT. "
                 "Si les attaquants sont plus nombreux, la pièce sur cette case tombe (en commençant par prendre avec "
                 "la pièce la moins chère). Ici le pion e5 est attaqué 1 fois et défendu 1 fois : on ne gagne rien.",
                 "rnbqkbnr/ppp2ppp/3p4/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 3",
                 arrows=[("f3", "e5", "r"), ("d6", "e5", "g")]),
            Step("Attention aux échanges : prendre une pièce de 3 avec ta dame (9) est une catastrophe si elle est "
                 "défendue. On capture toujours avec la pièce la moins chère d'abord."),
        ],
        ["Pion 1, Cavalier 3, Fou 3, Tour 5, Dame 9.",
         "Compte attaquants et défenseurs avant chaque capture.",
         "Une pièce non protégée est une cible : protège-la ou mets-la à l'abri."],
    ),
    Lesson(
        "principes", "Les 3 règles d'or de l'ouverture", "400-600", "ouverture",
        "Centre, développement, roque : le plan des 10 premiers coups.",
        [
            Step("Règle 1 : occupe le centre avec un pion (e4 ou d4). Le centre, c'est le milieu du terrain : "
                 "tes pièces y sont plus fortes et vont partout plus vite.",
                 START, moves=["e4"], arrows=[("e4", "d5", "b"), ("e4", "f5", "b")]),
            Step("Règle 2 : sors tes pièces mineures (cavaliers et fous) vers le centre, une nouvelle pièce à chaque coup. "
                 "Ne bouge pas deux fois la même pièce sans raison.",
                 START, moves=["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5"]),
            Step("Règle 3 : roque tôt. Le roque met ton roi à l'abri ET met ta tour en jeu. "
                 "Objectif : avoir roqué avant le 10e coup.",
                 START, moves=["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "d3", "Nf6", "O-O"]),
            Step("À éviter : sortir la dame trop tôt (elle se fait chasser), pousser les pions du bord, "
                 "bouger le roi sans roquer, et laisser une pièce au fond quand les autres sont sorties."),
        ],
        ["Un pion au centre.", "Une nouvelle pièce à chaque coup.", "Roque avant le 10e coup.",
         "La dame sort APRÈS les cavaliers et les fous."],
    ),
    Lesson(
        "italienne", "Un répertoire simple : l'Italienne (Blancs) et 1…e5 / 1…d5 (Noirs)", "400-600", "ouverture",
        "Des ouvertures faciles qui respectent les principes et évitent les pièges.",
        [
            Step("Avec les Blancs, l'Italienne : 1.e4 e5 2.Cf3 Cc6 3.Fc4. Le fou vise f7, la case faible des Noirs. "
                 "Puis c3, d3, roque, et tes pièces sont parfaitement placées.",
                 START, moves=["e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d3", "d6", "O-O", "O-O"],
                 arrows=[("c4", "f7", "b")]),
            Step("Avec les Noirs contre 1.e4 : réponds 1…e5, puis sors Cc6, Cf6, un fou, et roque. "
                 "Surveille toujours f7 : Dh5 + Fc4 = menace de mat !",
                 START, moves=["e4", "e5", "Bc4", "Nc6", "Qh5"], arrows=[("h5", "f7", "r"), ("c4", "f7", "r")]),
            Step("La bonne défense : 3…g6 chasse la dame (ou 3…De7 protège f7). Surtout pas 3…Cf6 ?? qui perd sur Dxf7#.",
                 START, moves=["e4", "e5", "Bc4", "Nc6", "Qh5", "g6"], arrows=[("g6", "h5", "g")]),
            Step("Avec les Noirs contre 1.d4 : joue 1…d5, puis Cf6, e6, Fe7 et le roque. Une structure solide, "
                 "facile à jouer, sans piège à apprendre par cœur.",
                 START, moves=["d4", "d5", "c4", "e6", "Nc3", "Nf6", "Bg5", "Be7", "e3", "O-O"]),
        ],
        ["Blancs : e4, Cf3, Fc4, c3, d3, roque.", "Noirs : …e5 contre e4, …d5 contre d4.",
         "Toujours surveiller f7 (f2 pour les Blancs)."],
    ),
    Lesson(
        "centre", "Le contrôle du centre", "600-800", "centre",
        "Pourquoi les cases d4, e4, d5, e5 valent de l'or.",
        [
            Step("Un cavalier au centre contrôle 8 cases ; dans un coin, seulement 2. Plus tes pièces sont "
                 "centralisées, plus elles ont d'options.", "8/8/8/4N3/8/8/8/N3K2k w - - 0 1",
                 arrows=[("e5", "d7", "g"), ("e5", "f7", "g"), ("e5", "g6", "g"), ("e5", "g4", "g"),
                         ("e5", "f3", "g"), ("e5", "d3", "g"), ("e5", "c4", "g"), ("e5", "c6", "g"),
                         ("a1", "b3", "r"), ("a1", "c2", "r")]),
            Step("Le duo de pions e4 + d4 est l'idéal : il chasse les pièces adverses et donne de l'espace à tes pièces.",
                 START, moves=["e4", "Nf6", "e5", "Nd5", "d4"], arrows=[("d4", "e5", "b")]),
            Step("Quand l'adversaire occupe le centre, attaque-le avec tes pions (…c5, …e5, …f6) et tes pièces. "
                 "Ne joue pas a3, h3, a6, h6 « pour voir » : ces coups ne font rien pour le centre."),
        ],
        ["Pièces au centre = pièces actives.", "Un cavalier sur le bord, c'est un cavalier mort.",
         "Attaque le centre adverse avec tes pions."],
    ),
    Lesson(
        "fourchette", "La fourchette (attaque double)", "400-600", "fourchette",
        "Attaquer deux pièces à la fois : l'adversaire ne peut en sauver qu'une.",
        [
            Step("Le cavalier est le roi des fourchettes. Ici Cc7+ attaque le roi ET la tour : le roi doit bouger, "
                 "et la tour tombe.", "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1",
                 arrows=[("d5", "c7", "g"), ("c7", "e8", "r"), ("c7", "a8", "r")]),
            Step("Même un pion peut faire une fourchette : d5 attaque le cavalier et le fou.",
                 "4k3/8/2n1b3/8/3P4/8/8/4K3 w - - 0 1",
                 arrows=[("d4", "d5", "g"), ("d5", "c6", "r"), ("d5", "e6", "r")]),
            Step("La dame fait des fourchettes dans toutes les directions : Da4+ donne échec et attaque la tour en h4.",
                 "4k3/8/8/8/7r/8/8/3QK3 w - - 0 1",
                 arrows=[("d1", "a4", "g"), ("a4", "e8", "r"), ("a4", "h4", "r")]),
            Step("Pour repérer une fourchette : cherche deux pièces adverses non protégées (ou le roi + une grosse "
                 "pièce) et demande-toi quelle pièce pourrait les attaquer en même temps."),
        ],
        ["Cibles idéales : roi + dame, roi + tour, dame + tour.",
         "Le cavalier attaque des cases de couleurs différentes : redoutable.",
         "Ne laisse pas ton roi et ta dame à « un saut de cavalier » de la même case."],
    ),
    Lesson(
        "clouage", "Le clouage", "600-800", "clouage",
        "Une pièce qui ne peut pas bouger sans exposer plus important derrière elle.",
        [
            Step("Clouage absolu : Fb5 cloue le cavalier c6 sur le roi. Le cavalier n'a PAS LE DROIT de bouger "
                 "(il exposerait son roi).", "4k3/8/2n5/8/8/3B4/8/4K3 w - - 0 1",
                 arrows=[("d3", "b5", "g"), ("b5", "e8", "r")]),
            Step("Clouage relatif : Te1 cloue le cavalier e5 devant la dame e8. Il peut bouger, mais la dame tombe.",
                 "4q1k1/8/8/4n3/8/8/8/R5K1 w - - 0 1", arrows=[("a1", "e1", "g"), ("e1", "e8", "r")]),
            Step("Une pièce clouée est une cible : attaque-la une deuxième fois (par exemple avec un pion) "
                 "et elle ne pourra pas s'échapper."),
        ],
        ["Fous, tours et dames clouent.", "Attaque une pièce clouée avec un pion !",
         "Évite d'aligner ton roi ou ta dame derrière une de tes pièces sur une ligne ouverte."],
    ),
    Lesson(
        "enfilade", "L'enfilade", "600-800", "enfilade",
        "Le clouage à l'envers : la grosse pièce devant, la victime derrière.",
        [
            Step("Ff2+ donne échec au roi d4. Le roi doit bouger… et le fou prend la dame b6 qui était derrière.",
                 "8/8/1q6/8/3k3B/8/8/4K3 w - - 0 1", arrows=[("h4", "f2", "g"), ("f2", "b6", "r")]),
            Step("Avec une tour, c'est pareil sur les colonnes et les rangées. Les finales de tours sont pleines "
                 "d'enfilades : vérifie toujours que ton roi et ta tour ne sont pas alignés."),
        ],
        ["Échec + pièce derrière le roi = enfilade.", "Méfie-toi des alignements roi-dame, roi-tour."],
    ),
    Lesson(
        "mats", "Les mats à connaître", "400-600", "mat",
        "Le mat du couloir, le Coup du Berger et les mats de base.",
        [
            Step("Le mat du couloir : le roi est enfermé derrière ses propres pions. Td8 est mat !",
                 "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1", arrows=[("d1", "d8", "g")]),
            Step("La parade : faire « un trou » (on dit un luft) avec h3 ou g3, pour que ton roi ait une case de sortie. "
                 "Fais-le quand c'est calme, avant que la menace n'arrive."),
            Step("Le Coup du Berger : la dame et le fou visent f7. Dxf7 est mat. Ça arrive TRÈS souvent sous 600 !",
                 START, moves=["e4", "e5", "Bc4", "Nc6", "Qh5", "Nf6", "Qxf7#"], arrows=[("c4", "f7", "r")]),
            Step("Le mat dame + roi : la dame donne le mat protégée par son roi. Retiens ce dessin.",
                 "k7/1Q6/1K6/8/8/8/8/8 b - - 0 1", arrows=[("b6", "b7", "g")]),
            Step("Attention au PAT : si le roi adverse n'est pas en échec mais n'a aucun coup légal, c'est nulle ! "
                 "Ici, aux Noirs de jouer : pat. Laisse toujours une case au roi tant que tu n'es pas prêt à mater.",
                 "k7/2Q5/1K6/8/8/8/8/8 b - - 0 1"),
        ],
        ["Fais un luft (h3/g3) pour éviter le mat du couloir.", "Surveille f7/f2 dans l'ouverture.",
         "Avant de donner un coup « tranquille » quand tu gagnes, vérifie le pat."],
    ),
    Lesson(
        "mat_dame", "Mater avec la dame (ou la tour) et le roi", "600-800", "finale",
        "La technique pour conclure quand tu as gagné tout le matériel.",
        [
            Step("Technique de la boîte : place ta dame à un saut de cavalier du roi adverse. Elle réduit ses cases. "
                 "Puis suis-le avec ta dame toujours à un saut de cavalier, jusqu'à le coller au bord.",
                 "8/8/8/3k4/8/8/8/Q3K3 w - - 0 1", arrows=[("a1", "c3", "g")]),
            Step("Quand le roi est au bord, STOP avec la dame : amène ton roi pour la protéger, puis mate. "
                 "Avec une tour, même idée : la tour coupe le roi, ton roi vient en face, et échec = mat.",
                 "4k3/R7/4K3/8/8/8/8/8 w - - 0 1", arrows=[("a7", "a8", "g")]),
        ],
        ["Dame à un saut de cavalier du roi.", "Au bord : ramène ton roi.", "Attention au pat !"],
    ),
    Lesson(
        "roi", "La sécurité du roi", "600-800", "securite_roi",
        "Roquer, garder ses pions devant le roi, repérer les attaques.",
        [
            Step("Le « mat du sot » : les Blancs ont poussé f3 et g4, ouvrant la diagonale de leur roi. "
                 "Dh4 est mat en 2 coups seulement !",
                 START, moves=["f3", "e5", "g4", "Qh4#"], arrows=[("h4", "e1", "r")]),
            Step("Après le roque, garde les pions devant ton roi (f2, g2, h2) le plus longtemps possible. "
                 "Chaque poussée crée un trou que les pièces adverses peuvent utiliser.",
                 "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQ1RK1 w - - 4 6"),
            Step("Si ton adversaire n'a pas roqué et que le centre s'ouvre, attaque ! Ouvre les colonnes devant son roi "
                 "et amène tes pièces : un roi au centre est une cible."),
        ],
        ["Roque tôt.", "Ne pousse pas f, g, h devant ton roi sans raison.",
         "Roi adverse au centre = ouvre le jeu."],
    ),
    Lesson(
        "finales_pions", "Les finales de pions : carré et opposition", "800-1000", "finale",
        "Savoir si un pion va à dame et comment escorter le sien.",
        [
            Step("La règle du carré : trace un carré du pion jusqu'à sa case de promotion. Si le roi adverse peut entrer "
                 "dans le carré, il rattrape le pion. Ici, le roi e1 entre dans le carré du pion a4 avec Rd2 : il le rattrape.",
                 "7k/8/8/8/p7/8/8/4K3 w - - 0 1", arrows=[("e1", "d2", "g")], highlights=["a4", "d4", "a1", "d1"]),
            Step("Ici le roi g1 est trop loin : le pion va à dame. En finale, compte les coups avant de bouger !",
                 "7k/8/8/8/p7/8/8/6K1 w - - 0 1", highlights=["a4", "d4", "a1", "d1"]),
            Step("L'opposition : les rois face à face avec une case entre eux. Celui qui N'EST PAS au trait gagne "
                 "l'opposition. Pour faire promouvoir un pion, ton roi doit passer DEVANT ton pion.",
                 "8/8/4k3/8/4K3/4P3/8/8 w - - 0 1", arrows=[("e4", "e5", "b")]),
        ],
        ["Règle du carré pour les pions passés.", "Le roi devant le pion, pas derrière.",
         "En finale, le roi est une pièce d'attaque : centralise-le."],
    ),
    Lesson(
        "plan", "Construire un plan au lieu de jouer au hasard", "800-1000", "calcul",
        "Que faire quand il n'y a pas de tactique ?",
        [
            Step("Question 1 : Quelle est ma pièce la moins active ? Améliore-la (un fou bloqué, une tour sans colonne, "
                 "un cavalier sur le bord)."),
            Step("Question 2 : Où sont les faiblesses de mon adversaire ? Un pion isolé, un roi mal protégé, une case "
                 "qu'aucun de ses pions ne peut défendre. Vise-les avec plusieurs pièces."),
            Step("Question 3 : Que veut mon adversaire ? Si tu sais ce qu'il prépare, tu peux l'empêcher avant que ça "
                 "devienne dangereux (c'est ce qu'on appelle la prophylaxie)."),
            Step("Exemple : les deux camps ont roqué, la tour f1 n'a rien à faire. Plan simple : Te1 (soutenir le centre), "
                 "Cbd2-f1-g3 pour amener le cavalier vers le roi adverse.",
                 "r1bq1rk1/pppp1ppp/2n2n2/2b1p3/2B1P3/2PP1N2/PP3PPP/RNBQ1RK1 w - - 1 6",
                 arrows=[("f1", "e1", "g"), ("b1", "d2", "b")]),
        ],
        ["Améliore ta pire pièce.", "Vise une faiblesse.", "Demande-toi ce que veut l'adversaire."],
    ),
    Lesson(
        "routine", "Ta routine de partie (temps et mental)", "400-600", "menaces",
        "Jouer en 10 minutes sans gaffer : la méthode concrète.",
        [
            Step("Joue des parties de 10 ou 15 minutes (pas de blitz pour progresser) : tu as le temps de vérifier "
                 "chaque coup. Le blitz et le bullet entretiennent les mauvaises habitudes."),
            Step("Routine à chaque coup : 1) Qu'est-ce qu'il menace ? 2) Échecs, captures, menaces pour moi. "
                 "3) Je choisis un coup. 4) Blunder check : après mon coup, qu'est-ce qu'il peut faire ?"),
            Step("Après chaque partie, analyse-la ici, lis les explications du coach, et fais les exercices tirés de tes "
                 "erreurs. C'est la boucle la plus efficace : jouer → comprendre → s'entraîner."),
            Step("Si tu perds deux parties de suite, fais une pause : jouer frustré coûte des points. "
                 "Et rappelle-toi : chaque gaffe évitée, c'est des Elo gagnés."),
        ],
        ["Cadence 10-15 minutes.", "Blunder check avant chaque coup.", "Analyse chaque partie jouée."],
    ),
]


def lesson_by_id(lid: str) -> Lesson | None:
    return next((l for l in LESSONS if l.id == lid), None)


def recommended_lessons(weak_themes: list[str], done: set[str]) -> list[Lesson]:
    """Leçons conseillées : d'abord celles des thèmes faibles, puis l'ordre du programme."""
    ordered = [l for t in weak_themes for l in LESSONS if l.theme == t and l.id not in done]
    for l in LESSONS:
        if l.id not in done and l not in ordered:
            ordered.append(l)
    return ordered
