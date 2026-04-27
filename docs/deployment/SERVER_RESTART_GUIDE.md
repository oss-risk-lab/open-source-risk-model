# Server Restart Guide

## What Happened

The server was running but consuming high CPU (50%+), likely due to the background ingestion worker processing jobs.

**Good news**: You already have 51 repos in the database! ✅

---

## Quick Restart (Recommended)

I've stopped the old server and created a restart script that disables the background worker for faster, lighter operation:

```bash
./restart_server.sh
```

This will:
- Kill any running server
- Start fresh with worker disabled
- Server will be ready in ~5 seconds

---

## Manual Restart (Alternative)

If you prefer to control it manually:

### Stop Server
```bash
pkill -f "uvicorn api.app:app"
```

### Start Server (with worker disabled)
```bash
export GRAPH_WORKER_ENABLED=false
python -m uvicorn api.app:app --reload
```

### Start Server (with worker enabled - slower)
```bash
python -m uvicorn api.app:app --reload
```

---

## After Server Starts

1. **Wait for startup message**: "Application startup complete"
2. **Check health**: Open http://localhost:8000/api/health
3. **Test queries**: Open http://localhost:8000/ui/query.html

---

## Test Queries to Try

Since you have 51 repos, try these:

1. "How many repos do we have?"
2. "Show me dataset stats"
3. "List all repos"
4. "What are the dependencies of flask?"
5. "Search for repos with 'django'"

---

## Troubleshooting

### Server still slow?
- Check CPU: `top -pid $(pgrep -f uvicorn)`
- Check logs in terminal for errors
- Try restarting with worker disabled (see above)

### Can't connect?
- Verify server is running: `ps aux | grep uvicorn`
- Check port 8000 is free: `lsof -i :8000`

### Database issues?
- Check database exists: `ls -lh data/graphs.db`
- Check repo count: `sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_graphs;"`

---

## Current Status

- ✅ Old server stopped
- ✅ Database exists (2.2MB, 51 repos)
- ✅ OPENAI_API_KEY configured
- ⏳ Ready to restart

**Next**: Run `./restart_server.sh` to start fresh
