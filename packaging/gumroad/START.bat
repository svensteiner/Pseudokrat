@echo off
chcp 65001 >nul
title Pseudokrat - Einrichtung
setlocal
set "HERE=%~dp0"

rem Diese START.bat liegt im entpackten Gumroad-ZIP und startet die
rem mitgelieferte EXE (kein Python noetig). Fallback-Reihenfolge:
rem   1. EXE-Bundle im Unterordner Pseudokrat\ (ZIP-Layout)
rem   2. EXE direkt daneben (flaches Layout)
rem   3. Python-Quellcode (Entwickler-Checkout)

if exist "%HERE%Pseudokrat\Pseudokrat.exe" (
    "%HERE%Pseudokrat\Pseudokrat.exe" setup --folder "%HERE%."
    goto :ende
)
if exist "%HERE%Pseudokrat.exe" (
    "%HERE%Pseudokrat.exe" setup --folder "%HERE%."
    goto :ende
)
if exist "%HERE%env\Scripts\python.exe" (
    "%HERE%env\Scripts\python.exe" -m pseudokrat setup --folder "%HERE%."
    goto :ende
)
python -m pseudokrat setup --folder "%HERE%."

:ende
echo.
pause
