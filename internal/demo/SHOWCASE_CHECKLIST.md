# Supply Chain Graph - Showcase Checklist

Use this checklist to prepare your project for demo/portfolio presentation.

## ✅ Completed (Path A)

- [x] Fix cache key issue (correctness bug)
- [x] Add explanation panel to UI
- [x] Create diverse repository testing script
- [x] Enhance README with compelling narrative
- [x] Add screenshots section to README
- [x] Comprehensive validation (200+ tests passing)
- [x] Documentation complete
- [x] Fix static file serving (UI now accessible at `/ui/graph.html`)

## 📸 Screenshots Needed

Create these 3 screenshots and save to `docs/images/`:

- [ ] `graph-visualization.png` - Full graph view of numpy/numpy or similar
  - Show the interactive graph with multiple node types
  - Include the filters panel and details panel
  - Make sure it looks clean and professional

- [ ] `node-details.png` - Details panel showing provenance
  - Click on a CVE or release node
  - Capture the details panel with metadata and provenance
  - Highlight the confidence scores

- [ ] `risk-score.png` - API response or score dashboard
  - Either screenshot the JSON response from `/api/score`
  - Or create a simple dashboard view
  - Show the risk breakdown and feature contributions

**Quick Screenshot Tips:**
- Use a clean browser window (no bookmarks bar, etc.)
- Zoom to 100% for crisp screenshots
- Use a tool like CleanShot X (Mac) or Greenshot (Windows)
- Crop to remove unnecessary whitespace
- Save as PNG for best quality

## 🚀 Deployment (Optional but Recommended)

- [ ] Choose a hosting platform:
  - [ ] Railway (easiest, free tier)
  - [ ] Heroku (classic choice)
  - [ ] Render (modern alternative)
  - [ ] DigitalOcean App Platform
  - [ ] Fly.io

- [ ] Set up environment variables on platform
  - `GITHUB_TOKEN` (required)
  - `LOG_LEVEL=INFO` (optional)

- [ ] Deploy and test
  - Verify `/health` endpoint works
  - Test `/api/graph?repo=numpy/numpy`
  - Test UI at `/ui/graph.html`

- [ ] Get a custom domain (optional)
  - Makes it more professional
  - Example: `supply-chain.yourdomain.com`

## 🎥 Demo Video (Optional but High Impact)

- [ ] Record 2-minute walkthrough showing:
  - [ ] Loading a repository (numpy/numpy)
  - [ ] Exploring the graph (click nodes, zoom, pan)
  - [ ] Showing provenance and confidence
  - [ ] Highlighting CVEs if present
  - [ ] Explaining what makes this useful

- [ ] Tools for recording:
  - Loom (easiest, web-based)
  - OBS Studio (free, powerful)
  - QuickTime (Mac built-in)
  - Windows Game Bar (Windows built-in)

- [ ] Upload to:
  - YouTube (unlisted or public)
  - Loom
  - Vimeo

- [ ] Add link to README

## 📝 Testing & Validation

- [ ] Run diverse repository tests:
  ```bash
  python scripts/test_diverse_repos.py
  ```

- [ ] Document interesting findings:
  - Which repos have the most CVEs?
  - Which have the best/worst risk scores?
  - Any surprising patterns?

- [ ] Add findings to README or blog post

## 👥 Get Feedback

Show the project to 3-5 people and ask:

- [ ] Person 1: ________________
  - What's confusing?
  - What's impressive?
  - What's missing?

- [ ] Person 2: ________________
  - What's confusing?
  - What's impressive?
  - What's missing?

- [ ] Person 3: ________________
  - What's confusing?
  - What's impressive?
  - What's missing?

- [ ] Person 4: ________________ (optional)
- [ ] Person 5: ________________ (optional)

## 📊 Portfolio/Resume Updates

- [ ] Add to portfolio website
  - Project title
  - Brief description
  - Link to live demo
  - Link to GitHub repo
  - Screenshots

- [ ] Update resume
  - Add to projects section
  - Highlight key technologies:
    - Python, FastAPI, vis.js
    - Property-based testing (Hypothesis)
    - Supply chain security
    - Graph visualization
    - Multi-source data integration

- [ ] Update LinkedIn
  - Add as a project
  - Share a post about it
  - Tag relevant skills

## 🔗 Links to Share

Prepare these links for easy sharing:

- [ ] GitHub repo: `https://github.com/yourusername/open-source-risk-model`
- [ ] Live demo: `https://your-deployment-url.com`
- [ ] Demo video: `https://youtube.com/...` or `https://loom.com/...`
- [ ] Documentation: Link to README or docs folder

## 📢 Optional: Write About It

- [ ] Blog post explaining:
  - The problem you're solving
  - Your approach
  - Interesting technical decisions
  - Lessons learned

- [ ] Share on:
  - [ ] Dev.to
  - [ ] Medium
  - [ ] Your personal blog
  - [ ] Hacker News (if you're brave!)
  - [ ] Reddit (r/programming, r/Python)

## 🎯 Next Decision Point

After completing the above, decide:

- [ ] **Path B (Technical Depth)**: Build SBOM/dependency graph traversal
- [ ] **Path C (Product Vision)**: Turn into monitoring SaaS
- [ ] **Done**: Move on to next project

## Notes

Use this space to track progress, ideas, or feedback:

---

**Started:** _______________  
**Completed:** _______________  
**Deployed URL:** _______________  
**Demo Video:** _______________

---

## Quick Commands Reference

```bash
# Start the API server
python -m uvicorn api.app:app --reload

# Run all tests
python -m pytest test/ -v

# Run diverse repo tests
python scripts/test_diverse_repos.py

# Run final validation
python -m pytest test/test_final_validation.py -v

# Check test coverage
python -m pytest test/ --cov=src --cov-report=html
```

---

**Remember:** The goal of Path A is to maximize immediate credibility and demo-ability. Focus on making it look professional and telling a compelling story. You can always add more features later!
