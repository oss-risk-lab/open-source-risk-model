#!/bin/bash
# Demo script for testing the Query API in dev mode
# No OpenAI API key required!

set -e

API_URL="http://localhost:8000"

echo "=========================================="
echo "Query API Dev Mode Demo"
echo "=========================================="
echo ""
echo "Make sure the API server is running:"
echo "  uvicorn api.app:app --reload"
echo ""
echo "Press Enter to start testing..."
read

echo ""
echo "=========================================="
echo "1. Dataset Statistics"
echo "=========================================="
curl -s -X POST "$API_URL/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me dataset stats",
    "intent": "dataset_stats",
    "parameters": {}
  }' | python -m json.tool

echo ""
echo ""
echo "Press Enter for next query..."
read

echo ""
echo "=========================================="
echo "2. List Dependencies for a Repo"
echo "=========================================="
curl -s -X POST "$API_URL/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "List dependencies",
    "intent": "list_dependencies",
    "parameters": {"repo_full_name": "pallets/flask"},
    "max_results": 10
  }' | python -m json.tool

echo ""
echo ""
echo "Press Enter for next query..."
read

echo ""
echo "=========================================="
echo "3. Find Who Depends on a Package"
echo "=========================================="
curl -s -X POST "$API_URL/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Who uses flask?",
    "intent": "find_dependents",
    "parameters": {"package_name": "flask", "registry_type": "pypi"},
    "max_results": 5
  }' | python -m json.tool

echo ""
echo ""
echo "Press Enter for next query..."
read

echo ""
echo "=========================================="
echo "4. Get Dependency Tree"
echo "=========================================="
curl -s -X POST "$API_URL/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Dependency tree",
    "intent": "get_dependency_tree",
    "parameters": {"repo_full_name": "pallets/flask", "max_depth": 2},
    "max_results": 20
  }' | python -m json.tool

echo ""
echo ""
echo "Press Enter for next query..."
read

echo ""
echo "=========================================="
echo "5. Repository Statistics"
echo "=========================================="
curl -s -X POST "$API_URL/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Stats for flask",
    "intent": "repo_stats",
    "parameters": {"repo_full_name": "pallets/flask"}
  }' | python -m json.tool

echo ""
echo ""
echo "Press Enter for next query..."
read

echo ""
echo "=========================================="
echo "6. List Unresolved Dependencies"
echo "=========================================="
curl -s -X POST "$API_URL/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Unresolved dependencies",
    "intent": "list_unresolved",
    "parameters": {},
    "max_results": 10
  }' | python -m json.tool

echo ""
echo ""
echo "Press Enter for next query..."
read

echo ""
echo "=========================================="
echo "7. Search Repositories"
echo "=========================================="
curl -s -X POST "$API_URL/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find repos",
    "intent": "search_repos",
    "parameters": {"pattern": "%django%"},
    "max_results": 5
  }' | python -m json.tool

echo ""
echo ""
echo "Press Enter for next query..."
read

echo ""
echo "=========================================="
echo "8. Search Packages"
echo "=========================================="
curl -s -X POST "$API_URL/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Find packages",
    "intent": "search_packages",
    "parameters": {"pattern": "flask%", "registry_type": "pypi"},
    "max_results": 10
  }' | python -m json.tool

echo ""
echo ""
echo "=========================================="
echo "Demo Complete!"
echo "=========================================="
echo ""
echo "All 8 queries executed successfully."
echo "Try modifying the parameters to explore your data!"
