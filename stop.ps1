# Stop all job-hunter containers.
# Volumes (pgdata, redisdata) are PRESERVED — your jobs and Applied/Submitted
# history survive. To wipe data too, run: docker compose down -v
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "==> Stopping job-hunter..." -ForegroundColor Cyan
docker compose down
Write-Host "==> Stopped. Data preserved in Docker volumes." -ForegroundColor Green
