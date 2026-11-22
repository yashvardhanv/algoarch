# Copies the MP4 muxer used by the lecture-video renderer into tools/video/vendor.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$vendor = Join-Path $here 'vendor'
New-Item -ItemType Directory -Force $vendor | Out-Null
$tmp = Join-Path $env:TEMP 'mp4muxer-dl'
New-Item -ItemType Directory -Force $tmp | Out-Null
Push-Location $tmp
npm init -y | Out-Null
npm i mp4-muxer@5.1.3 --no-audit --no-fund
Pop-Location
Copy-Item (Join-Path $tmp 'node_modules\mp4-muxer\build\mp4-muxer.js') (Join-Path $vendor 'mp4-muxer.js') -Force
Copy-Item (Join-Path $tmp 'node_modules\mp4-muxer\LICENSE') (Join-Path $vendor 'mp4-muxer.LICENSE') -Force
Get-ChildItem $vendor | Select-Object Name, Length
