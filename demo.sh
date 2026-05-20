#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-8081}"
DIR="$(cd "$(dirname "$0")/docs" && pwd)"

echo "🌐 Starting demo server at http://localhost:$PORT/presentation.html"
echo "   Press Ctrl+C to stop"
echo ""
python3 -m http.server "$PORT" --directory "$DIR"
