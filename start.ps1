Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Launching ALGOARCH - 50LPA FAANG Career Guidance Platform" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Opening http://127.0.0.1:5050 in default browser..." -ForegroundColor Yellow
Start-Process "http://127.0.0.1:5050"
node (Join-Path $PSScriptRoot "server.js")
