#!/bin/bash
# Script to populate dependency data for popular repositories

API_URL="http://localhost:8000"

echo "🚀 Populating Dependency Data"
echo "=============================="
echo ""

# Check if API is running
if ! curl -s "${API_URL}/api/health" > /dev/null 2>&1; then
    echo "❌ Error: API is not running at ${API_URL}"
    echo "Please start the server first:"
    echo "  uvicorn api.app:app --reload --port 8000"
    exit 1
fi

echo "✅ API is running"
echo ""

# Popular Python repositories
PYTHON_REPOS=(
    "numpy/numpy"
    "scipy/scipy"
    "pandas-dev/pandas"
    "scikit-learn/scikit-learn"
    "matplotlib/matplotlib"
    "fastapi/fastapi"
    "pytest-dev/pytest"
    "python/cpython"
)

# Popular JavaScript repositories
JS_REPOS=(
    "facebook/react"
    "expressjs/express"
    "lodash/lodash"
    "axios/axios"
    "nodejs/node"
    "vercel/next.js"
)

echo "📦 Processing Python Repositories..."
echo "-----------------------------------"
for repo in "${PYTHON_REPOS[@]}"; do
    echo -n "  Processing $repo... "
    
    response=$(curl -s -w "\n%{http_code}" "${API_URL}/api/graph?repo=${repo}")
    http_code=$(echo "$response" | tail -n1)
    
    if [ "$http_code" = "200" ]; then
        echo "✅"
    else
        echo "❌ (HTTP $http_code)"
    fi
    
    # Be nice to GitHub API
    sleep 2
done

echo ""
echo "📦 Processing JavaScript Repositories..."
echo "---------------------------------------"
for repo in "${JS_REPOS[@]}"; do
    echo -n "  Processing $repo... "
    
    response=$(curl -s -w "\n%{http_code}" "${API_URL}/api/graph?repo=${repo}")
    http_code=$(echo "$response" | tail -n1)
    
    if [ "$http_code" = "200" ]; then
        echo "✅"
    else
        echo "❌ (HTTP $http_code)"
    fi
    
    # Be nice to GitHub API
    sleep 2
done

echo ""
echo "=============================="
echo "✅ Population Complete!"
echo ""
echo "You can now query dependencies for these repositories:"
echo "  curl \"${API_URL}/api/repos/numpy/numpy/dependencies\""
echo "  curl \"${API_URL}/api/repos/facebook/react/dependencies\""
echo ""
echo "Or use the Dependency Explorer UI:"
echo "  open ui/dependency-explorer.html"
echo ""
