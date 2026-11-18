@echo off
REM Lance l'application depuis les sources (sans construire d'exe).
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
start "" pythonw main.py
