"""Tests for file upload endpoints"""
import pytest
import os
import json
from pathlib import Path


class TestPythonFileUpload:
    """Tests for /api/upload-python-file endpoint"""

    def test_upload_python_file_success(self, client, sample_python_file):
        """Test successful Python file upload"""
        with open(sample_python_file, 'rb') as f:
            response = client.post(
                '/api/upload-python-file',
                data={'file': (f, 'test_strategy.py')},
                content_type='multipart/form-data'
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'absolute_path' in data
        assert 'filename' in data
        assert data['filename'] == 'test_strategy.py'

    def test_upload_python_file_no_file(self, client):
        """Test Python file upload without file"""
        response = client.post('/api/upload-python-file')
        assert response.status_code == 400

    def test_upload_python_file_invalid_extension(self, client):
        """Test Python file upload with invalid extension"""
        response = client.post(
            '/api/upload-python-file',
            data={'file': (b'test content', 'test.txt')},
            content_type='multipart/form-data'
        )
        assert response.status_code == 400


class TestOHLCFileUpload:
    """Tests for /api/upload-ohlc-file endpoint"""

    def test_upload_ohlc_file_success(self, client, sample_ohlc_csv):
        """Test successful OHLC file upload"""
        with open(sample_ohlc_csv, 'rb') as f:
            response = client.post(
                '/api/upload-ohlc-file',
                data={'file': (f, 'test_ohlc.csv')},
                content_type='multipart/form-data'
            )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['success'] == True
        assert 'absolute_path' in data

    def test_upload_ohlc_file_no_file(self, client):
        """Test OHLC file upload without file"""
        response = client.post('/api/upload-ohlc-file')
        assert response.status_code == 400

    def test_upload_ohlc_invalid_format(self, client):
        """Test OHLC file with invalid CSV format"""
        invalid_csv = b'invalid,data\nno,ohlc'
        response = client.post(
            '/api/upload-ohlc-file',
            data={'file': (invalid_csv, 'invalid.csv')},
            content_type='multipart/form-data'
        )
        assert response.status_code in [400, 422]


class TestFileAnalyze:
    """Tests for /api/analyze/<filename> endpoint"""

    def test_analyze_missing_file(self, client):
        """Test analyzing non-existent file"""
        response = client.get('/api/analyze/nonexistent_file.csv')
        assert response.status_code == 404

    def test_analyze_file_path_traversal(self, client):
        """Test path traversal attack prevention"""
        response = client.get('/api/analyze/../../../etc/passwd')
        assert response.status_code == 404


class TestFileDelete:
    """Tests for /api/delete/<filename> endpoint"""

    def test_delete_missing_file(self, client):
        """Test deleting non-existent file"""
        response = client.post('/api/delete/nonexistent_file.csv')
        assert response.status_code == 404

    def test_delete_file_path_traversal(self, client):
        """Test path traversal prevention in delete"""
        response = client.post('/api/delete/../../../etc/passwd')
        assert response.status_code == 404
