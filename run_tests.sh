#!/bin/bash

# Regression Test Suite Runner
# This script runs the complete test suite with coverage reporting

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "========================================"
echo "StrategyTester v1 - Regression Test Suite"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}pytest not found. Installing test dependencies...${NC}"
    pip install -r tests/requirements-test.txt
fi

# Parse command line arguments
TEST_PATTERN="${1:-.}"
COVERAGE="${2:-}"

echo -e "${YELLOW}Running tests matching: $TEST_PATTERN${NC}"
echo ""

# Run tests with coverage
if [ "$COVERAGE" == "--coverage" ] || [ "$COVERAGE" == "-c" ]; then
    echo -e "${YELLOW}Running with coverage report...${NC}"
    pytest tests/$TEST_PATTERN -v \
        --cov=. \
        --cov-report=html \
        --cov-report=term-missing \
        --cov-report=xml \
        --junitxml=test-results.xml

    echo ""
    echo -e "${GREEN}✅ Coverage report generated: htmlcov/index.html${NC}"
else
    echo -e "${YELLOW}Running tests (no coverage)...${NC}"
    pytest tests/$TEST_PATTERN -v --junitxml=test-results.xml
fi

echo ""
echo -e "${GREEN}========================================"
echo "✅ Test suite completed successfully!"
echo "========================================${NC}"
echo ""
echo "Usage:"
echo "  ./run_tests.sh                    # Run all tests"
echo "  ./run_tests.sh api/test_*.py      # Run API tests"
echo "  ./run_tests.sh --coverage         # Run with coverage"
echo "  ./run_tests.sh api -c             # Run API tests with coverage"
