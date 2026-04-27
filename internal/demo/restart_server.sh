#!/bin/bash
# Quick server restart script

echo "🛑 Stopping any running server..."
pkill -f "uvicorn api.app:app" 2>/dev/null
sleep 2

echo "✅ Server stopped"
echo ""

# Check if OPENAI_API_KEY is in .env
if ! grep -q "^OPENAI_API_KEY=" .env 2>/dev/null; then
    echo "⚠️  OPENAI_API_KEY not found in .env file"
    echo ""
    echo "Please add your OpenAI API key to .env file"
    echo ""
    read -p "Press Enter after adding the key, or Ctrl+C to cancel..."
fi

echo "🚀 Starting server..."
echo "   (The server will load .env automatically via python-dotenv)"
echo ""

# Disable background worker for faster startup
export GRAPH_WORKER_ENABLED=false

# Start server (it will load .env via python-dotenv in api/app.py)
python -m uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

# Note: Press Ctrl+C to stop the server
