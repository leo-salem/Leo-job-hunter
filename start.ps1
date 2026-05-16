# One-command startup for job-hunter. Run with:    start.bat   (or .\start.ps1)
#
# Every run of this script does ALL of the following:
#   1. Brings up the Docker stack (postgres, redis, api, worker, migrate)
#   2. Seeds companies (idempotent; new entries in companies.yaml are added)
#   3. Runs a FRESH scrape — every source is hit again, new jobs added,
#      tombstoned jobs (ones you clicked "Submitted") are NEVER re-added
#   4. Opens http://localhost:8000 in your browser

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> job-hunter starting..." -ForegroundColor Cyan

# 1. Docker reachable?
try {
    docker version --format '{{.Server.Version}}' | Out-Null
} catch {
    Write-Host "ERROR: Docker Desktop is not running. Start Docker Desktop and try again." -ForegroundColor Red
    exit 1
}

# 2. .env from template if missing
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "    Created .env from .env.example" -ForegroundColor Yellow
    Write-Host "    Edit it later to set ANTHROPIC_API_KEY for AI scoring." -ForegroundColor Yellow
}

# 3. Build (cached after first run) + start containers.
#    The 'migrate' service runs alembic upgrade head automatically.
Write-Host "==> Building & starting containers..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 4. Wait for the API to start serving
Write-Host "==> Waiting for API to be ready..." -ForegroundColor Cyan
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}
if (-not $ready) {
    Write-Host "API didn't respond within 30s. Check 'docker compose logs api'." -ForegroundColor Red
    exit 1
}

# 5. Seed companies (idempotent upsert).
Write-Host "==> Seeding companies (idempotent)..." -ForegroundColor Cyan
docker compose exec -T api python -m scripts.seed_companies
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# 6. ALWAYS run a fresh scrape now. ~2 min depending on source responsiveness.
#    This is the only way scrapes happen — no midnight cron, no startup-catchup.
Write-Host "==> Running a fresh scrape (~2 min)..." -ForegroundColor Cyan
docker compose exec -T api python -m scripts.run_once
if ($LASTEXITCODE -ne 0) {
    Write-Host "    (Scrape returned non-zero, but the dashboard will still open.)" -ForegroundColor Yellow
}

# 7. Open the browser
Write-Host ""
Write-Host "==> Dashboard ready: http://localhost:8000" -ForegroundColor Green
Start-Process "http://localhost:8000"
