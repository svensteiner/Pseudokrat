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
set "HERE=%~dp0"
"%HERE%env\Scripts\python.exe" -m pseudokrat watch --folder "%HERE%." --no-llm
echo.
echo Watcher beendet. Fenster kann geschlossen werden.
pause
