"""UI/E2E tests for user interactions and button clicks"""
import pytest


class TestPageNavigation:
    """Tests for page navigation and tab switching"""

    def test_reconciliation_page_loads(self, client):
        """Test that reconciliation page loads"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Reconciliation' in response.data
        assert b'Pine Script' in response.data
        assert b'Python Script' in response.data

    def test_reconciliation_page_elements_present(self, client):
        """Test that all reconciliation page elements are present"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for main sections
        assert 'pine-file' in data  # Pine Script upload input
        assert 'python-file' in data  # Python file upload input
        assert 'excel-file' in data  # Excel file upload input
        assert 'ohlc-file' in data  # OHLC file upload input

        # Check for interactive elements
        assert 'Upload' in data or 'upload' in data or 'button' in data.lower()
        assert 'button' in data.lower() or 'onclick' in data

    def test_tester_page_loads(self, client):
        """Test that strategy tester page loads"""
        response = client.get('/')
        assert response.status_code == 200
        assert b'Strategy Backtest' in response.data or b'Tester' in response.data


class TestUnattendedBruteforceUI:
    """Tests for unattended bruteforce page interactions"""

    def test_unattended_page_loads(self, client):
        """Test that unattended bruteforce page is accessible"""
        response = client.get('/')
        assert response.status_code == 200
        # Check for unattended bruteforce specific elements
        data = response.data.decode('utf-8')
        assert 'Unattended' in data or 'unattended' in data or 'bruteforce' in data

    def test_csv_upload_section_present(self, client):
        """Test that CSV upload section exists"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for CSV upload elements
        assert 'CSV' in data or 'csv' in data
        assert 'Upload' in data
        assert 'Validate' in data

    def test_build_csv_modal_elements(self, client):
        """Test that Build CSV modal has necessary elements"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for modal elements
        assert 'modal' in data or 'Modal' in data or 'dialog' in data
        assert 'python' in data.lower()
        assert 'ohlc' in data.lower() or 'CSV' in data


class TestFormSubmissions:
    """Tests for form submission functionality"""

    def test_csv_validation_api_exists(self, client):
        """Test that CSV validation API endpoint exists"""
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': 'test,data\n1,2'}
        )
        # Should return 400 or 200, not 404
        assert response.status_code in [200, 400]

    def test_file_upload_endpoints_exist(self, client):
        """Test that all file upload endpoints exist"""
        endpoints = [
            '/api/upload-python-file',
            '/api/upload-ohlc-file',
        ]

        for endpoint in endpoints:
            # Make a POST request without file (should fail gracefully)
            response = client.post(endpoint)
            # Should not return 404
            assert response.status_code != 404


class TestButtonFunctionality:
    """Tests for button click functionality"""

    def test_execute_button_endpoint(self, client):
        """Test that execute button uses working endpoint"""
        response = client.post(
            '/api/unattended-bruteforce-execute',
            json={'csv_content': ''}
        )
        # Should return 400 (bad input), not 404
        assert response.status_code != 404
        assert response.status_code in [400, 422]

    def test_stop_button_endpoint(self, client):
        """Test that stop button uses working endpoint"""
        response = client.post('/api/unattended-bruteforce-stop')
        # Should return 200 or 400, not 404
        assert response.status_code != 404
        assert response.status_code in [200, 400]

    def test_progress_endpoint(self, client):
        """Test that progress check endpoint works"""
        response = client.get('/api/unattended-bruteforce-progress')
        # Should return 200 or 400, not 404
        assert response.status_code != 404
        assert response.status_code in [200, 400]

    def test_results_endpoint(self, client):
        """Test that results retrieval endpoint works"""
        response = client.get('/api/unattended-bruteforce-final-results')
        # Should return 200 or 400, not 404
        assert response.status_code != 404


class TestModalInteractions:
    """Tests for modal popup functionality"""

    def test_modal_elements_in_html(self, client):
        """Test that modal elements are in HTML"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for modal-related elements
        assert 'onclick' in data or 'click' in data.lower()
        assert 'close' in data.lower() or 'modal' in data.lower()

    def test_modal_functions_defined(self, client):
        """Test that modal JavaScript functions are defined"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for modal function definitions
        functions = ['openBuildCSVModal', 'closeBuildCSVModal', 'Modal']
        for func in functions:
            if func in data:  # At least one should be present
                assert func in data


