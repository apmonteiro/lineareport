@echo off
REM Rode numa maquina COM internet (Windows, mesma versao do Python do servidor).
REM Cria a pasta "pacotes" com tudo o que o LineaReport precisa. Copie o projeto inteiro,
REM com essa pasta, para o servidor da intranet e rode iniciar_servidor.bat.
cd /d "%~dp0"
python -m pip wheel -r backend\requirements.txt -w pacotes || (pause & exit /b 1)
echo.
echo Pronto. Pacotes salvos em "%~dp0pacotes".
pause
