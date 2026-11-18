@echo off
REM Construit ChessCoach.exe (dossier dist\ChessCoach) avec PyInstaller.
REM Prerequis : Python 3.11+ installe (python.org), puis double-clic sur ce fichier.
cd /d "%~dp0"
python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt || goto :err
python -c "from coach.stockfish_dl import download_stockfish; import shutil; p=download_stockfish(); shutil.copy(p, 'stockfish.exe'); print('Stockfish :', p)"
pyinstaller --noconfirm --windowed --name ChessCoach --add-data "coach\data;coach\data" --collect-submodules coach main.py || goto :err
if exist stockfish.exe copy /Y stockfish.exe dist\ChessCoach\stockfish.exe
echo.
echo Termine ! Lance dist\ChessCoach\ChessCoach.exe
pause
exit /b 0
:err
echo Une erreur est survenue.
pause
exit /b 1
