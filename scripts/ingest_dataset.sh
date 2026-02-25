#!/bin/bash
#
# Dataset Ingestion Script
#
# Usage:
#   ./scripts/ingest_dataset.sh pilot    # Ingest 10-repo pilot
#   ./scripts/ingest_dataset.sh full     # Ingest full 50-repo dataset
#   ./scripts/ingest_dataset.sh custom repos.txt  # Ingest custom list
#

set -e  # Exit on error

# Load environment variables from .env file
if [ -f ".env" ]; then
    set -a  # automatically export all variables
    source .env
    set +a
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DB_PATH="data/graphs.db"
PILOT_FILE="data/repos_pilot.txt"
FULL_FILE="data/repos_full.txt"

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if Python script exists
if [ ! -f "scripts/populate_popular_repos.py" ]; then
    print_error "populate_popular_repos.py not found"
    exit 1
fi

# Parse command
MODE=${1:-pilot}
CUSTOM_FILE=$2

case $MODE in
    pilot)
        print_header "PILOT INGESTION (10 repos)"
        REPO_FILE=$PILOT_FILE
        ;;
    full)
        print_header "FULL INGESTION (50 repos)"
        REPO_FILE=$FULL_FILE
        ;;
    custom)
        if [ -z "$CUSTOM_FILE" ]; then
            print_error "Custom mode requires a repo file"
            echo "Usage: $0 custom <repo_file>"
            exit 1
        fi
        print_header "CUSTOM INGESTION"
        REPO_FILE=$CUSTOM_FILE
        ;;
    *)
        print_error "Invalid mode: $MODE"
        echo "Usage: $0 {pilot|full|custom <file>}"
        exit 1
        ;;
esac

# Check if repo file exists
if [ ! -f "$REPO_FILE" ]; then
    print_error "Repo file not found: $REPO_FILE"
    exit 1
fi

# Count repos (excluding comments and empty lines)
REPO_COUNT=$(grep -v '^#' "$REPO_FILE" | grep -v '^$' | wc -l | tr -d ' ')
print_info "Repo file: $REPO_FILE"
print_info "Repos to ingest: $REPO_COUNT"
print_info "Database: $DB_PATH"
echo ""

# Confirm
read -p "Proceed with ingestion? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Ingestion cancelled"
    exit 0
fi

# Create temporary Python script to ingest from file
TEMP_SCRIPT=$(mktemp)
cat > "$TEMP_SCRIPT" << 'EOFPYTHON'
#!/usr/bin/env python3
import sys
import os
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Add project root to path
project_root = Path.cwd()
sys.path.insert(0, str(project_root))

from open_source_risk_model.dependencies.ingestion_service import DependencyIngestionService
from datetime import datetime

def load_repos(file_path):
    """Load repos from file, skipping comments and empty lines."""
    repos = []
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                repos.append(line)
    return repos

def main():
    repo_file = sys.argv[1]
    db_path = sys.argv[2]
    
    print(f"\n{'='*70}")
    print(f"INGESTION STARTED")
    print(f"{'='*70}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Repo file: {repo_file}")
    print(f"Database: {db_path}")
    print(f"{'='*70}\n")
    
    # Load repos
    repos = load_repos(repo_file)
    print(f"Loaded {len(repos)} repos from {repo_file}\n")
    
    # Initialize service
    service = DependencyIngestionService(db_path=db_path)
    
    # Ingest each repo
    results = []
    for i, repo in enumerate(repos, 1):
        print(f"\n[{i}/{len(repos)}] Ingesting {repo}...")
        
        try:
            result = service.ingest_repo(
                repo,
                refresh=True,
                resolve_packages=True
            )
            results.append(result)
            
            # Print result
            status = "✅" if result.success else "❌"
            resolution_pct = f"{result.resolution_rate:.0%}" if result.dependencies_found > 0 else "N/A"
            
            print(f"{status} {result.repo_full_name}")
            print(f"   Manifests: {result.manifests_discovered}")
            print(f"   Dependencies: {result.dependencies_found}")
            print(f"   Resolved: {result.dependencies_resolved} ({resolution_pct})")
            print(f"   Duration: {result.duration_seconds:.1f}s")
            
            if result.errors:
                print(f"   Errors: {len(result.errors)}")
                for error in result.errors[:2]:
                    print(f"     - {error}")
        
        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            break
        except Exception as e:
            print(f"❌ {repo}")
            print(f"   Error: {e}")
    
    # Print summary
    total_duration = sum(r.duration_seconds for r in results)
    successful = sum(1 for r in results if r.success)
    total_deps = sum(r.dependencies_found for r in results)
    total_resolved = sum(r.dependencies_resolved for r in results)
    avg_resolution = (total_resolved / total_deps * 100) if total_deps > 0 else 0
    
    print(f"\n{'='*70}")
    print(f"INGESTION SUMMARY")
    print(f"{'='*70}")
    print(f"Total repos: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(results) - successful}")
    print(f"Total dependencies: {total_deps}")
    print(f"Total resolved: {total_resolved} ({avg_resolution:.0f}%)")
    print(f"Total duration: {total_duration/60:.1f} minutes")
    print(f"{'='*70}\n")

if __name__ == '__main__':
    main()
EOFPYTHON

# Run ingestion
print_info "Starting ingestion..."
python3 "$TEMP_SCRIPT" "$REPO_FILE" "$DB_PATH"
INGESTION_EXIT_CODE=$?

# Clean up
rm "$TEMP_SCRIPT"

# Check if ingestion succeeded
if [ $INGESTION_EXIT_CODE -ne 0 ]; then
    print_error "Ingestion failed with exit code $INGESTION_EXIT_CODE"
    exit $INGESTION_EXIT_CODE
fi

print_success "Ingestion completed"
echo ""

# Generate dataset report
print_header "GENERATING DATASET REPORT"
python3 scripts/generate_dataset_report.py --db-path "$DB_PATH"
REPORT_EXIT_CODE=$?

# Check quality gate
if [ $REPORT_EXIT_CODE -eq 0 ]; then
    print_success "Quality gate PASSED"
    echo ""
    print_info "Next steps:"
    if [ "$MODE" = "pilot" ]; then
        echo "  1. Review the report above"
        echo "  2. If quality gate passed, run: ./scripts/ingest_dataset.sh full"
        echo "  3. If quality gate failed, fix issues and re-run pilot"
    else
        echo "  1. Dataset is ready for intelligence layer development"
        echo "  2. Proceed to Week 2: Intent-based query API"
    fi
else
    print_error "Quality gate FAILED"
    echo ""
    print_warning "Action required:"
    echo "  1. Review the failing criteria above"
    echo "  2. Fix discovery/parsing issues"
    echo "  3. Re-run ingestion: ./scripts/ingest_dataset.sh $MODE"
fi

echo ""
exit $REPORT_EXIT_CODE
