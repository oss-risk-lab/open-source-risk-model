# Check Server Status

## Quick Check: Open This Link in Your Browser

**Click here to check if the server is running:**

👉 **http://localhost:8000/api/health**

### What You'll See:

**If server IS running** ✅:
```json
{
  "status": "healthy",
  "timestamp": "2026-03-04T...",
  "database": "connected",
  "worker": "running"
}
```

**If server is NOT running** ❌:
- Browser shows: "This site can't be reached" or "Connection refused"
- Or: "Unable to connect"

---

## Next Steps Based on Result

### ✅ If Server IS Running

Great! The server is already up. Now test the query interface:

**Open the Query UI:**
👉 **http://localhost:8000/ui/query.html**

Then test these queries:
1. "How many repos do we have?"
2. "Show stats for django/django"
3. "What are the dependencies of flask?"

### ❌ If Server is NOT Running

Start the server with this command:

```bash
python -m uvicorn api.app:app --reload
```

Then:
1. Wait for message: "Application startup complete"
2. Open: http://localhost:8000/api/health
3. Verify it shows "healthy"
4. Open: http://localhost:8000/ui/query.html

---

## Database Status Check

After confirming the server is running, check if you have data:

```bash
sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_graphs;"
```

**Expected**:
- If you see a number > 0: You have data! ✅
- If you see 0: Need to populate database first

---

## Summary

1. **Check server**: Open http://localhost:8000/api/health in browser
2. **If running**: Go to http://localhost:8000/ui/query.html and test queries
3. **If not running**: Run `python -m uvicorn api.app:app --reload`
4. **Check data**: Run the sqlite3 command above

---

**Current Status**: OPENAI_API_KEY is configured ✅

**Next**: Check if server is running using the browser link above
