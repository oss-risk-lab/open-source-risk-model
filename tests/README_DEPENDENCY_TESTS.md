# Dependency Graph Test Suite

## Overview

This directory contains comprehensive tests for the Dependency Graph feature, covering parsing, resolution, integration, and property-based testing.

## Test Files

### 1. test_dependency_parsers.py (30 tests)
Unit tests for dependency manifest parsers.

**Coverage:**
- RequirementsTxtParser (13 tests)
  - Simple package parsing
  - Versioned packages
  - Version constraints
  - Extras and environment markers
  - Comment and empty line handling
  - Complex file parsing
  
- PyProjectTomlParser (5 tests)
  - PEP 621 dependencies
  - Optional dependencies
  - Poetry format
  - Error handling
  
- PackageJsonParser (5 tests)
  - Production dependencies
  - Development dependencies
  - Optional dependencies
  - Error handling
  
- DependencyParserRegistry (6 tests)
  - Parser selection
  - File parsing
  - Unknown file types

### 2. test_package_resolver.py (21 tests)
Unit tests for package-to-repository resolution.

**Coverage:**
- GitHub URL extraction (6 formats)
- Repository format validation
- PyPI resolution (project_urls, home_page)
- npm resolution (repository, homepage)
- Resolution caching
- Error handling (timeouts, connection errors)
- Unresolved packages

### 3. test_dependency_integration.py (10 tests)
Integration tests for end-to-end workflows.

**Coverage:**
- Complete Python repository flow
- Complete JavaScript repository flow
- Package resolution caching
- Dependent queries
- Dependency updates
- Graph node inclusion
- Multiple manifest files
- API endpoint integration

### 4. test_dependency_properties.py (15 tests)
Property-based tests using Hypothesis.

**Coverage:**
- Parser invariants (never crashes, idempotent)
- Resolver invariants (URL extraction, format validation)
- Fuzzing with generated inputs
- Edge case discovery

## Running Tests

### Quick Start

```bash
# Run all tests
./test/run_dependency_tests.sh

# Run with coverage
./test/run_dependency_tests.sh --coverage

# Run with verbose output
./test/run_dependency_tests.sh --verbose

# Run with Hypothesis statistics
./test/run_dependency_tests.sh --stats
```

### Individual Test Suites

```bash
# Unit tests only
pytest test/test_dependency_parsers.py test/test_package_resolver.py -v

# Integration tests only
pytest test/test_dependency_integration.py -v

# Property tests only
pytest test/test_dependency_properties.py -v

# Specific test class
pytest test/test_dependency_parsers.py::TestRequirementsTxtParser -v

# Specific test method
pytest test/test_dependency_parsers.py::TestRequirementsTxtParser::test_parse_simple_package -v
```

### With Coverage

```bash
# Generate coverage report
pytest test/test_dependency_*.py --cov=src/open_source_risk_model/dependencies --cov-report=html

# View coverage report
open htmlcov/index.html
```

### With Hypothesis Options

```bash
# Show statistics
pytest test/test_dependency_properties.py --hypothesis-show-statistics

# More examples
pytest test/test_dependency_properties.py --hypothesis-seed=12345

# Verbose output
pytest test/test_dependency_properties.py --hypothesis-verbosity=verbose
```

## Test Statistics

- **Total Tests**: 76 tests
- **Unit Tests**: 51 tests (67%)
- **Integration Tests**: 10 tests (13%)
- **Property Tests**: 15 tests (20%)

### Execution Time
- Unit tests: ~2-3 seconds
- Integration tests: ~3-5 seconds
- Property tests: ~5-10 seconds
- **Total**: ~10-18 seconds

## Requirements

Install test dependencies:

```bash
pip install pytest pytest-cov hypothesis
```

Or from requirements:

```bash
pip install -r requirements-dev.txt
```

## Test Structure

### Unit Tests
- Test individual components in isolation
- Mock external dependencies (API calls, database)
- Fast execution
- High coverage of edge cases

### Integration Tests
- Test complete workflows
- Use temporary test database
- Mock external APIs (GitHub, PyPI, npm)
- Verify component interactions

### Property Tests
- Test invariants that should always hold
- Generate random inputs with Hypothesis
- Discover edge cases automatically
- Ensure robustness

## Writing New Tests

### Unit Test Template

```python
class TestNewComponent:
    """Test NewComponent class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.component = NewComponent()
    
    def test_basic_functionality(self):
        """Test basic functionality."""
        result = self.component.do_something()
        assert result == expected_value
    
    def test_error_handling(self):
        """Test error handling."""
        with pytest.raises(ExpectedError):
            self.component.do_invalid_thing()
```

### Integration Test Template

```python
class TestNewIntegration:
    """Integration tests for new feature."""
    
    def setup_method(self):
        """Set up test database."""
        self.test_db = tempfile.mktemp(suffix=".db")
    
    def teardown_method(self):
        """Clean up test database."""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    @patch('external.api.call')
    def test_end_to_end_flow(self, mock_api):
        """Test complete workflow."""
        # Setup mocks
        mock_api.return_value = mock_response
        
        # Execute workflow
        result = complete_workflow()
        
        # Verify results
        assert result.success
```

### Property Test Template

```python
from hypothesis import given, strategies as st

class TestNewProperties:
    """Property-based tests for new component."""
    
    @given(input_data=st.text(min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_never_crashes(self, input_data):
        """Property: Component should never crash on any input."""
        try:
            result = component.process(input_data)
            assert isinstance(result, ExpectedType)
        except Exception as e:
            pytest.fail(f"Component crashed: {e}")
```

## Continuous Integration

### GitHub Actions

```yaml
name: Dependency Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
      - name: Run tests
        run: ./test/run_dependency_tests.sh --coverage
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

## Troubleshooting

### Tests Failing

1. **Import errors**: Ensure `src/` is in PYTHONPATH
   ```bash
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"
   ```

2. **Database errors**: Check test database cleanup
   ```bash
   rm -f /tmp/*.db
   ```

3. **Mock errors**: Verify mock paths match actual imports
   ```python
   @patch('src.module.function')  # Correct
   @patch('module.function')      # Wrong
   ```

### Slow Tests

1. **Reduce Hypothesis examples**:
   ```bash
   pytest --hypothesis-profile=quick
   ```

2. **Run specific tests**:
   ```bash
   pytest test/test_dependency_parsers.py -k "test_parse_simple"
   ```

3. **Disable coverage**:
   ```bash
   pytest test/test_dependency_*.py  # Without --cov
   ```

### Coverage Issues

1. **Missing coverage**: Check that all code paths are tested
2. **Low coverage**: Add tests for uncovered branches
3. **Coverage report**: View HTML report for details
   ```bash
   open htmlcov/index.html
   ```

## Best Practices

1. **Test naming**: Use descriptive names that explain what is being tested
2. **One assertion per test**: Keep tests focused and simple
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Mock external dependencies**: Don't make real API calls in tests
5. **Clean up resources**: Use teardown methods to clean up test data
6. **Test edge cases**: Include tests for boundary conditions
7. **Document complex tests**: Add comments explaining non-obvious test logic

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Hypothesis documentation](https://hypothesis.readthedocs.io/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [Dependency Graph User Guide](../docs/DEPENDENCY_GRAPH_GUIDE.md)

## Support

For questions or issues with tests:
1. Check test output for error messages
2. Review test documentation above
3. Check [GitHub Issues](https://github.com/your-org/repo/issues)
4. Contact the development team

