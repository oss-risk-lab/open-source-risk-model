# 🎯 Demo Quick Reference Card

**Print this out or keep it on a second screen during the demo**

---

## Key Stats to Mention

- **47 repos** with dependencies tracked
- **3,313 production dependencies** (excludes examples/tests/docs)
- **Top repo:** aiohttp with 521 dependencies
- **Query speed:** < 100ms for most queries
- **Test coverage:** 76+ passing tests

---

## Demo Queries (Copy-Paste Ready)

### In UI (ui/query.html):

1. `Show me dataset statistics`
2. `What depends on flask?`
3. `Show me React's dependencies`
4. `Which repos have the most dependencies?`
5. `Find all repos that depend on requests`
6. `Show me unresolved dependencies for angular`

### In Terminal (if needed):

```bash
# Start API
uvicorn api.app:app --reload

# Run demo script
./demo_query_api.sh

# Check data
sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_dependencies;"
```

---

## The 30-Second Pitch

> "We've built an AI-native supply chain intelligence platform. Ask questions in natural language - 'what depends on Flask?', 'which repos have the most dependencies?' - and get instant answers across your entire software supply chain. Unlike traditional scanners, we provide cross-repo intelligence for impact analysis. 47 repos, 3,313 production dependencies, fast queries, passing tests."

---

## Key Differentiators

1. **AI-native** - natural language queries
2. **Cross-repo** - supply chain impact analysis  
3. **Database-first** - fast, deterministic queries
4. **Package resolution** - PyPI/npm → GitHub mapping
5. **Extensible** - custom policies, compliance rules

---

## Questions & Answers

**Q: How many repos?**
A: 47 repos with 3,313 production dependencies. Can scale to 500-1,000 easily.

**Q: How accurate is the AI?**
A: AI only classifies intent. Data queries are deterministic SQL.

**Q: Different from Snyk?**
A: They're scanners. We're an intelligence platform with cross-repo queries.

**Q: When production-ready?**
A: Core is ready now. Need 1-2 weeks for automated ingestion & auth.

**Q: Business model?**
A: [Defer to dad - options: per-repo, per-user, enterprise, freemium]

**Q: Target customer?**
A: [Defer to dad - options: security teams, engineering teams, OSS maintainers]

---

## If Something Goes Wrong

**API won't start:**
- Check: `ps aux | grep uvicorn` (kill if already running)
- Try: `python -m uvicorn api.app:app --reload`

**UI shows errors:**
- Use terminal demo: `./demo_query_api.sh`
- Or Python script: `python test_query_api_live.py`

**Database locked:**
- Check: `ps aux | grep ingest` (kill if running)
- Wait 30 seconds and try again

**Dad wants to see code:**
- Show: `src/open_source_risk_model/query/`
- Run tests: `pytest test/test_query_api.py -v`

---

## Demo Flow Checklist

- [ ] Show stats (47 repos, 3,313 deps)
- [ ] Demo AI queries (6 examples)
- [ ] Explain cross-repo intelligence
- [ ] Show architecture diagram
- [ ] Discuss what's next
- [ ] Get feedback
- [ ] Agree on priorities

---

## What's Next (If Asked)

**Near-term (1-2 weeks):**
- Tree visualization
- CVE impact analysis
- Risk scoring

**Medium-term (1 month):**
- Automated ingestion
- Alerts (Slack/email)
- Custom risk policies

**Long-term (2-3 months):**
- Multi-tenant SaaS
- GitHub App
- Compliance reporting

---

## Confidence Boosters

✅ 76+ tests passing
✅ Clean, documented code
✅ Fast queries (<100ms)
✅ Real data (3,313 production deps)
✅ Working AI interface
✅ Production-ready architecture

---

**Remember:** This is real and working. Be confident. Let the demo speak for itself.

🚀 You've got this!
