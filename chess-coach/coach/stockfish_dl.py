"""Téléchargement automatique de Stockfish (version officielle, GitHub)."""
from __future__ import annotations

import io
import os
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from .config import app_dir

BASE = "https://github.com/official-stockfish/Stockfish/releases/latest/download/"


def _assets() -> list[str]:
    if sys.platform.startswith("win"):
        return ["stockfish-windows-x86-64-avx2.zip", "stockfish-windows-x86-64.zip"]
    if sys.platform == "darwin":
        return ["stockfish-macos-m1-apple-silicon.tar" if platform.machine() == "arm64" else "stockfish-macos-x86-64.tar"]
    return ["stockfish-ubuntu-x86-64-avx2.tar", "stockfish-ubuntu-x86-64.tar"]


def _cpu_has_avx2() -> bool:
    try:
        if sys.platform.startswith("linux"):
            return "avx2" in Path("/proc/cpuinfo").read_text()
    except OSError:
        pass
    return True  # la plupart des PC récents ; repli automatique si l'exécutable échoue


def download_stockfish(progress=None) -> str:
    """Télécharge et installe Stockfish dans le dossier de l'application. Retourne le chemin."""
    dest_dir = app_dir() / "engine"
    dest_dir.mkdir(parents=True, exist_ok=True)
    assets = _assets()
    if not _cpu_has_avx2():
        assets = assets[1:] or assets
    last_err = None
    for asset in assets:
        try:
            data = _download(BASE + asset, progress)
            exe = _extract(data, asset, dest_dir)
            if _works(exe):
                return str(exe)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
    raise RuntimeError(f"Téléchargement de Stockfish impossible : {last_err}")


def _download(url: str, progress=None) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ChessCoach/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length", 0) or 0)
        buf = io.BytesIO()
        done = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            buf.write(chunk)
            done += len(chunk)
            if progress and total:
                progress(done, total)
    return buf.getvalue()


def _extract(data: bytes, asset: str, dest_dir: Path) -> Path:
    name = "stockfish.exe" if sys.platform.startswith("win") else "stockfish"
    target = dest_dir / name
    if asset.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            members = [m for m in z.namelist() if m.lower().endswith(".exe") and "stockfish" in m.lower()]
            if not members:
                raise RuntimeError("exécutable introuvable dans l'archive")
            target.write_bytes(z.read(members[0]))
    else:
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            members = [m for m in t.getmembers() if m.isfile() and Path(m.name).name.startswith("stockfish-")
                       and "." not in Path(m.name).name]
            if not members:
                raise RuntimeError("exécutable introuvable dans l'archive")
            f = t.extractfile(members[0])
            target.write_bytes(f.read())
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target


def _works(exe: Path) -> bool:
    import subprocess
    try:
        kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
        p = subprocess.run([str(exe)], input="uci\nquit\n", capture_output=True, text=True, timeout=10, **kw)
        return "uciok" in p.stdout
    except (OSError, subprocess.SubprocessError):
        return False
