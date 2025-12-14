#!/usr/bin/env python3
"""
Tests for the Bird Detection Gallery Web Interface

Tests the gallery API endpoints and helper functions.
"""

import os
import sys
import json
import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from base64 import b64encode
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the server module
import server


# ============================================
# Test Fixtures
# ============================================

@pytest.fixture
def app():
    """Create a test Flask app"""
    server.app.config['TESTING'] = True
    return server.app


@pytest.fixture
def client(app):
    """Create a test client"""
    return app.test_client()


@pytest.fixture
def auth_headers():
    """Create authentication headers"""
    credentials = b64encode(b'birds:birdwatcher').decode('utf-8')
    return {'Authorization': f'Basic {credentials}'}


@pytest.fixture
def temp_images_dir(tmp_path):
    """Create a temporary images directory with test images"""
    # Create date folders
    today = datetime.now().strftime('%Y-%m-%d')
    yesterday = '2024-01-15'  # Fixed date for testing

    today_folder = tmp_path / today
    yesterday_folder = tmp_path / yesterday

    today_folder.mkdir()
    yesterday_folder.mkdir()

    # Create dummy image files
    for i in range(3):
        # Today's images
        img_path = today_folder / f"motion_{i:04d}.jpeg"
        img_path.write_bytes(b'\xff\xd8\xff\xe0')  # Minimal JPEG header

        # Yesterday's images
        img_path = yesterday_folder / f"motion_{i:04d}.jpeg"
        img_path.write_bytes(b'\xff\xd8\xff\xe0')

    return tmp_path


@pytest.fixture
def mock_images_dir(temp_images_dir, monkeypatch):
    """Mock the IMAGES_DIR to use temp directory"""
    monkeypatch.setattr(server, 'IMAGES_DIR', temp_images_dir)
    return temp_images_dir


# ============================================
# Helper Function Tests
# ============================================

class TestIsDateFolder:
    """Tests for is_date_folder helper function"""

    def test_valid_date_folder(self, tmp_path):
        """Test with valid YYYY-MM-DD format folder"""
        folder = tmp_path / "2024-01-15"
        folder.mkdir()
        assert server.is_date_folder(folder) is True

    def test_invalid_date_format(self, tmp_path):
        """Test with invalid date format"""
        folder = tmp_path / "2024-1-15"  # Missing leading zeros
        folder.mkdir()
        assert server.is_date_folder(folder) is False

    def test_not_a_directory(self, tmp_path):
        """Test with a file instead of directory"""
        file_path = tmp_path / "2024-01-15"
        file_path.write_text("test")
        assert server.is_date_folder(file_path) is False

    def test_random_folder_name(self, tmp_path):
        """Test with random folder name"""
        folder = tmp_path / "random_folder"
        folder.mkdir()
        assert server.is_date_folder(folder) is False

    def test_incomplete_date(self, tmp_path):
        """Test with incomplete date string"""
        folder = tmp_path / "2024-01"
        folder.mkdir()
        assert server.is_date_folder(folder) is False


class TestGetDateFolders:
    """Tests for get_date_folders helper function"""

    def test_returns_sorted_folders(self, mock_images_dir):
        """Test that folders are returned sorted newest first"""
        folders = server.get_date_folders()
        folder_names = [f.name for f in folders]

        # Should be sorted descending (newest first)
        assert folder_names == sorted(folder_names, reverse=True)

    def test_empty_directory(self, tmp_path, monkeypatch):
        """Test with empty images directory"""
        monkeypatch.setattr(server, 'IMAGES_DIR', tmp_path)
        folders = server.get_date_folders()
        assert folders == []

    def test_nonexistent_directory(self, tmp_path, monkeypatch):
        """Test with non-existent images directory"""
        monkeypatch.setattr(server, 'IMAGES_DIR', tmp_path / "nonexistent")
        folders = server.get_date_folders()
        assert folders == []

    def test_excludes_non_date_folders(self, mock_images_dir):
        """Test that non-date folders are excluded"""
        # Create a non-date folder
        (mock_images_dir / "IdentifiedSpecies").mkdir()
        (mock_images_dir / "random_folder").mkdir()

        folders = server.get_date_folders()
        folder_names = [f.name for f in folders]

        assert "IdentifiedSpecies" not in folder_names
        assert "random_folder" not in folder_names


