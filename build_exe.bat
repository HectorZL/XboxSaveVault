@echo off
title Compilar Xbox Save Vault a .EXE
cd /d "%~dp0"
echo ===================================================
echo   COMPILANDO XBOX SAVE VAULT A EJECUTABLE (.EXE)
echo ===================================================
echo.
echo Verificando dependencias (PyInstaller, pywebview)...
python -m pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Instalando PyInstaller...
    python -m pip install pyinstaller
)
python -m pip show pywebview >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Instalando pywebview (Motor de ventana nativa)...
    python -m pip install pywebview pythonnet
)

echo.
echo Cerrando instancias previas de XboxSaveVault si estan abiertas...
taskkill /f /im XboxSaveVault.exe >nul 2>&1

echo.
echo [1/2] Compilando ejecutable silencioso sin consola (One-File + Icono + Ventana Nativa)...
python -m PyInstaller --noconfirm --onefile --clean --noconsole --name "XboxSaveVault" --icon "app_icon.ico" --add-data "web;web" --collect-all webview xbox_save_manager.py

echo.
if %errorlevel% equ 0 (
    echo [2/2] Autofirmando ejecutable (Code Signing)...
    powershell -ExecutionPolicy Bypass -File .\sign_exe.ps1
    echo.
    echo ===================================================
    echo  [+] PROCESO COMPLETADO CON EXITO!
    echo  El ejecutable firmado esta en: dist\XboxSaveVault.exe
    echo ===================================================
) else (
    echo [!] Ocurrio un error durante la compilacion.
)
pause
