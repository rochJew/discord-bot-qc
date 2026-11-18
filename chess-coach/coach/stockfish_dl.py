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
API = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"


def _platform_key() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "ubuntu"


def _rank(name: str, avx2: bool) -> int | None:
    """Score d'un fichier de release pour cette machine (plus petit = meilleur)."""
    n = name.lower()
    plat = _platform_key()
    if plat not in n or not (n.endswith(".zip") or n.endswith(".tar")):
        return None
    if plat == "macos":
        arm = platform.machine() == "arm64"
        return 0 if (("apple-silicon" in n or "m1" in n) == arm) else None
    if "x86-64" not in n:
        return None
    variant = n.split("x86-64", 1)[1].split(".")[0].strip("-")
    order = (["avx2", "bmi2", "sse41-popcnt", ""] if avx2 else ["sse41-popcnt", ""])
    return order.index(variant) if variant in order else None


def _api(url: str):
    import json
    headers = {"User-Agent": "ChessCoach/1.0", "Accept": "application/vnd.github+json"}
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _release_assets(avx2: bool) -> list[str]:
    """URLs des fichiers adaptés à ce PC : dernière version stable, sinon releases récentes."""
    releases = []
    try:
        releases.append(_api(API))
    except Exception:  # noqa: BLE001
        pass
    try:
        rels = _api(API.rsplit("/", 1)[0] + "?per_page=15")
        releases += sorted(rels, key=lambda r: bool(r.get("prerelease")))  # stables d'abord
    except Exception:  # noqa: BLE001
        pass
    for rel in releases:
        ranked = []
        for a in rel.get("assets", []):
            k = _rank(a.get("name", ""), avx2)
            if k is not None:
                ranked.append((k, a["browser_download_url"]))
        if ranked:
            return [u for _, u in sorted(ranked)]
    return []


def _assets() -> list[str]:
    """Noms de fichiers connus (repli si l'API GitHub est inaccessible)."""
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
    avx2 = _cpu_has_avx2()
    try:
        urls = _release_assets(avx2)
    except Exception:  # noqa: BLE001 - API indisponible : on tente les noms connus
        urls = []
    if not urls:
        names = _assets() if avx2 else (_assets()[1:] or _assets())
        urls = [BASE + n for n in names]
    last_err = None
    for url in urls:
        try:
            data = _download(url, progress)
            exe = _extract(data, url.rsplit("/", 1)[-1], dest_dir)
            if _works(exe):
                return str(exe)
            last_err = RuntimeError(f"{url} ne démarre pas sur ce PC")
        except Exception as exc:  # noqa: BLE001
            last_err = f"{url.rsplit('/', 1)[-1]} : {exc}"
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
