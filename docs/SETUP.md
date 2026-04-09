# Setup Guide

Detailed instructions for setting up the Open Source Risk Model project.

## System Requirements

- Python 3.9 or higher
- Git
- 500 MB disk space (more if caching many repositories)
- Internet connection for GitHub API access

## Step-by-Step Setup

### 1. Install Python

Check your Python version:
```bash
python --version
```

If you need to install or upgrade Python:
- **macOS:** `brew install python@3.11`
- **Ubuntu/Debian:** `sudo apt install python3.11`
- **Windows:** Download from [python.org](https://www.python.org/downloads/)

### 2. Clone the Repository

```bash
git clone https://github.com/yourusername/open-source-risk-model.git
cd open-source-risk-model
```

### 3. Create Virtual Environment

```bash
python -m venv venv
```

Activate it:
- **macOS/Linux:** `source venv/bin/activate`
- **Windows:** `venv\Scripts\activate`

You should see `(venv)` in your terminal prompt.

### 4. Install Dependencies

```bash
pip install -e ".[dev]"
```

This installs:
- Core dependencies (PyGithub, FastAPI, etc.)
- Development tools (pytest, ruff)
- The package in editable mode

### 5. Configure GitHub Token

Create a GitHub personal access token:

1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Give it a name like "Risk Model API"
4. Select scope: `public_repo`
5. Click "Generate token"
6. Copy the token (starts with `ghp_`)

Create your `.env` file:
```bash
cp .env.example .env
```

Edit `.env` and add your token:
```
GITHUB_TOKEN=ghp_your_actual_token_here
```

### 6. Configure LLM Provider (Optional)

If you plan to use the intelligent query API with LLM-powered intent classification, configure an LLM provider:

**OpenAI Setup:**

1. Get an API key from https://platform.openai.com/api-keys
2. Add to your `.env` file:
```
# LLM Provider Configuration (optional)
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-api-key-here
# OPENAI_BASE_URL=https://api.openai.com/v1  # Optional
# OPENAI_ORGANIZATION=org-your-org-id  # Optional
```

**Testing Without API Keys:**

All unit tests use a mock provider and don't require API keys:
```bash
pytest -m "not integration" -v
```

Integration tests (which use real API calls) are automatically skipped if no API key is present.

**See Also:** [LLM Module README](../src/open_source_risk_model/llm/README.md) for detailed configuration.

### 7. Verify Installation

Test the GitHub API connection:
```bash
python test/github_api_hello.py
```

You should see your GitHub username and rate limit info.

Run the test suite:
```bash
pytest
```

All tests should pass.

### 8. Start the API Server

```bash
uvicorn api.app:app --reload
```

Visit http://localhost:8000/docs to see the interactive API documentation.

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError: No module named 'open_source_risk_model'`:

1. Make sure you installed with `-e` flag: `pip install -e .`
2. Check that you're in the project root directory
3. Verify your virtual environment is activated

### GitHub API Rate Limits

Without authentication:
- 60 requests/hour

With authentication:
- 5,000 requests/hour

If you hit rate limits:
- Wait for the limit to reset
- Use cached data (`refresh=false`)
- Check your token is properly configured

### Permission Errors

If you see permission errors when installing:
- Don't use `sudo pip install`
- Make sure your virtual environment is activated
- Try: `pip install --user -e .`

## Next Steps

- Read the [API Documentation](API.md)
- Explore the [Data Guide](DATA_GUIDE.md)
- Check out [Contributing Guidelines](../CONTRIBUTING.md)
- Try scoring some repositories!

## Development Tools

### Code Formatting

```bash
ruff format .
```

### Linting

```bash
ruff check .
ruff check --fix .  # Auto-fix issues
```

### Running Specific Tests

```bash
pytest test/test_option_a.py
pytest -k "test_composite"  # Run tests matching pattern
pytest -v  # Verbose output
```

## IDE Setup

### VS Code

Recommended extensions:
- Python
- Pylance
- Ruff

Settings (`.vscode/settings.json`):
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["test"],
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true
  }
}
```

### PyCharm

1. Open project
2. File → Settings → Project → Python Interpreter
3. Add interpreter → Existing environment
4. Select `venv/bin/python`
5. Enable pytest: Settings → Tools → Python Integrated Tools → Testing → pytest