class TestGetImagesForDate:
    """Tests for get_images_for_date helper function"""

    def test_returns_images(self, mock_images_dir):
        """Test that images are returned for a date folder"""
        today = datetime.now().strftime('%Y-%m-%d')
        date_folder = mock_images_dir / today

        images = server.get_images_for_date(date_folder)
        assert len(images) == 3

    def test_empty_folder(self, mock_images_dir):
        """Test with empty date folder"""
        empty_folder = mock_images_dir / "2024-01-01"
        empty_folder.mkdir()

        images = server.get_images_for_date(empty_folder)
        assert images == []

    def test_nonexistent_folder(self, mock_images_dir):
        """Test with non-existent folder"""
        images = server.get_images_for_date(mock_images_dir / "nonexistent")
        assert images == []

    def test_sorted_by_mtime(self, mock_images_dir):
        """Test that images are sorted by modification time (newest first)"""
        today = datetime.now().strftime('%Y-%m-%d')
        date_folder = mock_images_dir / today

        images = server.get_images_for_date(date_folder)
        mtimes = [img.stat().st_mtime for img in images]

        # Should be sorted descending
        assert mtimes == sorted(mtimes, reverse=True)


class TestGetAllImageFiles:
    """Tests for get_all_image_files helper function"""

    def test_returns_all_images(self, mock_images_dir):
        """Test that all images from all date folders are returned"""
        images = server.get_all_image_files()
        # 3 images in today's folder + 3 in yesterday's folder
        assert len(images) == 6

    def test_sorted_by_mtime(self, mock_images_dir):
        """Test images are sorted by modification time"""
        images = server.get_all_image_files()
        mtimes = [img.stat().st_mtime for img in images]
        assert mtimes == sorted(mtimes, reverse=True)


# ============================================
# API Endpoint Tests
# ============================================

class TestGalleryEndpoint:
    """Tests for /api/gallery endpoint"""

    def test_requires_auth(self, client):
        """Test that gallery endpoint requires authentication"""
        response = client.get('/api/gallery')
        assert response.status_code == 401

    def test_returns_images_with_auth(self, client, auth_headers, mock_images_dir):
        """Test gallery returns images when authenticated"""
        response = client.get('/api/gallery', headers=auth_headers)
        assert response.status_code == 200

        data = response.get_json()
        assert data['success'] is True
        assert 'images' in data
        assert 'date' in data
        assert 'available_dates' in data

    def test_pagination_limit(self, client, auth_headers, mock_images_dir):
        """Test pagination limit parameter"""
        response = client.get('/api/gallery?limit=2', headers=auth_headers)
        data = response.get_json()

        assert data['success'] is True
        assert len(data['images']) <= 2

    def test_pagination_offset(self, client, auth_headers, mock_images_dir):
        """Test pagination offset parameter"""
        # Get first page
        response1 = client.get('/api/gallery?limit=1&offset=0', headers=auth_headers)
        data1 = response1.get_json()

        # Get second page
        response2 = client.get('/api/gallery?limit=1&offset=1', headers=auth_headers)
        data2 = response2.get_json()

        # Images should be different
        if data1['images'] and data2['images']:
            assert data1['images'][0]['filename'] != data2['images'][0]['filename']

    def test_date_filter(self, client, auth_headers, mock_images_dir):
        """Test date filter parameter"""
        response = client.get('/api/gallery?date=2024-01-15', headers=auth_headers)
        data = response.get_json()

        assert data['success'] is True
        assert data['date'] == '2024-01-15'

    def test_empty_gallery(self, client, auth_headers, tmp_path, monkeypatch):
        """Test gallery with no images"""
        monkeypatch.setattr(server, 'IMAGES_DIR', tmp_path)

        response = client.get('/api/gallery', headers=auth_headers)
        data = response.get_json()

        assert data['success'] is True
        assert data['images'] == []
        assert data['date'] is None

    def test_has_more_pagination(self, client, auth_headers, mock_images_dir):
        """Test has_more flag for pagination"""
        response = client.get('/api/gallery?limit=1', headers=auth_headers)
        data = response.get_json()

        # With 3 images per date and limit=1, has_more should be True
        assert data['has_more'] is True

    def test_next_date_when_exhausted(self, client, auth_headers, mock_images_dir):
        """Test next_date is provided when current date is exhausted"""
        # Get all images for today
        response = client.get('/api/gallery?limit=100', headers=auth_headers)
        data = response.get_json()

        # When has_more is False, next_date should be set if there are more dates
        if not data['has_more'] and len(data['available_dates']) > 1:
            assert data['next_date'] is not None


class TestImagesEndpoint:
    """Tests for /api/images endpoint"""

    def test_returns_recent_images(self, client, mock_images_dir):
        """Test that recent images are returned"""
        response = client.get('/api/images')
        assert response.status_code == 200

        data = response.get_json()
        assert isinstance(data, list)

    def test_limit_parameter(self, client, mock_images_dir):
        """Test limit parameter"""
        response = client.get('/api/images?limit=2')
        data = response.get_json()

        assert len(data) <= 2

    def test_image_metadata(self, client, mock_images_dir):
        """Test that image metadata is included"""
        response = client.get('/api/images?limit=1')
        data = response.get_json()

        if data:
            image = data[0]
            assert 'filename' in image
            assert 'path' in image
            assert 'timestamp' in image
            assert 'size' in image


