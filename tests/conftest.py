"""Pytest configuration and shared fixtures for regression tests"""
import pytest
import json
import tempfile
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from strategy_ui import app
from unattended_bruteforce import UnattendedBruteForceEngine


@pytest.fixture
def client():
    """Flask test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def temp_dir():
    """Temporary directory for test files"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_python_file(temp_dir):
    """Create a sample Python strategy file"""
    python_code = '''
import pandas as pd
import numpy as np

def run_strategy(ohlc_data, **params):
    """Sample strategy for testing"""
    length = params.get('length', 20)
    mult = params.get('mult', 1.0)

    # Simple moving average strategy
    ohlc_data['sma'] = ohlc_data['close'].rolling(window=length).mean()
    ohlc_data['signal'] = (ohlc_data['close'] > ohlc_data['sma']).astype(int)

    return {
        'trades': len(ohlc_data[ohlc_data['signal'] == 1]),
        'win_rate': 0.5,
        'profit': 100.0
    }

DEFAULT_PARAMS = {
    'length': {'default': 20, 'min': 5, 'max': 50, 'step': 1},
    'mult': {'default': 1.0, 'min': 0.1, 'max': 5.0, 'step': 0.1}
}
'''
    filepath = os.path.join(temp_dir, 'sample_strategy.py')
    with open(filepath, 'w') as f:
        f.write(python_code)
    return filepath


@pytest.fixture
def sample_ohlc_csv(temp_dir):
    """Create a sample OHLC CSV file"""
    csv_content = '''time,open,high,low,close,volume
2024-01-01 00:00,100.0,101.0,99.0,100.5,1000
2024-01-01 01:00,100.5,102.0,100.0,101.5,1100
2024-01-01 02:00,101.5,103.0,101.0,102.5,1200
2024-01-01 03:00,102.5,104.0,102.0,103.5,1300
2024-01-01 04:00,103.5,105.0,103.0,104.5,1400
2024-01-01 05:00,104.5,106.0,104.0,105.5,1500
2024-01-01 06:00,105.5,107.0,105.0,106.5,1600
2024-01-01 07:00,106.5,108.0,106.0,107.5,1700
2024-01-01 08:00,107.5,109.0,107.0,108.5,1800
2024-01-01 09:00,108.5,110.0,108.0,109.5,1900
'''
    filepath = os.path.join(temp_dir, 'sample_ohlc.csv')
    with open(filepath, 'w') as f:
        f.write(csv_content)
    return filepath


@pytest.fixture
def sample_csv_valid(temp_dir):
    """Create a valid CSV for unattended brute force"""
    csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,length,1,10,1
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,mult,0.1,1,0.1
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,enablePyramiding,True,True,1
'''
    return csv_content


@pytest.fixture
def sample_csv_invalid():
    """Create an invalid CSV for testing error handling"""
    csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/nonexistent/path.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,length,1,10,1
'''
    return csv_content
