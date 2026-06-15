@echo off
chcp 65001 >nul
title Pseudokrat - Anonymisierung
echo ============================================================
echo   Pseudokrat - Ordner-Anonymisierung
echo ------------------------------------------------------------
echo   Datei zum Anonymisieren  ->  Ordner INPUT
echo   Anonymisiertes Ergebnis  ->  Ordner OUTPUT
echo.
echo   Bitte warten, bis unten "BEREIT." steht (erster Start
echo   dauert 2-3 Minuten). Dann Datei in INPUT ziehen.
echo   Beenden: dieses Fenster schliessen.
echo ============================================================
echo.
"%~dp0env\Scripts\python.exe" -m pseudokrat watch --folder "%~dp0"
echo.
echo Watcher beendet. Fenster kann geschlossen werden.
pause
