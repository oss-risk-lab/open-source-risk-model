# 🚀 Local Site Quick Start Guide

## ✅ Server is Running!

Your API server is now running at: **http://localhost:8000**

## 🌐 Ways to Explore

### 1. Dependency Explorer UI (Recommended)

Open the interactive dependency explorer:

```bash
open ui/dependency-explorer.html
```

Or manually open: `ui/dependency-explorer.html` in your browser

**Features:**
- 📦 Get dependencies for any repository
- 🔍 Find repositories that depend on a package
- 🎨 Beautiful, interactive interface
- 📊 Real-time API calls

### 2. API Documentation (Swagger UI)

Interactive API documentation with "Try it out" feature:

```bash
open http://localhost:8000/docs
```

Or visit: http://localhost:8000/docs

**Features:**
- Complete API reference
- Try endpoints directly in browser
- See request/response examples
- Authentication testing

### 3. Alternative API Docs (ReDoc)

Clean, readable API documentation:

```bash
open http://localhost:8000/redoc
```

Or visit: http://localhost:8000/redoc

### 4. Graph Visualization UI

Explore supply chain graphs visually:

```bash
open ui/graph.html
```

Or manually open: `ui/graph.html` in your browser

## 🧪 Quick API Tests

### Test 1: Health Check
```bash
curl http://localhost:8000/api/health
```

Expected: `{"status":"ok"}`

### Test 2: Get Dependencies (if endpoint implemented)
```bash
curl "http://localhost:8000/api/repos/pallets/flask/dependencies"
```

### Test 3: Find Dependents (if endpoint implemented)
```bash
curl "http://localhost:8000/api/packages/requests/dependents?registry=pypi"
```

### Test 4: Get Graph
```bash
curl "http://localhost:8000/api/graph?repo=numpy/numpy"
```

## 📝 Example Repositories to Try

### Python Projects
- `pallets/flask` - Popular web framework
- `psf/requests` - HTTP library
- `django/django` - Web framework
- `numpy/numpy` - Scientific computing

### JavaScript Projects
- `facebook/react` - UI library
- `expressjs/express` - Web framework
- `lodash/lodash` - Utility library
- `axios/axios` - HTTP client

## 🛠️ Server Management

### Check Server Status
The server is running in the background. Check the terminal output:
```bash
# Server should show:
# INFO: Uvicorn running on http://127.0.0.1:8000
# INFO: Application startup complete.
```

### Stop the Server
If you need to stop the server:
1. Find the terminal where it's running
2. Press `Ctrl+C`

Or kill the process:
```bash
lsof -ti:8000 | xargs kill -9
```

### Restart the Server
```bash
GRAPH_PARSE_DEPENDENCIES=true python3 -m uvicorn api.app:app --reload --port 8000
```

## 🔧 Configuration

The server is running with dependency parsing enabled:
- `GRAPH_PARSE_DEPENDENCIES=true`

To change configuration, set environment variables:
```bash
export GRAPH_PARSE_DEPENDENCIES=true
export GRAPH_MAX_DEPENDENCIES=100
export GITHUB_TOKEN=your_token_here  # For higher rate limits
```

## 📚 Documentation Files

- **User Guide**: `docs/DEPENDENCY_GRAPH_GUIDE.md`
- **Quick Reference**: `docs/DEPENDENCY_QUICK_REFERENCE.md`
- **API Docs**: `docs/API.md`
- **Test Docs**: `test/README_DEPENDENCY_TESTS.md`

## 🐛 Troubleshooting

### Port Already in Use
If port 8000 is busy:
```bash
# Use a different port
uvicorn api.app:app --reload --port 8001
```

### Module Not Found
If you see import errors:
```bash
pip3 install -e .
```

### API Returns 404
Check that the endpoint is implemented in `api/app.py`

### CORS Issues
The API has CORS enabled for local development

## 🎯 Next Steps

1. **Open the Dependency Explorer**: `open ui/dependency-explorer.html`
2. **Try the Swagger UI**: `open http://localhost:8000/docs`
3. **Test with real repositories**: Use the examples above
4. **Read the documentation**: Check out the guides in `docs/`

## 💡 Tips

- Use the Swagger UI to test endpoints interactively
- The Dependency Explorer provides a user-friendly interface
- Check server logs for debugging
- Use `?refresh=true` to bypass cache
- Set `GITHUB_TOKEN` for higher API rate limits

---

**Server Status**: ✅ Running on http://localhost:8000

**Ready to explore!** 🚀

