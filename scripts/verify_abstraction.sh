#!/bin/bash
# Verification script for LLM Provider Abstraction Layer
# Ensures provider-specific imports are isolated to llm/providers/ directory

set -e

echo "=========================================="
echo "LLM Provider Abstraction Verification"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

echo "Checking for provider-specific imports in application code..."
echo ""

# Check for OpenAI imports in query module
echo "1. Checking for 'openai' imports in query module..."
if grep -r "import openai" src/open_source_risk_model/query/ 2>/dev/null; then
    echo -e "${RED}FAIL: Found 'import openai' in query module${NC}"
    FAILED=1
else
    echo -e "${GREEN}PASS: No 'import openai' found in query module${NC}"
fi

if grep -r "from openai" src/open_source_risk_model/query/ 2>/dev/null; then
    echo -e "${RED}FAIL: Found 'from openai' in query module${NC}"
    FAILED=1
else
    echo -e "${GREEN}PASS: No 'from openai' found in query module${NC}"
fi

echo ""

# Check for Anthropic imports in query module
echo "2. Checking for 'anthropic' imports in query module..."
if grep -r "import anthropic" src/open_source_risk_model/query/ 2>/dev/null; then
    echo -e "${RED}FAIL: Found 'import anthropic' in query module${NC}"
    FAILED=1
else
    echo -e "${GREEN}PASS: No 'import anthropic' found in query module${NC}"
fi

if grep -r "from anthropic" src/open_source_risk_model/query/ 2>/dev/null; then
    echo -e "${RED}FAIL: Found 'from anthropic' in query module${NC}"
    FAILED=1
else
    echo -e "${GREEN}PASS: No 'from anthropic' found in query module${NC}"
fi

echo ""

# Check that provider imports only exist in llm/providers/
echo "3. Verifying provider imports are isolated to llm/providers/..."
echo ""
echo "Provider imports in llm/providers/ (expected):"

PROVIDER_IMPORTS=$(grep -r "import openai\|from openai" src/open_source_risk_model/llm/providers/ 2>/dev/null || echo "")

if [ -z "$PROVIDER_IMPORTS" ]; then
    echo -e "${YELLOW}WARNING: No OpenAI imports found in llm/providers/${NC}"
    echo "This is expected if OpenAI provider hasn't been implemented yet."
else
    echo "$PROVIDER_IMPORTS"
    echo -e "${GREEN}✓ Provider imports correctly isolated${NC}"
fi

echo ""

# Check for provider imports outside llm/providers/
echo "4. Checking for provider imports outside llm/providers/..."

# Exclude llm/providers/ directory from search
OUTSIDE_IMPORTS=$(find src/open_source_risk_model/ -type f -name "*.py" \
    ! -path "*/llm/providers/*" \
    ! -path "*/__pycache__/*" \
    -exec grep -l "import openai\|from openai\|import anthropic\|from anthropic" {} \; 2>/dev/null || echo "")

if [ -n "$OUTSIDE_IMPORTS" ]; then
    echo -e "${RED}FAIL: Found provider imports outside llm/providers/${NC}"
    for file in $OUTSIDE_IMPORTS; do
        echo "  $file"
        grep -n "import openai\|from openai\|import anthropic\|from anthropic" "$file"
    done
    FAILED=1
else
    echo -e "${GREEN}PASS: No provider imports found outside llm/providers/${NC}"
fi

echo ""
echo "=========================================="

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All abstraction invariants verified!${NC}"
    echo ""
    echo "The LLM provider abstraction is correctly implemented:"
    echo "  - No provider-specific imports in application code"
    echo "  - Provider imports isolated to llm/providers/"
    echo "  - Application code uses abstraction layer only"
    exit 0
else
    echo -e "${RED}✗ Abstraction verification failed!${NC}"
    echo ""
    echo "Provider-specific imports found in application code."
    echo "This violates the abstraction layer design."
    echo ""
    echo "Fix by:"
    echo "  1. Remove direct provider imports from application code"
    echo "  2. Use LLMClient and factory functions instead"
    echo "  3. Keep provider imports only in llm/providers/"
    exit 1
fi
