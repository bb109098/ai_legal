@echo off
setlocal
cd /d "%~dp0"

echo ===============================================================================
echo TNREGINET UNIFIED AUTONOMOUS LEGAL TITLE SCRUTINY PIPELINE (ENGINES A -> B -> C)
echo ===============================================================================

set DOC=1579
set YEAR=2021
set SRO=Trichy Joint 1
set SRO_ID=20445:1
set PLOT=26

if not "%~1"=="" set DOC=%~1
if not "%~2"=="" set YEAR=%~2
if not "%~3"=="" set SRO=%~3
if not "%~4"=="" set SRO_ID=%~4
if not "%~5"=="" set PLOT=%~5

echo Target Deed : Doc %DOC%/%YEAR% @ %SRO% (SRO ID: %SRO_ID%) [Plot: %PLOT%]
echo.

python run_scrutiny_pipeline.py --doc %DOC% --year %YEAR% --sro "%SRO%" --sro_id "%SRO_ID%" --plot %PLOT%

echo.
pause
