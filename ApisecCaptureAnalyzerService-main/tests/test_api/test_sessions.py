"""Tests for session endpoints"""

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.storage.session_store import get_session_store

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_sessions():
    """Clear session store before each test"""
    store = get_session_store()
    store._sessions.clear()
    yield
    store._sessions.clear()


class TestStartSession:
    """Tests for POST /api/v1/sessions/start"""
    
    def test_start_session_minimal(self):
        """Test starting session with minimal data"""
        response = client.post("/api/v1/sessions/start", json={})
        
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert data["status"] == "active"
        assert "created_at" in data
        assert "expires_at" in data
    
    def test_start_session_with_domain(self):
        """Test starting session with domain"""
        response = client.post(
            "/api/v1/sessions/start",
            json={"domain": "example.com"}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "active"
    
    def test_start_session_with_metadata(self):
        """Test starting session with metadata"""
        response = client.post(
            "/api/v1/sessions/start",
            json={
                "domain": "example.com",
                "metadata": {
                    "plugin_version": "1.0.0",
                    "user_agent": "Chrome"
                }
            }
        )
        
        assert response.status_code == 201


class TestAddCaptures:
    """Tests for POST /api/v1/sessions/{session_id}/captures"""
    
    def test_add_captures_success(self, sample_captures):
        """Test adding captures to a session"""
        # Start session
        start_response = client.post("/api/v1/sessions/start", json={})
        session_id = start_response.json()["session_id"]
        
        # Add captures
        captures_data = {
            "captures": [
                {
                    "url": sample_captures[0].url,
                    "method": sample_captures[0].method,
                    "request": {
                        "headers": sample_captures[0].request.headers,
                        "body": sample_captures[0].request.body
                    },
                    "response": {
                        "status": sample_captures[0].response.status,
                        "headers": sample_captures[0].response.headers,
                        "body": sample_captures[0].response.body
                    },
                    "timestamp": sample_captures[0].timestamp.isoformat(),
                    "duration_ms": sample_captures[0].duration_ms
                }
            ]
        }
        
        response = client.post(
            f"/api/v1/sessions/{session_id}/captures",
            json=captures_data
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["captures_added"] == 1
        assert data["total_captures_in_session"] == 1
    
    def test_add_captures_multiple_batches(self, sample_captures):
        """Test adding multiple batches of captures"""
        # Start session
        start_response = client.post("/api/v1/sessions/start", json={})
        session_id = start_response.json()["session_id"]
        
        # Add first batch
        batch1 = {"captures": [self._capture_to_dict(sample_captures[0])]}
        response1 = client.post(
            f"/api/v1/sessions/{session_id}/captures",
            json=batch1
        )
        assert response1.json()["total_captures_in_session"] == 1
        
        # Add second batch
        batch2 = {"captures": [self._capture_to_dict(sample_captures[1])]}
        response2 = client.post(
            f"/api/v1/sessions/{session_id}/captures",
            json=batch2
        )
        assert response2.json()["total_captures_in_session"] == 2
    
    def test_add_captures_invalid_session(self, sample_captures):
        """Test adding captures to non-existent session"""
        captures_data = {
            "captures": [self._capture_to_dict(sample_captures[0])]
        }
        
        response = client.post(
            "/api/v1/sessions/invalid-id/captures",
            json=captures_data
        )
        
        assert response.status_code == 404
    
    def test_add_captures_exceeds_batch_limit(self):
        """Test adding more than 50 captures in one batch"""
        # Start session
        start_response = client.post("/api/v1/sessions/start", json={})
        session_id = start_response.json()["session_id"]
        
        # Try to add 51 captures
        captures_data = {
            "captures": [
                {
                    "url": f"https://api.example.com/v1/users/{i}",
                    "method": "GET",
                    "request": {"headers": {}, "body": None},
                    "response": {"status": 200, "headers": {}, "body": {}},
                    "timestamp": "2025-11-05T10:30:00Z",
                    "duration_ms": 100
                }
                for i in range(51)
            ]
        }
        
        response = client.post(
            f"/api/v1/sessions/{session_id}/captures",
            json=captures_data
        )
        
        assert response.status_code == 422  # Validation error
    
    @staticmethod
    def _capture_to_dict(capture):
        """Convert capture object to dict for JSON"""
        return {
            "url": capture.url,
            "method": capture.method,
            "request": {
                "headers": capture.request.headers,
                "body": capture.request.body
            },
            "response": {
                "status": capture.response.status,
                "headers": capture.response.headers,
                "body": capture.response.body
            },
            "timestamp": capture.timestamp.isoformat(),
            "duration_ms": capture.duration_ms
        }


class TestAnalyzeSession:
    """Tests for POST /api/v1/sessions/{session_id}/analyze"""
    
    def test_analyze_session_success(self, sample_captures):
        """Test analyzing a session with captures"""
        # Start session
        start_response = client.post("/api/v1/sessions/start", json={})
        session_id = start_response.json()["session_id"]
        
        # Add captures
        captures_data = {
            "captures": [
                TestAddCaptures._capture_to_dict(c) for c in sample_captures
            ]
        }
        client.post(f"/api/v1/sessions/{session_id}/captures", json=captures_data)
        
        # Analyze
        response = client.post(f"/api/v1/sessions/{session_id}/analyze")
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert data["total_captures_analyzed"] == len(sample_captures)
        assert "microservices_identified" in data
        assert "microservices" in data
        assert isinstance(data["microservices"], list)
    
    def test_analyze_session_no_captures(self):
        """Test analyzing a session with no captures"""
        # Start session
        start_response = client.post("/api/v1/sessions/start", json={})
        session_id = start_response.json()["session_id"]
        
        # Try to analyze without adding captures
        response = client.post(f"/api/v1/sessions/{session_id}/analyze")
        
        assert response.status_code == 400
    
    def test_analyze_session_not_found(self):
        """Test analyzing non-existent session"""
        response = client.post("/api/v1/sessions/invalid-id/analyze")
        
        assert response.status_code == 404


class TestHealthEndpoints:
    """Tests for health and root endpoints"""
    
    def test_root_endpoint(self):
        """Test root endpoint"""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
        assert "status" in data
    
    def test_health_check(self):
        """Test health check endpoint"""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

