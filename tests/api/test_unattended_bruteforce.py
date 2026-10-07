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

    def test_validate_csv_bad_request(self, client):
        """Test validation with empty CSV returns 400"""
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': ''}
        )
        assert response.status_code == 400

    def test_validate_csv_missing_content(self, client):
        """Test validation without CSV content"""
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={}
        )
        assert response.status_code == 400

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

        assert response.status_code == 400

    def test_execute_without_csv(self, client):
        """Test execution without CSV content"""
        response = client.post('/api/unattended-bruteforce-execute', json={})
        assert response.status_code == 400


class TestUnattendedBruteforceProgress:
    """Tests for /api/unattended-bruteforce-progress endpoint"""

    def test_get_progress_endpoint_exists(self, client):
        """Test that progress endpoint is accessible"""
        response = client.get('/api/unattended-bruteforce-progress')
        # Should return either 200 or 400 depending on execution state
        assert response.status_code in [200, 400]


class TestUnattendedBruteforceStop:
    """Tests for /api/unattended-bruteforce-stop endpoint"""

    def test_stop_execution_endpoint(self, client):
        """Test stop execution endpoint"""
        response = client.post('/api/unattended-bruteforce-stop')
        # Should return 200 with message or 400 if nothing to stop
        assert response.status_code in [200, 400]


class TestUnattendedBruteforceFinalResults:
    """Tests for /api/unattended-bruteforce-final-results endpoint"""

    def test_get_final_results_endpoint(self, client):
        """Test getting final results endpoint"""
        response = client.get('/api/unattended-bruteforce-final-results')
        # Endpoint should be accessible
        assert response.status_code in [200, 400]
        data = json.loads(response.data)
        # Should have execution_results or error
        assert 'execution_results' in data or 'error' in data
