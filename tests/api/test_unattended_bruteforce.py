"""Tests for unattended brute force API endpoints"""
import pytest
import json


class TestUnattendedBruteforceValidation:
    """Tests for /api/unattended-bruteforce-validate endpoint"""

    def test_validate_csv_success(self, client, sample_csv_valid):
        """Test successful CSV validation"""
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': sample_csv_valid}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['valid'] == True
        assert 'tests' in data
        assert 'total_combinations' in data
        assert len(data['tests']) > 0

    def test_validate_csv_empty(self, client):
        """Test validation with empty CSV"""
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': ''}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['valid'] == False
        assert 'errors' in data

    def test_validate_csv_invalid_paths(self, client, sample_csv_invalid):
        """Test validation with invalid file paths"""
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': sample_csv_invalid}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['valid'] == False
        assert len(data['errors']) > 0

    def test_validate_csv_invalid_numeric(self, client):
        """Test validation with invalid numeric parameters"""
        csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/path/to/file.py,/path/to/ohlc.csv,,length,invalid,10,1
'''
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': csv_content}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['valid'] == False

    def test_validate_csv_param_from_gte_to(self, client):
        """Test validation when param_from >= param_to"""
        csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,length,10,10,1
'''
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': csv_content}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['valid'] == False

    def test_validate_csv_combinations_under_limit(self, client):
        """Test that combinations stay under 500K limit per test"""
        csv_content = '''test_sequence_id,python_file_path,main_ohlc_path,additional_ohlc_path,parameter_name,param_from,param_to,param_step
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,length,1,10,1
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,mult,0.1,1,0.1
TEST_001,/Users/saransh/StrategyTester_v1/uploads/version_11.py,/Users/saransh/StrategyTester_v1/uploads/OANDA_XAUUSD_23min.csv,,ema9Len,1,10,1
'''
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': csv_content}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['valid'] == True
        # 10 * 10 * 10 = 1000 combinations (should be under 500K)
        assert data['tests'][0]['combinations'] == 1000


class TestUnattendedBruteforceExecution:
    """Tests for /api/unattended-bruteforce-execute endpoint"""

    def test_execute_with_valid_csv(self, client, sample_csv_valid):
        """Test execution with valid CSV"""
        response = client.post(
            '/api/unattended-bruteforce-execute',
            json={'csv_content': sample_csv_valid}
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert data['message'] == 'Execution started'

    def test_execute_with_empty_csv(self, client):
        """Test execution with empty CSV"""
        response = client.post(
            '/api/unattended-bruteforce-execute',
            json={'csv_content': ''}
        )

        assert response.status_code in [400, 422]

    def test_execute_without_csv(self, client):
        """Test execution without CSV content"""
        response = client.post('/api/unattended-bruteforce-execute', json={})
        assert response.status_code in [400, 422]


class TestUnattendedBruteforceProgress:
    """Tests for /api/unattended-bruteforce-progress endpoint"""

    def test_get_progress_when_no_execution(self, client):
        """Test getting progress when nothing is running"""
        response = client.get('/api/unattended-bruteforce-progress')

        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data


class TestUnattendedBruteforceStop:
    """Tests for /api/unattended-bruteforce-stop endpoint"""

    def test_stop_when_no_execution(self, client):
        """Test stopping when nothing is running"""
        response = client.post('/api/unattended-bruteforce-stop')

        assert response.status_code in [400, 200]  # May return 400 or 200 with message


class TestUnattendedBruteforceFinalResults:
    """Tests for /api/unattended-bruteforce-final-results endpoint"""

    def test_get_final_results_default(self, client):
        """Test getting final results"""
        response = client.get('/api/unattended-bruteforce-final-results')

        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'execution_results' in data
        assert 'output_directory' in data
