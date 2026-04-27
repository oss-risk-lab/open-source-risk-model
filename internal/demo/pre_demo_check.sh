#!/bin/bash

# Pre-Demo Checklist Script
# Run this before showing dad the demo

echo "🎯 PRE-DEMO CHECKLIST"
echo "===================="
echo ""

# Check 1: Database exists and has data
echo "✓ Checking database..."
if [ -f "data/graphs.db" ]; then
    REPO_COUNT=$(sqlite3 data/graphs.db "SELECT COUNT(DISTINCT repo_full_name) FROM repo_dependencies;" 2>/dev/null)
    DEP_COUNT=$(sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_dependencies;" 2>/dev/null)
    
    if [ -n "$REPO_COUNT" ] && [ "$REPO_COUNT" -gt 0 ]; then
        echo "  ✅ Database found: $REPO_COUNT repos, $DEP_COUNT dependencies"
    else
        echo "  ❌ Database exists but has no data"
        echo "     Run: python -m open_source_risk_model.cli.ingest --input data/repos_full.txt --max-repos 50"
        exit 1
    fi
else
    echo "  ❌ Database not found at data/graphs.db"
    exit 1
fi

# Check 2: API dependencies installed
echo ""
echo "✓ Checking Python dependencies..."
if python -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "  ✅ API dependencies installed"
else
    echo "  ❌ Missing dependencies"
    echo "     Run: pip install -e ."
    exit 1
fi

# Check 3: API can start (don't actually start it, just check)
echo ""
echo "✓ Checking API server..."
if [ -f "api/app.py" ]; then
    echo "  ✅ API server file found"
    echo "     To start: uvicorn api.app:app --reload"
else
    echo "  ❌ API server file not found"
    exit 1
fi

# Check 4: UI files exist
echo ""
echo "✓ Checking UI files..."
if [ -f "ui/query.html" ]; then
    echo "  ✅ Query UI found"
    echo "     To open: open ui/query.html"
else
    echo "  ⚠️  Query UI not found (optional)"
fi

if [ -f "ui/dependency-explorer.html" ]; then
    echo "  ✅ Dependency explorer found"
else
    echo "  ⚠️  Dependency explorer not found (optional)"
fi

# Check 5: Demo scripts exist
echo ""
echo "✓ Checking demo scripts..."
if [ -f "demo_query_api.sh" ]; then
    echo "  ✅ Query API demo script found"
    chmod +x demo_query_api.sh
else
    echo "  ⚠️  Demo script not found (optional)"
fi

# Check 6: Show top repos
echo ""
echo "✓ Top repos by dependency count:"
sqlite3 data/graphs.db "
SELECT 
    repo_full_name,
    COUNT(*) as deps
FROM repo_dependencies
GROUP BY repo_full_name
ORDER BY deps DESC
LIMIT 5;
" 2>/dev/null | while IFS='|' read -r repo deps; do
    echo "  • $repo: $deps dependencies"
done

# Check 7: Environment variables
echo ""
echo "✓ Checking environment..."
if [ -f ".env" ]; then
    if grep -q "GITHUB_TOKEN" .env; then
        echo "  ✅ GitHub token configured"
    else
        echo "  ⚠️  No GitHub token (may hit rate limits)"
    fi
    
    if grep -q "OPENAI_API_KEY" .env; then
        echo "  ✅ OpenAI API key configured (natural language queries enabled)"
    else
        echo "  ⚠️  No OpenAI key (dev mode only - still works!)"
    fi
else
    echo "  ⚠️  No .env file found"
fi

# Summary
echo ""
echo "===================="
echo "📊 DEMO READY STATUS"
echo "===================="
echo ""
echo "Data: ✅ $REPO_COUNT repos, $DEP_COUNT dependencies"
echo "API:  ✅ Ready to start"
echo "UI:   ✅ Ready to open"
echo ""
echo "🚀 TO START DEMO:"
echo "   1. uvicorn api.app:app --reload"
echo "   2. open ui/query.html"
echo "   3. Follow DAD_DEMO_GUIDE.md"
echo ""
echo "Good luck! 🎯"
