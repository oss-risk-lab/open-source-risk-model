# Add OpenAI API Key

## The Problem

The server can't find your OPENAI_API_KEY. It needs to be in the `.env` file.

---

## Solution: Add Your API Key

### Option 1: Edit .env File Directly (Recommended)

Open `.env` in your editor and add this line at the end:

```bash
OPENAI_API_KEY=sk-your-actual-key-here
```

Replace `sk-your-actual-key-here` with your real OpenAI API key.

### Option 2: Add via Command Line

```bash
echo 'OPENAI_API_KEY=sk-your-actual-key-here' >> .env
```

Replace `sk-your-actual-key-here` with your real OpenAI API key.

---

## Get Your OpenAI API Key

If you don't have one:

1. Go to https://platform.openai.com/api-keys
2. Sign in or create account
3. Click "Create new secret key"
4. Copy the key (starts with `sk-`)
5. Add it to `.env` as shown above

---

## After Adding the Key

Restart the server:

```bash
./restart_server.sh
```

The script will:
- Check if the key exists
- Load it from .env
- Start the server with the key available

---

## Verify It Works

After server starts, try a query:

**Open**: http://localhost:8000/ui/query.html

**Test query**: "How many repos do we have?"

**Expected**: Should work without 503 error

---

## Current .env File

Your `.env` currently has:
- ✅ GITHUB_TOKEN (set)
- ❌ OPENAI_API_KEY (missing - needs to be added)

---

## Quick Check

After adding the key, verify it's there:

```bash
grep OPENAI_API_KEY .env
```

Should show:
```
OPENAI_API_KEY=sk-...
```

---

**Next Step**: Add your OpenAI API key to `.env` file, then run `./restart_server.sh`
