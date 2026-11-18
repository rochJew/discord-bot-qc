# ♞ Chess Coach — de 430 à 1000 Elo

Application Windows d'entraînement aux échecs : elle récupère tes parties Chess.com (ou les lit
directement à l'écran), les analyse avec **Stockfish**, t'explique tes erreurs en français simple,
suit ta progression et te crée des exercices à partir de **tes propres erreurs**.

## Installation (Windows)

**Option 1 — exécutable prêt à l'emploi.** Chaque modification du dossier `chess-coach/` lance le
workflow GitHub Actions « Chess Coach — build Windows ». Il exécute les tests sur Windows, construit
`ChessCoach.exe` avec Stockfish inclus et publie l'artefact **ChessCoach-Windows** (onglet *Actions*
du dépôt → dernière exécution → *Artifacts*). Dézippe-le, puis lance `ChessCoach.exe`.

**Option 2 — construire soi-même.** Installe Python 3.11+ (python.org, coche « Add to PATH »), puis
double-clique sur `build_windows.bat`. Le script télécharge les dépendances et Stockfish, puis
produit `dist\ChessCoach\ChessCoach.exe`.

**Option 3 — lancer depuis les sources.** `run_windows.bat` (ou `pip install -r requirements.txt`
puis `python main.py`). Stockfish peut ensuite être téléchargé depuis *Paramètres*.

## Premiers pas

1. **Paramètres** : indique ton pseudo Chess.com. Si Stockfish n'est pas trouvé, clique sur
   « Télécharger Stockfish ». Tu peux aussi ajouter une clé API Anthropic (optionnel, voir plus bas).
2. **Mes parties** → « Récupérer mes dernières parties » → « Analyser les 5 dernières ».
3. L'analyse s'ouvre automatiquement sur ta première erreur.
4. **Entraînement** → série de 10 exercices ciblés sur tes points faibles.
5. **Tableau de bord** : ta progression, tes erreurs fréquentes, les notions maîtrisées.

La boucle conseillée : *jouer (10-15 min) → analyser → comprendre → s'entraîner*.

## Fonctionnalités

| Module | Ce qu'il fait |
|---|---|
| **Import Chess.com** | API publique officielle (`api.chess.com/pub`) : aucune connexion ni mot de passe. Récupère le PGN, ta couleur, ton Elo et le résultat. |
| **PGN** | Coller un PGN ou ouvrir un fichier `.pgn`. |
| **Capture d'écran** | Repère l'échiquier à l'écran, apprend le style des pièces depuis la position de départ, puis reconstitue les coups (les règles du jeu corrigent les erreurs de lecture). **Aucune aide n'est affichée pendant la partie** (fair-play) : l'analyse ne démarre qu'après « Terminer et analyser ». |
| **Analyse** | Stockfish évalue chaque position. Chaque coup est classé (meilleur, excellent, bon, imprécision, erreur, occasion manquée, gaffe) selon la perte de chances de gain, avec la même formule que Lichess. |
| **Détection des motifs** | Pièce laissée en prise, menace ignorée, fourchette permise ou ratée, clouage, enfilade, mat permis ou raté (dont le mat du couloir), capture gratuite non prise, promotion, et principes d'ouverture (dame sortie trop tôt, même pièce jouée deux fois, cavalier au bord, roi qui bouge sans roquer, centre négligé, roque oublié). |
| **Revue interactive** | Échiquier avec flèches (rouge : ton coup, vert : le meilleur, bleu : la réponse adverse), barre et graphique d'évaluation, liste des coups annotés, bouton « Erreur suivante », lecture de la meilleure suite ou de la punition adverse, exploration libre (tu joues des coups et le moteur répond). |
| **Coach** | Pour chaque erreur : ce qui s'est passé, pourquoi c'est une erreur, ce que l'adversaire pouvait faire, le meilleur coup et son idée, ce qu'il fallait chercher, et le réflexe à retenir. |
| **Coach IA (optionnel)** | Avec une clé API Anthropic, Claude reformule ces explications dans un style plus naturel, rédige un bilan de partie et répond à tes questions sur la position. Il ne reçoit que des faits vérifiés par Stockfish et n'a pas le droit d'inventer des variantes. |
| **Entraînement** | Exercices « trouve mieux » tirés de tes erreurs, plus une banque thématique générée et vérifiée par Stockfish (mats, fourchettes, clouages, enfilades, captures, menaces, finales) et des quiz d'ouverture. Trois niveaux d'indice et une répétition espacée : un exercice raté revient vite. |
| **Leçons** | 14 leçons, de 400 à 1000 Elo : méthode Échecs-Captures-Menaces, valeur des pièces, ouverture, répertoire simple, centre, fourchette, clouage, enfilade, mats de base, mat avec dame/tour, sécurité du roi, finales de pions, plan, routine de partie. |
| **Tableau de bord** | Parties analysées, précision, gaffes par partie, Elo Chess.com, niveau de jeu estimé, courbes de progression, erreurs fréquentes, maîtrise de chaque notion, séance du jour. |

