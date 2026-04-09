#!/bin/bash
# Phase 2: Query Test Set
# Tests 10 queries across all intents

API_URL="http://localhost:8000/api/query"

echo "=== Phase 2: Query Test Set ==="
echo "Testing 10 queries across all intents"
echo ""

# Function to run query and extract key info
run_query() {
    local query="$1"
    local expected_intent="$2"
    
    echo "----------------------------------------"
    echo "Query: $query"
    echo "Expected Intent: $expected_intent"
    
    response=$(curl -s -X POST "$API_URL" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\"}")
    
    # Extract intent, confidence, row count, and response time
    intent=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('intent', 'ERROR'))" 2>/dev/null)
    confidence=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('confidence', 0))" 2>/dev/null)
    row_count=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(len(data.get('results', [])))" 2>/dev/null)
    response_time=$(echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('response_time_ms', 0))" 2>/dev/null)
    
    echo "Actual Intent: $intent"
    echo "Confidence: $confidence"
    echo "Row Count: $row_count"
    echo "Response Time: ${response_time}ms"
    
    # Check if intent matches
    if [ "$intent" = "$expected_intent" ]; then
        echo "✅ Intent CORRECT"
    else
        echo "❌ Intent MISMATCH"
    fi
    
    # Show first result if available
    if [ "$row_count" -gt 0 ]; then
        echo "Sample Result:"
        echo "$response" | python3 -c "import sys, json; data=json.load(sys.stdin); print(json.dumps(data.get('results', [])[0], indent=2))" 2>/dev/null | head -10
    fi
    
    echo ""
}

# Test 1: Dataset stats
run_query "How many repos do we have?" "dataset_stats"

# Test 2: Repo stats
run_query "Show stats for django/django" "repo_stats"

# Test 3: List dependencies
run_query "What are the dependencies of django?" "list_dependencies"

# Test 4: Dependency tree
run_query "Show dependency tree for django/django with depth 2" "dependency_tree"

# Test 5: Find dependents
run_query "What repos depend on requests?" "find_dependents"

# Test 6: Search repos
run_query "Search for repos containing 'security'" "search_repos"

# Test 7: Search packages
run_query "Search for packages named 'express'" "search_packages"

# Test 8: List manifests
run_query "List manifests for django/django" "list_manifests"

# Test 9: Count by manifest type
run_query "Count dependencies by manifest type" "count_by_manifest"

# Test 10: List unresolved
run_query "Show unresolved dependencies" "list_unresolved"

echo "========================================"
echo "Query Test Set Complete"
echo "========================================"
