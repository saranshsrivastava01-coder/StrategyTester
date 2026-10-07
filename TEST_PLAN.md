# Regression Test Suite - StrategyTester v1

## Overview
This document outlines the comprehensive regression test suite for the StrategyTester application. The goal is to ensure that all existing functionality continues to work correctly when new features are added.

## Application Structure

### Pages & Features
1. **Reconciliation Page** - Pine Script, Python Strategy, Excel, OHLC Data uploads and analysis
2. **Strategy Tester Page** - Backtest analysis with Python strategies and OHLC data
3. **Brute Force Page** - Parameter optimization with combination generation
4. **Unattended Brute Force Page** - Batch testing via CSV with parallel execution
5. **Add Data Modal** - CSV template builder in unattended brute force

### Core Functionalities

#### Backend APIs
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/upload-python-file` | POST | Upload and extract Python strategy parameters |
| `/api/upload-excel-file` | POST | Upload strategy output Excel |
| `/api/upload-ohlc-file` | POST | Upload OHLC CSV data |
| `/api/upload-pine-script` | POST | Upload Pine Script file |
| `/api/analyze/<filename>` | GET | Analyze uploaded file |
| `/api/delete/<filename>` | DELETE | Delete uploaded file |
| `/api/brute-force-progress` | GET | Get brute force execution progress |
| `/api/brute-force-stop` | POST | Stop active brute force |
| `/api/brute-force-final-results` | GET | Get final brute force results |
| `/api/unattended-bruteforce-validate` | POST | Validate CSV for unattended testing |
| `/api/unattended-bruteforce-execute` | POST | Execute unattended brute force |
| `/api/unattended-bruteforce-progress` | GET | Get execution progress |
| `/api/unattended-bruteforce-stop` | POST | Stop unattended execution |
| `/api/unattended-bruteforce-final-results` | GET | Get final results |

#### Data Processing
- CSV validation and parsing
- Parameter combination generation
- Float precision handling (epsilon tolerance)
- File path verification and security

#### UI Features
- Real-time progress tracking
- Dynamic test tiles with completion status
- File upload handlers
- Dropdown parameter population
- Modal popups
- CSV preview and download

## Test Categories

### 1. API Endpoint Tests
- File upload validation
- Parameter extraction
- CSV parsing and validation
- Error handling
- File path security
- Progress tracking

### 2. Data Processing Tests
- Combination generation accuracy
- Float precision handling
- Parameter range validation
- Numeric vs. non-numeric parameter handling

### 3. Integration Tests
- End-to-end execution workflows
- Multi-test sequential execution
- Progress accumulation
- Completion detection
- Result aggregation

### 4. UI Tests (Manual/Automated)
- Page navigation
- Form submission
- Modal interactions
- Progress display
- File downloads

### 5. Regression Tests
- Ensure no breaking changes
- Validate all endpoints work
- Check data integrity
- Verify progress calculation

## Test Execution

### Running Tests
```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/api/test_uploads.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

### Test Data
- Sample Python strategies in `tests/fixtures/strategies/`
- Sample OHLC CSV in `tests/fixtures/data/`
- Sample Excel files in `tests/fixtures/excel/`
- CSV test cases in `tests/fixtures/csv/`

## Coverage Requirements

### Minimum Coverage Targets
- Backend APIs: 85%+
- Data processing: 90%+
- UI interactions: Manual testing (automated where possible)
- Overall: 80%+

## CI/CD Integration
- Tests run on every PR
- Tests must pass before merge to main
- Coverage reports generated
- Regression tests run nightly

## Continuous Updates
- Add tests for every new feature
- Update regression tests when changing existing features
- Document any breaking changes
- Maintain test data freshness

## Status
- [ ] API endpoint tests
- [ ] Data processing tests
- [ ] Integration tests
- [ ] UI regression tests
- [ ] Documentation complete
- [ ] CI/CD pipeline setup
