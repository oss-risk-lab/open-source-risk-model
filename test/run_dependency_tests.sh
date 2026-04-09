#!/bin/bash
# Test runner for Dependency Graph feature
# Runs all dependency-related tests with various options

set -e

echo "=========================================="
echo "Dependency Graph Test Suite"
echo "=========================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "Error: pytest is not installed"
    echo "Install with: pip install pytest pytest-cov hypothesis"
    exit 1
fi

# Parse command line arguments
COVERAGE=false
VERBOSE=false
STATS=false
QUICK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --coverage|-c)
            COVERAGE=true
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --stats|-s)
            STATS=true
            shift
            ;;
        --quick|-q)
            QUICK=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -c, --coverage    Generate coverage report"
            echo "  -v, --verbose     Verbose output"
            echo "  -s, --stats       Show Hypothesis statistics"
            echo "  -q, --quick       Quick run (fewer examples)"
            echo "  -h, --help        Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="pytest"
TEST_FILES="test/test_dependency_parsers.py test/test_package_resolver.py test/test_dependency_integration.py test/test_dependency_properties.py"

if [ "$VERBOSE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v"
else
    PYTEST_CMD="$PYTEST_CMD -q"
fi

if [ "$COVERAGE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=src/open_source_risk_model/dependencies --cov-report=html --cov-report=term"
fi

if [ "$STATS" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --hypothesis-show-statistics"
fi

if [ "$QUICK" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --hypothesis-profile=quick"
fi

# Run tests
echo -e "${BLUE}Running tests...${NC}"
echo "Command: $PYTEST_CMD $TEST_FILES"
echo ""

$PYTEST_CMD $TEST_FILES

# Show coverage report location if generated
if [ "$COVERAGE" = true ]; then
    echo ""
    echo -e "${GREEN}Coverage report generated!${NC}"
    echo "View HTML report: open htmlcov/index.html"
fi

echo ""
echo -e "${GREEN}=========================================="
echo "All tests completed!"
echo -e "==========================================${NC}"
