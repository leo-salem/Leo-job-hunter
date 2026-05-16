#!/usr/bin/env bash
# Stop all job-hunter containers. Volumes preserved.
set -euo pipefail
cd "$(dirname "$0")"
echo "==> Stopping job-hunter..."
docker compose down
echo "==> Stopped. Data preserved in Docker volumes."