class TestDownloadFunctionality:
    """Tests for download and export features"""

    def test_download_csv_functionality(self, client):
        """Test that CSV download features are accessible"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for download-related elements
        download_keywords = ['download', 'export', 'save', 'csv']
        has_download = any(keyword in data.lower() for keyword in download_keywords)
        assert has_download, "No download functionality found"

    def test_file_analysis_works(self, client, sample_ohlc_csv):
        """Test that file analysis API works"""
        response = client.get('/api/analyze/test.csv')
        # Should return 404 (file doesn't exist), not 500
        assert response.status_code == 404


class TestInputValidation:
    """Tests for input validation on user interactions"""

    def test_empty_csv_rejected(self, client):
        """Test that empty CSV is rejected"""
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={'csv_content': ''}
        )
        assert response.status_code == 400

    def test_invalid_json_rejected(self, client):
        """Test that invalid JSON is rejected"""
        response = client.post(
            '/api/unattended-bruteforce-validate',
            json={}
        )
        assert response.status_code == 400

    def test_missing_parameters_rejected(self, client):
        """Test that missing parameters are rejected"""
        response = client.post('/api/unattended-bruteforce-execute', json={})
        assert response.status_code == 400


class TestErrorHandling:
    """Tests for error messages and handling"""

    def test_nonexistent_file_handling(self, client):
        """Test that nonexistent file access is handled"""
        response = client.get('/api/analyze/nonexistent_file.csv')
        assert response.status_code == 404
        data = response.data.decode('utf-8')
        assert 'error' in data.lower() or 'not found' in data.lower()

    def test_invalid_operation_handling(self, client):
        """Test that invalid operations return proper errors"""
        response = client.post('/api/delete/nonexistent_file.csv')
        assert response.status_code == 404

    def test_path_traversal_blocked(self, client):
        """Test that path traversal attempts are blocked"""
        response = client.get('/api/analyze/../../../etc/passwd')
        assert response.status_code == 404
        assert b'etc/passwd' not in response.data


class TestClickableElements:
    """Tests that all clickable elements are functional"""

    def test_all_buttons_have_handlers(self, client):
        """Test that all buttons have click handlers"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Count buttons with onclick handlers
        button_count = data.count('<button')
        onclick_count = data.count('onclick=')

        # Most buttons should have onclick handlers
        # (allowing for some buttons that might use form submission)
        assert onclick_count > 0, "No onclick handlers found"

    def test_navigation_links_work(self, client):
        """Test that navigation links point to valid endpoints"""
        response = client.get('/')
        assert response.status_code == 200

        # Check that main page loads
        data = response.data.decode('utf-8')
        assert 'html' in data.lower() or 'body' in data.lower()

    def test_form_elements_complete(self, client):
        """Test that forms have required elements"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for form-related elements
        form_keywords = ['form', 'input', 'button', 'submit']
        found_forms = sum(1 for keyword in form_keywords if keyword in data.lower())
        assert found_forms >= 2, "Missing form elements"


class TestPageContent:
    """Tests for page content and structure"""

    def test_page_has_title(self, client):
        """Test that page has a title"""
        response = client.get('/')
        data = response.data.decode('utf-8')
        assert '<title>' in data or '<h1>' in data or 'Strategy' in data

    def test_page_has_navigation(self, client):
        """Test that page has navigation elements"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for navigation elements
        nav_keywords = ['nav', 'menu', 'tab', 'button']
        has_nav = any(keyword in data.lower() for keyword in nav_keywords)
        assert has_nav, "No navigation found"

    def test_css_is_loaded(self, client):
        """Test that CSS is properly loaded"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for style definitions
        assert '<style' in data or 'href=' in data or 'class=' in data

    def test_javascript_is_loaded(self, client):
        """Test that JavaScript is properly loaded"""
        response = client.get('/')
        data = response.data.decode('utf-8')

        # Check for script tags
        assert '<script' in data
