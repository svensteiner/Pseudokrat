@echo off
chcp 65001 >nul
title Pseudokrat - Anonymisierung
echo ============================================================
echo   Pseudokrat - Ordner-Anonymisierung
echo ------------------------------------------------------------
echo   Datei zum Anonymisieren  ^>  Ordner INPUT
echo   Anonymisiertes Ergebnis  ^>  Ordner OUTPUT
echo.
echo   Bitte warten, bis unten "BEREIT." steht (erster Start
echo   dauert 2-3 Minuten). Dann Datei in INPUT ziehen.
echo   Hinweis: Scan-PDFs mit OCR koennen mehrere Minuten dauern.
echo   Beenden: dieses Fenster schliessen.
echo ============================================================
echo.
setlocal
set "HERE=%~dp0"
if exist "%HERE%Pseudokrat\Pseudokrat.exe" (
    "%HERE%Pseudokrat\Pseudokrat.exe" watch --folder "%HERE%." --no-llm
    goto :result
)
if exist "%HERE%Pseudokrat.exe" (
    "%HERE%Pseudokrat.exe" watch --folder "%HERE%." --no-llm
    goto :result
)
if exist "%HERE%env\Scripts\python.exe" (
    "%HERE%env\Scripts\python.exe" -m pseudokrat watch --folder "%HERE%." --no-llm
    goto :result
)
set "RC=9009"
echo FEHLER: Keine mitgelieferte Pseudokrat-Laufzeit gefunden.
goto :ende

:result
set "RC=%ERRORLEVEL%"

:ende
echo.
echo Watcher beendet. Fenster kann geschlossen werden.
if not "%RC%"=="0" echo Pseudokrat wurde mit Code %RC% beendet.
pause
exit /b %RC%
