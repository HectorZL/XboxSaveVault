@echo off
title Xbox Save Vault - Gestor de Partidas Xbox PC
cd /d "%~dp0"
echo ===================================================
echo     XBOX SAVE VAULT - GESTOR DE PARTIDAS XBOX PC
echo ===================================================
echo.
echo Iniciando servidor e interfaz visual...
echo Presiona Ctrl+C en esta ventana para detener.
echo.
python xbox_save_manager.py
pause