## Architecture

```
chess-coach/
├── main.py                 point d'entrée (PySide6)
├── coach/
│   ├── engine.py           Stockfish via UCI (python-chess)
│   ├── analysis.py         analyse d'une partie : évaluation, classification, précision
│   ├── motifs.py           détection des motifs tactiques et stratégiques
│   ├── chessutil.py        échange statique (SEE), pièces en prise, notation française
│   ├── explain.py          explications pédagogiques (sans IA, à partir des faits du moteur)
│   ├── llm.py              coach IA (Claude) : reformulation, bilan, questions
│   ├── chesscom.py         API publique Chess.com
│   ├── vision.py           détection d'échiquier, reconnaissance des pièces, reconstitution des coups
│   ├── db.py               SQLite : parties, coups, motifs, exercices, tentatives
│   ├── progress.py         statistiques, maîtrise des notions, Elo estimé
│   ├── training.py         sélection des exercices, vérification des coups, répétition espacée
│   ├── lessons.py          programme de cours
│   ├── stockfish_dl.py     téléchargement automatique de Stockfish
│   ├── service.py          « analyser et enregistrer » (utilisé par l'interface et les tests)
│   ├── data/puzzles.json   banque d'exercices (générée par tools/generate_puzzles.py)
│   └── ui/                 interface : board, review, games, training_page, lessons_page,
│                           screen_page, dashboard, settings_page, main_window, theme
├── tools/generate_puzzles.py
└── tests/                  23 tests (moteur, motifs, analyse, vision, base, entraînement, interface)
```

Choix techniques :

- **Python + PySide6 (Qt)** : une vraie application de bureau Windows, avec un rendu rapide de
  l'échiquier. python-chess fournit les règles et le protocole UCI ; OpenCV sert à la vision.
- **Fiabilité de l'analyse** : une position est analysée une seule fois (l'évaluation après le
  coup N est celle avant le coup N+1), à profondeur fixe avec une limite de temps. La classification
  repose sur la perte de *chances de gain* plutôt que sur les centipions, ce qui évite de punir un
  petit écart dans une position déjà gagnée. Permettre un mat forcé évitable est toujours une gaffe.
- **Explications ancrées** : tout le texte vient des lignes calculées par Stockfish et des
  détecteurs de motifs. L'IA ne fait que reformuler ces faits.
- **Données locales** : tout est stocké dans `%APPDATA%\ChessCoach` (paramètres, base SQLite,
  calibration de la vision). La clé API ne quitte ton PC que pour les appels à l'IA.

## Développement

```bash
pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q tests      # Stockfish doit être installé
python tools/generate_puzzles.py <chemin_stockfish> 10    # (re)générer la banque d'exercices
```

## Limites connues

- La capture d'écran marche mieux avec un échiquier aux couleurs unies (le vert par défaut de
  Chess.com ou le marron). Pour les échiquiers texturés, utilise « Sélectionner à la main ».
  Il faut calibrer une fois depuis la position de départ.
- Le « niveau de jeu estimé » est une estimation à partir de ta précision et de tes gaffes, pas
  un vrai classement.
