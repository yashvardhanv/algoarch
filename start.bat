@echo off
title ALGOARCH - 50LPA FAANG Platform
echo ================================================================
echo   Launching ALGOARCH - 50LPA FAANG Career Guidance Platform
echo ================================================================
echo Starting Node.js server on port 5050...
start "" "http://127.0.0.1:5050"
node "%~dp0server.js"
pause