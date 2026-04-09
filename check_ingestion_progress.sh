#!/bin/bash
# Quick script to check ingestion progress

echo "=== Current Database Stats ==="
PYTHONPATH=. python -c "
from open_source_risk_model.query.intent_executor import IntentExecutor
executor = IntentExecutor('data/graphs.db')
result = executor.execute('dataset_stats', {})
stats = result.results[0]
print(f\"Repos: {stats['repo_count']}\")
print(f\"Dependencies: {stats['total_dependencies']}\")
print(f\"Resolution Rate: {stats['resolution_rate']}%\")
"

echo ""
echo "=== Ingestion Process Status ==="
if ps aux | grep -i "cli.ingest" | grep -v grep > /dev/null; then
    echo "✅ Ingestion is RUNNING"
    echo ""
    echo "Recent activity (last 10 lines):"
    tail -10 /tmp/batch_20_repos.txt 2>/dev/null || echo "No log file found"
else
    echo "❌ No ingestion process running"
fi