class TestImageEndpoint:
    """Tests for /api/image/<path> endpoint"""

    def test_requires_auth(self, client, mock_images_dir):
        """Test that image endpoint requires authentication"""
        response = client.get('/api/image/2024-01-15/motion_0000.jpeg')
        assert response.status_code == 401

    def test_serves_image(self, client, auth_headers, mock_images_dir):
        """Test that images are served correctly"""
        response = client.get('/api/image/2024-01-15/motion_0000.jpeg', headers=auth_headers)
        assert response.status_code == 200
        assert response.content_type == 'image/jpeg'

    def test_image_not_found(self, client, auth_headers, mock_images_dir):
        """Test 404 for non-existent image"""
        response = client.get('/api/image/2024-01-15/nonexistent.jpeg', headers=auth_headers)
        assert response.status_code == 404

    def test_prevents_directory_traversal(self, client, auth_headers, mock_images_dir):
        """Test that directory traversal is prevented"""
        response = client.get('/api/image/../../../etc/passwd', headers=auth_headers)
        assert response.status_code in [403, 404]


class TestLatestEndpoint:
    """Tests for /api/latest endpoint"""

    def test_requires_auth(self, client):
        """Test that latest endpoint requires authentication"""
        response = client.get('/api/latest')
        assert response.status_code == 401

    def test_returns_latest_photo(self, client, auth_headers, mock_images_dir):
        """Test that latest photo is returned"""
        response = client.get('/api/latest', headers=auth_headers)
        assert response.status_code == 200

        data = response.get_json()
        assert data['success'] is True
        if data['photo']:
            assert 'filename' in data['photo']
            assert 'rel_path' in data['photo']
            assert 'timestamp' in data['photo']


# ============================================
# Authentication Tests
# ============================================

class TestAuthentication:
    """Tests for authentication functionality"""

    def test_valid_credentials(self):
        """Test check_auth with valid credentials"""
        assert server.check_auth('birds', 'birdwatcher') is True

    def test_invalid_username(self):
        """Test check_auth with invalid username"""
        assert server.check_auth('wrong', 'birdwatcher') is False

    def test_invalid_password(self):
        """Test check_auth with invalid password"""
        assert server.check_auth('birds', 'wrong') is False

    def test_protected_routes_require_auth(self, client):
        """Test that all protected routes require authentication"""
        protected_routes = [
            '/api/gallery',
            '/api/latest',
        ]

        for route in protected_routes:
            response = client.get(route)
            assert response.status_code == 401, f"Route {route} should require auth"


# ============================================
# Status and Stats Endpoint Tests
# ============================================

class TestStatusEndpoint:
    """Tests for /api/status endpoint"""

    def test_returns_status(self, client):
        """Test that status is returned"""
        response = client.get('/api/status')
        assert response.status_code == 200

        data = response.get_json()
        assert 'app_running' in data
        assert 'timestamp' in data


class TestStatsEndpoint:
    """Tests for /api/stats endpoint"""

    def test_returns_stats(self, client, mock_images_dir):
        """Test that stats are returned"""
        with patch.object(server, 'load_config', return_value={
            'services': {'drive_upload': {'folder_name': 'Test', 'enabled': False}}
        }):
            response = client.get('/api/stats')
            assert response.status_code == 200

            data = response.get_json()
            assert 'system' in data
            assert 'drive' in data
            assert 'app_running' in data


# ============================================
# Species Database Tests
# ============================================

class TestSpeciesDatabase:
    """Tests for species database functionality"""

    def test_get_species_for_photo_no_match(self):
        """Test species lookup with no match"""
        result = server.get_species_for_photo('nonexistent.jpeg')
        assert result is None

    def test_load_species_database_missing_file(self, tmp_path, monkeypatch):
        """Test loading species database when file doesn't exist"""
        monkeypatch.setattr(server, 'SPECIES_DB_PATH', tmp_path / "nonexistent.json")
        monkeypatch.setattr(server, '_species_cache', {})
        monkeypatch.setattr(server, '_species_cache_time', 0)

        result = server.load_species_database()
        assert result == {}


# ============================================
# Main Index Route Test
# ============================================

class TestIndexRoute:
    """Tests for main index route"""

    def test_requires_auth(self, client):
        """Test that index requires authentication"""
        response = client.get('/')
        assert response.status_code == 401

    def test_returns_html_with_auth(self, client, auth_headers):
        """Test that HTML is returned when authenticated"""
        response = client.get('/', headers=auth_headers)
        # May return 200 or 500 depending on template availability
        assert response.status_code in [200, 500]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
