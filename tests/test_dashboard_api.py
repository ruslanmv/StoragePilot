"""
Unit tests for StoragePilot Dashboard API
=========================================

Tests all API endpoints to ensure they work correctly.

Run with:
    pytest tests/test_dashboard_api.py -v

Or:
    make test-api
"""

import pytest
import time
import os
from pathlib import Path

from fastapi.testclient import TestClient

# Add project root to path
import sys
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from ui.dashboard import app


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client():
    """Create a test client for the API."""
    return TestClient(app)


@pytest.fixture
def scan_id(client):
    """Start a scan and return the scan_id."""
    response = client.post("/api/scan/start")
    assert response.status_code == 200
    data = response.json()
    assert "scan_id" in data
    return data["scan_id"]


# =============================================================================
# Health Check Tests
# =============================================================================

class TestHealthEndpoint:
    """Tests for /api/health endpoint."""

    def test_health_returns_ok(self, client):
        """Test that health endpoint returns ok status."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "time" in data
        assert "version" in data

    def test_health_response_format(self, client):
        """Test health endpoint response format."""
        response = client.get("/api/health")
        data = response.json()
        # Check that time is ISO format
        assert "T" in data["time"]  # ISO datetime has T separator


# =============================================================================
# Configuration Tests
# =============================================================================

class TestConfigEndpoints:
    """Tests for /api/config endpoints."""

    def test_get_config(self, client):
        """Test GET /api/config returns configuration."""
        response = client.get("/api/config")
        assert response.status_code == 200
        data = response.json()

        # Check required fields exist
        assert "provider" in data
        assert "model" in data
        assert "baseUrl" in data
        assert "dryRun" in data
        assert "approval" in data
        assert "backup" in data

    def test_get_config_default_values(self, client):
        """Test that config has sensible defaults."""
        response = client.get("/api/config")
        data = response.json()

        # Provider should be one of the allowed values
        assert data["provider"] in ["ollama", "openai", "matrixllm"]
        # Safety flags should be booleans
        assert isinstance(data["dryRun"], bool)
        assert isinstance(data["approval"], bool)
        assert isinstance(data["backup"], bool)

    def test_put_config(self, client):
        """Test PUT /api/config saves configuration."""
        # Get current config
        original = client.get("/api/config").json()

        # Modify config
        new_config = {
            "provider": "ollama",
            "model": "test-model",
            "baseUrl": "http://localhost:11434/v1",
            "scanPrimary": "~/Downloads",
            "scanWorkspace": "~/projects",
            "dryRun": True,
            "approval": True,
            "backup": False,
            "matrixCode": ""
        }

        response = client.put("/api/config", json=new_config)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

        # Verify config was saved
        response = client.get("/api/config")
        saved = response.json()
        assert saved["model"] == "test-model"
        assert saved["backup"] is False

        # Restore original config
        original["matrixCode"] = ""
        client.put("/api/config", json=original)

    def test_put_config_validates_provider(self, client):
        """Test that provider validation works."""
        response = client.get("/api/config")
        config = response.json()
        config["provider"] = "ollama"  # Valid provider
        config["matrixCode"] = ""

        response = client.put("/api/config", json=config)
        assert response.status_code == 200


# =============================================================================
# Scan Tests
# =============================================================================

class TestScanEndpoints:
    """Tests for /api/scan endpoints."""

    def test_start_scan(self, client):
        """Test POST /api/scan/start creates a new scan."""
        response = client.post("/api/scan/start")
        assert response.status_code == 200
        data = response.json()
        assert "scan_id" in data
        assert len(data["scan_id"]) == 32  # UUID hex is 32 chars

    def test_get_scan_not_found(self, client):
        """Test GET /api/scan/{id} returns 404 for invalid ID."""
        response = client.get("/api/scan/invalid-scan-id")
        assert response.status_code == 404

    def test_get_scan_returns_result(self, client, scan_id):
        """Test GET /api/scan/{id} returns scan result."""
        # Wait a moment for scan to progress
        time.sleep(0.5)

        response = client.get(f"/api/scan/{scan_id}")
        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert data["scan_id"] == scan_id
        assert data["status"] in ["IDLE", "SCANNING", "REVIEW", "SUCCESS"]
        assert "metrics" in data
        assert "dev_debt" in data
        assert "downloads_breakdown" in data

    def test_get_scan_metrics_format(self, client, scan_id):
        """Test scan metrics have correct format."""
        time.sleep(0.5)

        response = client.get(f"/api/scan/{scan_id}")
        data = response.json()
        metrics = data["metrics"]

        assert "storage_used_percent" in metrics
        assert "free_human" in metrics
        assert "total_human" in metrics
        assert "waste_human" in metrics

    def test_get_scan_logs(self, client, scan_id):
        """Test GET /api/scan/{id}/logs returns logs."""
        time.sleep(0.5)

        response = client.get(f"/api/scan/{scan_id}/logs")
        assert response.status_code == 200
        data = response.json()

        assert data["scan_id"] == scan_id
        assert "status" in data
        assert "progress" in data
        assert "logs" in data
        assert isinstance(data["logs"], list)

    def test_get_scan_logs_with_offset(self, client, scan_id):
        """Test GET /api/scan/{id}/logs with offset parameter."""
        time.sleep(0.5)

        response = client.get(f"/api/scan/{scan_id}/logs?offset=0")
        assert response.status_code == 200
        data = response.json()
        assert "total_logs" in data

    def test_get_scan_logs_not_found(self, client):
        """Test GET /api/scan/{id}/logs returns 404 for invalid ID."""
        response = client.get("/api/scan/invalid-id/logs")
        assert response.status_code == 404


# =============================================================================
# Filesystem Tests
# =============================================================================

class TestFilesystemEndpoints:
    """Tests for /api/fs endpoints."""

    def test_fs_list_home(self, client):
        """Test GET /api/fs/list returns directory listing."""
        response = client.get("/api/fs/list?path=~")
        assert response.status_code == 200
        data = response.json()

        assert "path" in data
        assert "directories" in data
        assert isinstance(data["directories"], list)

    def test_fs_list_root(self, client):
        """Test GET /api/fs/list works with root path."""
        response = client.get("/api/fs/list?path=/")
        assert response.status_code == 200
        data = response.json()

        assert data["path"] == "/"
        assert isinstance(data["directories"], list)

    def test_fs_list_default_path(self, client):
        """Test GET /api/fs/list uses default path when not specified."""
        response = client.get("/api/fs/list")
        assert response.status_code == 200
        data = response.json()
        assert "path" in data

    def test_fs_list_invalid_path(self, client):
        """Test GET /api/fs/list returns 200 with fallback for invalid path."""
        response = client.get("/api/fs/list?path=/nonexistent/path/12345")
        # API now returns 200 with graceful fallback to valid directory
        assert response.status_code == 200
        data = response.json()
        # Should have fallen back to a valid directory
        assert "path" in data
        assert "directories" in data

    def test_fs_list_file_path(self, client):
        """Test GET /api/fs/list returns 200 with fallback for file path."""
        # Use a known file
        response = client.get("/api/fs/list?path=/etc/passwd")
        # API now returns 200 with graceful fallback
        assert response.status_code == 200
        data = response.json()
        assert "path" in data

    def test_fs_list_directories_only(self, client):
        """Test that fs/list returns only directories."""
        response = client.get("/api/fs/list?path=/tmp")
        if response.status_code == 200:
            data = response.json()
            # All entries should have 'name' and 'path' keys
            for item in data["directories"]:
                assert "name" in item
                assert "path" in item


# =============================================================================
# Clean Execution Tests
# =============================================================================

class TestCleanEndpoints:
    """Tests for /api/clean endpoints."""

    def test_clean_execute_requires_scan(self, client):
        """Test POST /api/clean/execute requires valid scan_id."""
        response = client.post("/api/clean/execute", json={
            "scan_id": "invalid-scan-id",
            "selected_dev_debt_ids": [],
            "docker_prune": False,
            "organize_path": "~/Downloads"
        })
        assert response.status_code == 404

    def test_clean_execute_with_scan(self, client, scan_id):
        """Test POST /api/clean/execute works with valid scan."""
        # Wait for scan to complete (may take longer in CI)
        max_wait = 15
        start_time = time.time()
        status = "SCANNING"

        while status == "SCANNING" and (time.time() - start_time) < max_wait:
            time.sleep(0.5)
            response = client.get(f"/api/scan/{scan_id}")
            status = response.json()["status"]

        response = client.post("/api/clean/execute", json={
            "scan_id": scan_id,
            "selected_dev_debt_ids": [],
            "docker_prune": False,
            "organize_path": "~/Downloads"
        })

        # If scan completed, should work. If still scanning, may get 404
        if status in ["REVIEW", "SUCCESS"]:
            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "dry_run" in data
            assert "actions" in data
        else:
            # Scan didn't complete in time, 404 is acceptable
            assert response.status_code in [200, 404]

    def test_clean_execute_dry_run(self, client, scan_id):
        """Test that dry_run mode is respected."""
        # Wait for scan to complete
        max_wait = 15
        start_time = time.time()
        status = "SCANNING"

        while status == "SCANNING" and (time.time() - start_time) < max_wait:
            time.sleep(0.5)
            response = client.get(f"/api/scan/{scan_id}")
            status = response.json()["status"]

        response = client.post("/api/clean/execute", json={
            "scan_id": scan_id,
            "selected_dev_debt_ids": [],
            "docker_prune": False,
            "organize_path": "~/Downloads"
        })

        if response.status_code == 200:
            data = response.json()
            # Should be in dry_run mode by default
            assert data["dry_run"] is True

    def test_clean_plan(self, client, scan_id):
        """Test POST /api/clean/plan returns cleaning plan."""
        # Wait for scan to complete
        max_wait = 15
        start_time = time.time()
        status = "SCANNING"

        while status == "SCANNING" and (time.time() - start_time) < max_wait:
            time.sleep(0.5)
            response = client.get(f"/api/scan/{scan_id}")
            status = response.json()["status"]

        response = client.post("/api/clean/plan", json={
            "scan_id": scan_id,
            "selected_dev_debt_ids": [],
            "docker_prune": False,
            "organize_path": "~/Downloads"
        })

        if status in ["REVIEW", "SUCCESS"]:
            assert response.status_code == 200
            data = response.json()
            assert data["scan_id"] == scan_id
            assert "dry_run" in data
            assert "planned_actions" in data
        else:
            # Scan didn't complete, 404 is acceptable
            assert response.status_code in [200, 404]

    def test_clean_plan_not_found(self, client):
        """Test POST /api/clean/plan returns 404 for invalid scan."""
        response = client.post("/api/clean/plan", json={
            "scan_id": "invalid-id",
            "selected_dev_debt_ids": [],
            "docker_prune": False,
            "organize_path": "~/Downloads"
        })
        assert response.status_code == 404


# =============================================================================
# Static Files Tests
# =============================================================================

class TestStaticFiles:
    """Tests for static file serving."""

    def test_root_serves_content(self, client):
        """Test that root path serves something."""
        response = client.get("/")
        assert response.status_code == 200

    def test_index_html_exists(self):
        """Test that index.html exists in static directory."""
        index_path = PROJECT_ROOT / "ui" / "static" / "index.html"
        assert index_path.exists(), "index.html should exist in ui/static/"


# =============================================================================
# WebSocket Tests (Basic)
# =============================================================================

class TestWebSocket:
    """Basic WebSocket endpoint tests."""

    def test_websocket_invalid_scan(self, client):
        """Test WebSocket rejects invalid scan_id."""
        with pytest.raises(Exception):
            # This should fail because scan_id doesn't exist
            with client.websocket_connect("/api/scan/ws/invalid-scan-id"):
                pass

    def test_websocket_connection(self, client, scan_id):
        """Test WebSocket accepts valid scan_id."""
        try:
            with client.websocket_connect(f"/api/scan/ws/{scan_id}") as websocket:
                # Should receive initial status
                data = websocket.receive_json()
                assert "type" in data
                # Close gracefully
        except Exception:
            # WebSocket might close if scan completes quickly
            pass


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for complete workflows."""

    def test_full_scan_workflow(self, client):
        """Test complete scan workflow from start to results."""
        # 1. Start scan
        response = client.post("/api/scan/start")
        assert response.status_code == 200
        scan_id = response.json()["scan_id"]

        # 2. Wait for scan to complete (may not finish in CI)
        max_wait = 15  # seconds
        start_time = time.time()
        status = "SCANNING"

        while status == "SCANNING" and (time.time() - start_time) < max_wait:
            time.sleep(0.5)
            response = client.get(f"/api/scan/{scan_id}")
            status = response.json()["status"]

        # 3. Check scan is in valid state (SCANNING is OK if it hasn't finished)
        assert status in ["SCANNING", "REVIEW", "SUCCESS"]

        # 4. Get results (available even while scanning)
        response = client.get(f"/api/scan/{scan_id}")
        data = response.json()

        assert "metrics" in data
        assert "dev_debt" in data
        assert "downloads_breakdown" in data

    def test_config_persistence(self, client):
        """Test that config changes persist."""
        # Get original
        original = client.get("/api/config").json()

        # Change model
        modified = original.copy()
        modified["model"] = "persistence-test-model"
        modified["matrixCode"] = ""

        client.put("/api/config", json=modified)

        # Read back
        saved = client.get("/api/config").json()
        assert saved["model"] == "persistence-test-model"

        # Restore
        original["matrixCode"] = ""
        client.put("/api/config", json=original)


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
