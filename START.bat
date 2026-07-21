@echo off
chcp 65001 >nul
title Pseudokrat - Einrichtung
setlocal
set "HERE=%~dp0"

rem Fallback-Reihenfolge:
rem   1. EXE-Bundle im Unterordner Pseudokrat\ (Gumroad-ZIP-Layout)
rem   2. EXE direkt daneben (flaches Layout)
rem   3. Mitgelieferte Laufzeit-Umgebung (env\)
rem   4. System-Python (Entwickler-Checkout)

if exist "%HERE%Pseudokrat\Pseudokrat.exe" (
    "%HERE%Pseudokrat\Pseudokrat.exe" setup --folder "%HERE%."
    goto :result
)
if exist "%HERE%Pseudokrat.exe" (
    "%HERE%Pseudokrat.exe" setup --folder "%HERE%."
    goto :result
)
if exist "%HERE%env\Scripts\python.exe" (
    "%HERE%env\Scripts\python.exe" -m pseudokrat setup --folder "%HERE%."
    goto :result
)
where python >nul 2>&1
if errorlevel 1 goto :missing
python -m pseudokrat setup --folder "%HERE%."

:result
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo FEHLER: Pseudokrat wurde mit Code %RC% beendet.
)
goto :ende

:missing
set "RC=9009"
echo.
echo FEHLER: Keine mitgelieferte Pseudokrat-Laufzeit gefunden.
echo Bitte das vollstaendige ZIP entpacken oder Pseudokrat installieren.

:ende
echo.
pause
exit /b %RC%
