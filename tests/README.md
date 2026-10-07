# Regression Test Suite

Comprehensive test suite for StrategyTester v1 application to ensure no regressions when adding new features.

## Overview

This test suite covers:
- ✅ API endpoints (file uploads, validation, execution)
- ✅ Data processing (combination generation, CSV parsing)
- ✅ Integration workflows (end-to-end execution)
- ✅ Security (path traversal prevention, input validation)
- ✅ Edge cases (boundary conditions, error handling)

## Test Structure

```
tests/
├── api/
│   ├── test_file_uploads.py        # File upload endpoint tests
│   ├── test_unattended_bruteforce.py  # Unattended BF API tests
│   └── test_data_processing.py     # Data processing and combination tests
├── fixtures/
│   ├── strategies/                 # Sample Python strategy files
│   ├── data/                       # Sample OHLC CSV files
│   ├── excel/                      # Sample Excel files
│   └── csv/                        # Sample CSV test cases
├── integration/                    # Integration/end-to-end tests
├── conftest.py                     # Pytest configuration & fixtures
├── requirements-test.txt           # Testing dependencies
├── README.md                       # This file
└── .gitignore                      # Ignore test artifacts
```

## Setup

### 1. Install Test Dependencies
```bash
cd /Users/saransh/StrategyTester_v1
pip install -r tests/requirements-test.txt
```

### 2. Verify Setup
```bash
pytest tests/ --co -q  # List all tests without running
```

## Running Tests

### Run All Tests
```bash
pytest tests/ -v
```

### Run Specific Test File
```bash
pytest tests/api/test_file_uploads.py -v
```

### Run Specific Test Class
```bash
pytest tests/api/test_file_uploads.py::TestPythonFileUpload -v
```

### Run Specific Test
```bash
pytest tests/api/test_file_uploads.py::TestPythonFileUpload::test_upload_python_file_success -v
```

### Run with Coverage Report
```bash
pytest tests/ --cov=. --cov-report=html --cov-report=term-missing
# Open htmlcov/index.html to view detailed coverage
```

### Run Tests Matching Pattern
```bash
pytest tests/ -k "upload" -v  # Run tests with "upload" in name
pytest tests/ -k "not slow" -v  # Skip tests marked as slow
```

## Test Categories

### API Endpoint Tests (tests/api/test_file_uploads.py)
- File upload success/failure scenarios
- Invalid file format handling
- Missing file handling
- Security (path traversal prevention)

### Unattended Bruteforce Tests (tests/api/test_unattended_bruteforce.py)
- CSV validation (success, empty, invalid)
- Invalid numeric parameters
- Parameter order validation (from < to)
- Combination count validation
- Execution start/stop
- Progress tracking
- Final results retrieval

### Data Processing Tests (tests/api/test_data_processing.py)
- Numeric combination generation
- Float precision handling (epsilon tolerance)
- Boolean parameter handling
- Large range combination counting
- CSV validation (all aspects)

## Coverage Requirements

- **Backend APIs**: 85%+ coverage
- **Data Processing**: 90%+ coverage
- **Overall**: 80%+ coverage

## Test Fixtures

Fixtures are defined in `conftest.py`:
- `client`: Flask test client
- `temp_dir`: Temporary directory for test files
- `sample_python_file`: Sample strategy file
- `sample_ohlc_csv`: Sample OHLC data
- `sample_csv_valid`: Valid unattended BF CSV
- `sample_csv_invalid`: Invalid CSV for error testing

## Continuous Integration

Tests should be run on every PR:
```bash
# CI/CD pipeline
pytest tests/ --cov=. --cov-report=xml --junitxml=test-results.xml
```

## Adding New Tests

When adding a new feature:

1. **Create test file** in appropriate category:
   ```bash
   tests/api/test_new_feature.py
   tests/integration/test_new_workflow.py
   ```

2. **Follow naming conventions**:
   - Test files: `test_*.py`
   - Test classes: `Test*`
   - Test methods: `test_*`

3. **Use fixtures** for common setup:
   ```python
   def test_something(self, client, sample_python_file):
       # Use fixtures for setup
       pass
   ```

4. **Add docstrings** to explain test purpose:
   ```python
   def test_upload_file_success(self, client, sample_file):
       """Test successful file upload with valid file"""
   ```

5. **Run tests locally** before committing:
   ```bash
   pytest tests/ -v
   ```

## Debugging Failed Tests

### Verbose Output
```bash
pytest tests/api/test_file_uploads.py::TestPythonFileUpload::test_upload_python_file_success -vv
```

### Show Print Statements
```bash
pytest tests/ -v -s
```

### Drop into Debugger
```bash
pytest tests/ --pdb  # Drop to pdb on failure
pytest tests/ --pdb-trace  # Drop at test start
```

### Run Single Test with Logging
```bash
pytest tests/api/test_file_uploads.py::TestPythonFileUpload::test_upload_python_file_success -v --log-cli-level=DEBUG
```

## Troubleshooting

### Import Errors
```bash
# Ensure project root is in PYTHONPATH
export PYTHONPATH=/Users/saransh/StrategyTester_v1:$PYTHONPATH
pytest tests/
```

### Missing Dependencies
```bash
pip install -r tests/requirements-test.txt --upgrade
```

### Port Already in Use (for integration tests)
```bash
# Kill any existing Flask processes
pkill -f "python.*strategy_ui.py"
```

## Best Practices

1. **Keep tests independent** - Each test should be runnable alone
2. **Use descriptive names** - Test name should explain what is being tested
3. **One assertion per test** - Or group related assertions
4. **Use fixtures** - Don't create setup code in tests
5. **Clean up** - Use fixtures that handle cleanup automatically
6. **Mock external calls** - Don't make real API calls in tests
7. **Document assumptions** - Explain why test exists

## Regression Testing Checklist

Before merging new features:
- [ ] All existing tests pass
- [ ] New feature has test coverage (>80%)
- [ ] No decrease in overall coverage
- [ ] Integration tests pass
- [ ] Manual smoke testing done
- [ ] Documentation updated

## Further Reading

- [Pytest Documentation](https://docs.pytest.org/)
- [Testing Best Practices](https://docs.pytest.org/en/stable/goodpractices.html)
- [Flask Testing](https://flask.palletsprojects.com/en/2.3.x/testing/)

## Contributing

To add tests:
1. Create test in appropriate module
2. Run locally: `pytest tests/ -v`
3. Commit with message: `test: add tests for <feature>`
4. Ensure CI passes

## Questions?

Refer to TEST_PLAN.md for high-level test strategy documentation.
