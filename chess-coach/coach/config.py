"""Paramètres de l'application, stockés en JSON dans le dossier utilisateur."""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def app_dir() -> Path:
    """Dossier de données (%APPDATA%/ChessCoach sous Windows)."""
    override = os.environ.get("CHESS_COACH_HOME")
    if override:
        base = Path(override)
    elif sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home())) / "ChessCoach"
    else:
        base = Path.home() / ".chess_coach"
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class Settings:
    chesscom_username: str = ""
    stockfish_path: str = ""
    anthropic_api_key: str = ""
    use_ai_coach: bool = True
    analysis_depth: int = 16
    analysis_time: float = 1.0  # secondes max par position
    engine_threads: int = 2
    current_elo: int = 430
    target_elo: int = 1000
    extra: dict = field(default_factory=dict)

    @classmethod
    def path(cls) -> Path:
        return app_dir() / "settings.json"

    @classmethod
    def load(cls) -> "Settings":
        p = cls.path()
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
                return cls(**known)
            except (OSError, ValueError, TypeError):
                pass
        return cls()

    def save(self) -> None:
        self.path().write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")

    def api_key(self) -> str:
        return self.anthropic_api_key.strip() or os.environ.get("ANTHROPIC_API_KEY", "")


def find_stockfish(settings: Settings | None = None) -> str | None:
    """Cherche un exécutable Stockfish : paramètres, dossier de l'app, PATH."""
    candidates: list[Path] = []
    if settings and settings.stockfish_path:
        candidates.append(Path(settings.stockfish_path))
    exe_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for base in (exe_dir, Path(sys.executable).parent, app_dir()):
        for name in ("stockfish.exe", "stockfish", "engine/stockfish.exe", "engine/stockfish"):
            candidates.append(base / name)
    for c in candidates:
        if c.is_file():
            return str(c)
    for name in ("stockfish", "stockfish.exe"):
        found = shutil.which(name)
        if found:
            return found
    for p in ("/usr/games/stockfish", "/usr/local/bin/stockfish"):
        if Path(p).is_file():
            return p
    return None
