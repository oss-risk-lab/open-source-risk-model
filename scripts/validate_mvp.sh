#!/bin/bash
# MVP Validation Script
# Runs automated checks to validate the LLM Provider Abstraction Layer MVP

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo "=========================================="
echo "MVP VALIDATION: LLM Provider Abstraction"
echo "=========================================="
echo ""

FAILED=0

# Check 1: Environment Setup
echo -e "${BLUE}Check 1: Environment Setup${NC}"
echo "Checking for required environment variables..."

if [ -f ".env" ]; then
    echo -e "${GREEN}✓ .env file exists${NC}"
    
    if grep -q "GITHUB_TOKEN=" .env && ! grep -q "GITHUB_TOKEN=your_github_token_here" .env; then
        echo -e "${GREEN}✓ GITHUB_TOKEN configured${NC}"
    else
        echo -e "${YELLOW}⚠ GITHUB_TOKEN not configured (required for ingestion)${NC}"
    fi
    
    if grep -q "OPENAI_API_KEY=" .env && ! grep -q "OPENAI_API_KEY=sk-..." .env; then
        echo -e "${GREEN}✓ OPENAI_API_KEY configured${NC}"
    else
        echo -e "${YELLOW}⚠ OPENAI_API_KEY not configured (required for LLM queries)${NC}"
    fi
else
    echo -e "${RED}✗ .env file not found${NC}"
    echo "  Run: cp .env.example .env"
    FAILED=1
fi

echo ""

# Check 2: Provider Abstraction
echo -e "${BLUE}Check 2: Provider Abstraction Verification${NC}"
if [ -f "scripts/verify_abstraction.sh" ]; then
    bash scripts/verify_abstraction.sh
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Provider abstraction verified${NC}"
    else
        echo -e "${RED}✗ Provider abstraction verification failed${NC}"
        FAILED=1
    fi
else
    echo -e "${RED}✗ Abstraction verification script not found${NC}"
    FAILED=1
fi

echo ""

# Check 3: Unit Tests (No API Key Required)
echo -e "${BLUE}Check 3: Unit Tests (No API Key Required)${NC}"
echo "Running LLM unit tests..."

# Temporarily unset API key to prove tests work without it
ORIGINAL_KEY=$OPENAI_API_KEY
unset OPENAI_API_KEY

if pytest test/llm/ -m "not integration" -v --tb=short 2>&1 | tee /tmp/pytest_output.txt; then
    PASSED=$(grep -c "passed" /tmp/pytest_output.txt || echo "0")
    echo -e "${GREEN}✓ All unit tests passed ($PASSED tests)${NC}"
else
    echo -e "${RED}✗ Some unit tests failed${NC}"
    FAILED=1
fi

# Restore API key
export OPENAI_API_KEY=$ORIGINAL_KEY

echo ""

# Check 4: IntentClassifier Tests
echo -e "${BLUE}Check 4: IntentClassifier Tests${NC}"
echo "Running IntentClassifier tests..."

if pytest test/test_intent_classifier.py -v --tb=short 2>&1 | tee /tmp/pytest_classifier.txt; then
    PASSED=$(grep -c "passed" /tmp/pytest_classifier.txt || echo "0")
    echo -e "${GREEN}✓ IntentClassifier tests passed ($PASSED tests)${NC}"
else
    echo -e "${RED}✗ IntentClassifier tests failed${NC}"
    FAILED=1
fi

echo ""

# Check 5: Database Status
echo -e "${BLUE}Check 5: Database Status${NC}"
if [ -f "data/graphs.db" ]; then
    echo -e "${GREEN}✓ Database exists${NC}"
    
    REPO_COUNT=$(sqlite3 data/graphs.db "SELECT COUNT(*) FROM repositories;" 2>/dev/null || echo "0")
    DEP_COUNT=$(sqlite3 data/graphs.db "SELECT COUNT(*) FROM dependencies;" 2>/dev/null || echo "0")
    
    echo "  Repositories: $REPO_COUNT"
    echo "  Dependencies: $DEP_COUNT"
    
    if [ "$REPO_COUNT" -lt 10 ]; then
        echo -e "${YELLOW}⚠ Low repository count (recommend 200+ for meaningful analysis)${NC}"
    else
        echo -e "${GREEN}✓ Sufficient repository data${NC}"
    fi
else
    echo -e "${YELLOW}⚠ Database not found (run ingestion to populate)${NC}"
fi

echo ""

# Check 6: API Server Health
echo -e "${BLUE}Check 6: API Server Health Check${NC}"
echo "Checking if API server can start..."

# Try to import the app (validates no import errors)
if python -c "from api.app import app; print('✓ API app imports successfully')" 2>/dev/null; then
    echo -e "${GREEN}✓ API server imports successfully${NC}"
else
    echo -e "${RED}✗ API server has import errors${NC}"
    FAILED=1
fi

echo ""

# Check 7: Documentation
echo -e "${BLUE}Check 7: Documentation Completeness${NC}"

DOCS=(
    "README.md"
    "docs/SETUP.md"
    "src/open_source_risk_model/llm/README.md"
    ".env.example"
)

for doc in "${DOCS[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "${GREEN}✓ $doc exists${NC}"
    else
        echo -e "${RED}✗ $doc missing${NC}"
        FAILED=1
    fi
done

echo ""

# Summary
echo "=========================================="
echo "VALIDATION SUMMARY"
echo "=========================================="

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ MVP VALIDATION PASSED${NC}"
    echo ""
    echo "The LLM Provider Abstraction Layer MVP is ready for:"
    echo "  1. Real query testing"
    echo "  2. Provider switching validation"
    echo "  3. Cold start testing"
    echo ""
    echo "Next steps:"
    echo "  1. Start server: python -m uvicorn api.app:app --reload"
    echo "  2. Test queries via UI: http://localhost:8000/ui/query.html"
    echo "  3. Run integration tests: pytest -m integration -v"
    echo ""
    exit 0
else
    echo -e "${RED}✗ MVP VALIDATION FAILED${NC}"
    echo ""
    echo "Fix the issues above before proceeding."
    echo ""
    exit 1
fi
