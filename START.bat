@echo off
chcp 65001 >nul
title Pseudokrat - Einrichtung
setlocal
set "HERE=%~dp0"

rem Bevorzugt eine mitgelieferte Laufzeit-Umgebung (env\), sonst System-Python.
if exist "%HERE%env\Scripts\python.exe" (
    "%HERE%env\Scripts\python.exe" -m pseudokrat setup --folder "%HERE%"
) else (
    python -m pseudokrat setup --folder "%HERE%"
)

echo.
pause
