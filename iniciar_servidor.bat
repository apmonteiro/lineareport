@echo off
REM Inicia o LineaReport como servidor da rede interna (waitress). Veja INTRANET.md.
REM Porta e outras opcoes: iniciar_servidor.bat --porta 8080 --threads 8
cd /d "%~dp0backend"
if not exist ".venv" (
  echo Criando ambiente Python...
  python -m venv .venv || (echo Instale o Python 3.10 ou superior: https://www.python.org/downloads/ & pause & exit /b 1)
  call .venv\Scripts\activate.bat
  if exist "%~dp0pacotes" (
    echo Instalando dependencias a partir da pasta "pacotes" ^(sem internet^)...
    pip install --no-index --find-links "%~dp0pacotes" -r requirements.txt || (pause & exit /b 1)
  ) else (
    python -m pip install --upgrade pip
    pip install -r requirements.txt || (pause & exit /b 1)
  )
) else (
  call .venv\Scripts\activate.bat
)
python servir.py %*
pause
