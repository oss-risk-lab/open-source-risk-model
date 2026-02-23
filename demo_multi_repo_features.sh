#!/bin/bash
# Demo script showing NEW multi-repo persistent graph capabilities

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  Multi-Repo Persistent Graph - NEW Capabilities Demo        ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

echo "📦 1. Submit batch ingestion job (NEW!)"
echo "   Submitting 2 repos for background processing..."
RESPONSE=$(curl -s -X POST http://127.0.0.1:8000/api/ingest \
  -H "Content-Type: application/json" \
  -d '{"repos": ["psf/requests", "pallets/flask"]}')
echo "$RESPONSE" | python -m json.tool
JOB_ID=$(echo "$RESPONSE" | python -c "import sys, json; print(json.load(sys.stdin)['job_id'])" 2>/dev/null)

if [ -z "$JOB_ID" ]; then
  echo "❌ Failed to create job"
  exit 1
fi

echo ""
echo "⏳ 2. Monitor job progress (NEW!)"
for i in {1..30}; do
  JOB_DATA=$(curl -s "http://127.0.0.1:8000/api/jobs/$JOB_ID")
  STATUS=$(echo "$JOB_DATA" | python -c "import sys, json; print(json.load(sys.stdin)['status'])" 2>/dev/null)
  PROCESSED=$(echo "$JOB_DATA" | python -c "import sys, json; print(json.load(sys.stdin)['processed_repos'])" 2>/dev/null)
  TOTAL=$(echo "$JOB_DATA" | python -c "import sys, json; print(json.load(sys.stdin)['total_repos'])" 2>/dev/null)
  
  echo "   [$i/30] Status: $STATUS | Progress: $PROCESSED/$TOTAL repos"
  
  if [ "$STATUS" = "completed" ]; then
    echo "   ✅ Job completed!"
    break
  fi
  sleep 2
done

echo ""
echo "📊 3. List all stored repositories (NEW!)"
curl -s "http://127.0.0.1:8000/api/repos" | python -m json.tool

echo ""
echo "👤 4. Query repos by maintainer (NEW!)"
echo "   Finding repos maintained by 'kennethreitz'..."
curl -s "http://127.0.0.1:8000/api/repos/by-maintainer/kennethreitz" | python -m json.tool | head -50

echo ""
echo "⚡ 5. Test database caching"
echo "   First query (from database, should be fast):"
time curl -s "http://127.0.0.1:8000/api/graph?repo=psf/requests" | python -c "import sys, json; d=json.load(sys.stdin); print(f\"   Nodes: {d['metadata']['node_count']}, Edges: {d['metadata']['edge_count']}, Cache hit: {d['metadata']['cache_hit']}\")"

echo ""
echo "   Second query (should be instant from cache):"
time curl -s "http://127.0.0.1:8000/api/graph?repo=psf/requests" | python -c "import sys, json; d=json.load(sys.stdin); print(f\"   Nodes: {d['metadata']['node_count']}, Edges: {d['metadata']['edge_count']}, Cache hit: {d['metadata']['cache_hit']}\")"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  ✅ Demo Complete!                                           ║"
echo "║                                                              ║"
echo "║  What's NEW:                                                 ║"
echo "║  • Batch ingestion API (/api/ingest)                        ║"
echo "║  • Background job processing                                 ║"
echo "║  • Persistent database storage                               ║"
echo "║  • Cross-repo queries (by maintainer, CVE, package)         ║"
echo "║  • Fast database caching                                     ║"
echo "╚══════════════════════════════════════════════════════════════╝"
