# Contributing to Open Source Risk Model

Thank you for your interest in contributing to this project!

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/open-source-risk-model.git
cd open-source-risk-model
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package in development mode:
```bash
pip install -e ".[dev]"
```

4. Set up your environment variables:
```bash
cp .env.example .env
# Edit .env and add your GitHub token
```

## Running Tests

Run all tests:
```bash
pytest
```

Run specific test file:
```bash
pytest test/test_option_a.py
```

## Code Style

This project uses Ruff for linting and formatting:

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

## Project Structure

- `src/open_source_risk_model/` - Core library code
- `test/` - Unit tests
- `api/` - FastAPI web service
- `data/` - Baseline populations and cached data
- `docs/` - Documentation
- `spikes/` - Experimental scripts

## Making Changes

1. Create a new branch for your feature/fix
2. Make your changes
3. Add tests for new functionality
4. Ensure all tests pass
5. Update documentation as needed
6. Submit a pull request

## Commit Messages

Use clear, descriptive commit messages:
- `feat: add new risk mapping strategy`
- `fix: correct percentile calculation in option_b`
- `docs: update API documentation`
- `test: add tests for composite scoring`

## Questions?

Open an issue for discussion before starting major changes.
