#!/usr/bin/env bash
# One-command startup for job-hunter. Run with:    ./start.sh
#
# Every run of this script does ALL of the following:
#   1. Brings up the Docker stack (postgres, redis, api, worker, migrate)
#   2. Seeds companies (idempotent)
#   3. Runs a FRESH scrape — tombstoned (Submitted) jobs are never re-added
#   4. Opens http://localhost:8000

set -euo pipefail
cd "$(dirname "$0")"

echo "==> job-hunter starting..."

# 1. Docker reachable?
if ! docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
    echo "ERROR: Docker is not running. Start Docker and try again." >&2
    exit 1
fi

# 2. .env from template if missing
if [ ! -f .env ]; then
    cp .env.example .env
    echo "    Created .env from .env.example"
fi

# 3. Build + start
echo "==> Building & starting containers..."
docker compose up -d --build

# 4. Wait for API
echo "==> Waiting for API to be ready..."
for i in $(seq 1 30); do
    if curl -sf -o /dev/null --max-time 2 http://localhost:8000/; then
        break
    fi
    sleep 1
done

# 5. Seed
echo "==> Seeding companies (idempotent)..."
docker compose exec -T api python -m scripts.seed_companies

# 6. Always run a fresh scrape — only way scrapes happen
echo "==> Running a fresh scrape (~2 min)..."
docker compose exec -T api python -m scripts.run_once || true

# 7. Open browser
echo ""
echo "==> Dashboard ready: http://localhost:8000"
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://localhost:8000 >/dev/null 2>&1 &
elif command -v open >/dev/null 2>&1; then
    open http://localhost:8000
elif command -v start >/dev/null 2>&1; then
    start http://localhost:8000
fi
