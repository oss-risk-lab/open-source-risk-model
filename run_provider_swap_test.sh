#!/bin/bash
# Phase 3: Provider Swap Validation
# Tests same queries with OpenAI and Mock providers

API_URL="http://localhost:8000/api/query"

echo "=== Phase 3: Provider Swap Validation ==="
echo ""

# Test queries
queries=(
    "How many repos do we have?"
    "Show stats for django/django"
    "What are the dependencies of django?"
    "What repos depend on requests?"
    "Search for packages named 'express'"
)

# Function to test with a provider
test_provider() {
    local provider="$1"
    echo "========================================"
    echo "Testing with provider: $provider"
    echo "========================================"
    echo ""
    
    # Update .env
    if [ "$provider" = "mock" ]; then
        sed -i.bak 's/LLM_PROVIDER=openai/LLM_PROVIDER=mock/' .env
    else
        sed -i.bak 's/LLM_PROVIDER=mock/LLM_PROVIDER=openai/' .env
    fi
    
    # Wait for server to reload (if hot-reload enabled)
    sleep 2
    
    # Run test queries
    for query in "${queries[@]}"; do
        echo "Query: $query"
        
        response=$(curl -s -X POST "$API_URL" \
            -H "Content-Type: application/json" \
            -d "{\"query\": \"$query\"}")
        
        intent=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('intent', 'ERROR'))" 2>/dev/null)
        confidence=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('confidence', 0))" 2>/dev/null)
        row_count=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('results', [])))" 2>/dev/null)
        
        echo "  Intent: $intent | Confidence: $confidence | Rows: $row_count"
        echo ""
    done
}

# Test with OpenAI
test_provider "openai"

# Test with Mock
test_provider "mock"

# Restore OpenAI
sed -i.bak 's/LLM_PROVIDER=mock/LLM_PROVIDER=openai/' .env

echo "========================================"
echo "Provider Swap Test Complete"
echo "========================================"
echo ""
echo "Note: Server restart required for provider change to take effect."
echo "Run: ./restart_server.sh"
