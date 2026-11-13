@echo off
REM Inicia o LineaReport no Windows. Na primeira vez, instala as dependencias.
cd /d "%~dp0backend"
if not exist ".venv" (
  echo Criando ambiente Python...
  python -m venv .venv || (echo Instale o Python 3.10 ou superior: https://www.python.org/downloads/ & pause & exit /b 1)
  call .venv\Scripts\activate.bat
  if exist "%~dp0pacotes" (
    pip install --no-index --find-links "%~dp0pacotes" -r requirements.txt
  ) else (
    python -m pip install --upgrade pip
    pip install -r requirements.txt
  )
) else (
  call .venv\Scripts\activate.bat
)
python run_server.py
pause
