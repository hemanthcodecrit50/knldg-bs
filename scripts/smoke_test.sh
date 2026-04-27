#!/usr/bin/env bash
# scripts/smoke_test.sh
# Quick end-to-end check: sync → query.
# Run from the repo root with Milvus and backend already running.
#
# Usage:
#   BACKEND_URL=http://localhost:8000 bash scripts/smoke_test.sh

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
QUESTION="What is the Synced Brain and how does it sync files?"

echo ""
echo "══════════════════════════════════════════════"
echo "  Synced Brain — Smoke Test"
echo "══════════════════════════════════════════════"

# ── 1. Health check ────────────────────────────────────────────────────────────
echo ""
echo "[1/3] Checking backend health at ${BACKEND_URL}/health …"
STATUS=$(curl -sf "${BACKEND_URL}/health" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('status',''))")
if [ "$STATUS" != "ok" ]; then
  echo "  ✗ Health check failed (got: '${STATUS}')"
  exit 1
fi
echo "  ✓ Backend is healthy"

# ── 2. Sync ────────────────────────────────────────────────────────────────────
echo ""
echo "[2/3] Running sync engine (full reconcile) …"
python -m backend.app.sync.sync
echo "  ✓ Sync complete"

# ── 3. Query ──────────────────────────────────────────────────────────────────
echo ""
echo "[3/3] Querying brain: \"${QUESTION}\""
RESPONSE=$(curl -sf -X POST "${BACKEND_URL}/query" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"${QUESTION}\", \"top_k\": 3, \"debug\": true}")

ANSWER=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d['answer'][:200])")
NUM_CITATIONS=$(echo "$RESPONSE" | python3 -c "import sys, json; d=json.load(sys.stdin); print(len(d['citations']))")

echo ""
echo "  Answer (first 200 chars):"
echo "  ${ANSWER}"
echo ""
echo "  Citations returned: ${NUM_CITATIONS}"

if [ "$NUM_CITATIONS" -lt 1 ]; then
  echo ""
  echo "  ✗ Expected at least 1 citation — is the knowledge/ folder populated?"
  exit 1
fi

echo ""
echo "══════════════════════════════════════════════"
echo "  ✓ All checks passed"
echo "══════════════════════════════════════════════"
echo ""
