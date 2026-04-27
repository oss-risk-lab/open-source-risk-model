#!/bin/bash
#
# Demo: Batch Ingestion CLI
#
# Shows the new batch ingestion features:
# - Progress tracking
# - Resume capability
# - Rate limit handling
# - Dataset manifest
#

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Batch Ingestion CLI Demo${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Show help
echo -e "${GREEN}1. Show CLI help${NC}"
echo ""
python -m open_source_risk_model.cli.ingest --help
echo ""
read -p "Press Enter to continue..."
echo ""

# Show test dataset
echo -e "${GREEN}2. Show test dataset (3 repos)${NC}"
echo ""
cat data/repos_test.txt
echo ""
read -p "Press Enter to continue..."
echo ""

# Run test ingestion
echo -e "${GREEN}3. Run test ingestion${NC}"
echo ""
echo -e "${YELLOW}Command:${NC}"
echo "python -m open_source_risk_model.cli.ingest --input data/repos_test.txt"
echo ""
read -p "Press Enter to run (this will take ~30 seconds)..."
echo ""

python -m open_source_risk_model.cli.ingest \
  --input data/repos_test.txt \
  --log-level INFO

echo ""
read -p "Press Enter to continue..."
echo ""

# Show manifest
echo -e "${GREEN}4. Show dataset manifest${NC}"
echo ""
if [ -f "data/manifest.json" ]; then
    echo "Summary:"
    cat data/manifest.json | python -m json.tool | grep -A 10 '"summary"'
    echo ""
    echo "Full manifest available at: data/manifest.json"
else
    echo "Manifest not found (ingestion may have failed)"
fi
echo ""
read -p "Press Enter to continue..."
echo ""

# Show database tracking
echo -e "${GREEN}5. Show ingestion tracking in database${NC}"
echo ""
echo "Query: SELECT repo_full_name, status, dependencies_found, dependencies_resolved FROM repo_ingestion_runs;"
echo ""
sqlite3 data/graphs.db "SELECT repo_full_name, status, dependencies_found, dependencies_resolved FROM repo_ingestion_runs ORDER BY started_at DESC LIMIT 5;"
echo ""
read -p "Press Enter to continue..."
echo ""

# Show resume capability
echo -e "${GREEN}6. Demonstrate resume capability${NC}"
echo ""
echo -e "${YELLOW}Running again with --resume flag (should skip already-ingested repos)${NC}"
echo ""
read -p "Press Enter to run..."
echo ""

python -m open_source_risk_model.cli.ingest \
  --input data/repos_test.txt \
  --resume \
  --log-level INFO

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Demo Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Try with full dataset: --input data/repos_full.txt"
echo "  2. Use concurrency: --concurrency 3"
echo "  3. Handle rate limits: --sleep-on-ratelimit"
echo ""
echo "Documentation:"
echo "  - Quick start: BATCH_INGESTION_QUICK_START.md"
echo "  - Full guide: BATCH_INGESTION_GUIDE.md"
echo ""
