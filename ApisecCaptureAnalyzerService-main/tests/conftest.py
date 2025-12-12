"""Pytest configuration and fixtures"""

import pytest
from datetime import datetime
from typing import List
from app.models.capture import Capture, RequestData, ResponseData


@pytest.fixture
def sample_captures() -> List[Capture]:
    """Generate sample captures for testing"""
    return [
        # User service captures
        Capture(
            url="https://api.example.com/v1/users/123",
            method="GET",
            request=RequestData(
                headers={"Authorization": "Bearer token123", "Content-Type": "application/json"},
                body=None
            ),
            response=ResponseData(
                status=200,
                headers={"Content-Type": "application/json", "X-Service-Name": "user-service", "Server": "nginx"},
                body={"id": 123, "name": "John Doe", "email": "john@example.com", "created_at": "2025-01-01"}
            ),
            timestamp=datetime(2025, 11, 5, 10, 30, 0),
            duration_ms=150
        ),
        Capture(
            url="https://api.example.com/v1/users/456",
            method="GET",
            request=RequestData(
                headers={"Authorization": "Bearer token123", "Content-Type": "application/json"},
                body=None
            ),
            response=ResponseData(
                status=200,
                headers={"Content-Type": "application/json", "X-Service-Name": "user-service", "Server": "nginx"},
                body={"id": 456, "name": "Jane Smith", "email": "jane@example.com", "created_at": "2025-01-02"}
            ),
            timestamp=datetime(2025, 11, 5, 10, 30, 5),
            duration_ms=145
        ),
        Capture(
            url="https://api.example.com/v1/users",
            method="POST",
            request=RequestData(
                headers={"Authorization": "Bearer token123", "Content-Type": "application/json"},
                body={"name": "New User", "email": "new@example.com"}
            ),
            response=ResponseData(
                status=201,
                headers={"Content-Type": "application/json", "X-Service-Name": "user-service", "Server": "nginx"},
                body={"id": 789, "name": "New User", "email": "new@example.com", "created_at": "2025-01-03"}
            ),
            timestamp=datetime(2025, 11, 5, 10, 30, 10),
            duration_ms=200
        ),
        # Order service captures
        Capture(
            url="https://api.example.com/v1/orders/ord_abc123",
            method="GET",
            request=RequestData(
                headers={"Authorization": "Bearer token123", "Content-Type": "application/json"},
                body=None
            ),
            response=ResponseData(
                status=200,
                headers={"Content-Type": "application/json", "X-Service-Name": "order-service", "Server": "express"},
                body={"order_id": "ord_abc123", "total": 99.99, "status": "completed", "created_at": "2025-01-01"}
            ),
            timestamp=datetime(2025, 11, 5, 10, 30, 15),
            duration_ms=180
        ),
        Capture(
            url="https://api.example.com/v1/orders/ord_xyz789",
            method="GET",
            request=RequestData(
                headers={"Authorization": "Bearer token123", "Content-Type": "application/json"},
                body=None
            ),
            response=ResponseData(
                status=200,
                headers={"Content-Type": "application/json", "X-Service-Name": "order-service", "Server": "express"},
                body={"order_id": "ord_xyz789", "total": 149.99, "status": "pending", "created_at": "2025-01-02"}
            ),
            timestamp=datetime(2025, 11, 5, 10, 30, 20),
            duration_ms=175
        ),
    ]


@pytest.fixture
def sample_user_capture() -> Capture:
    """Generate a single user service capture"""
    return Capture(
        url="https://api.example.com/v1/users/999",
        method="GET",
        request=RequestData(
            headers={"Authorization": "Bearer token", "Content-Type": "application/json"},
            body=None
        ),
        response=ResponseData(
            status=200,
            headers={"Content-Type": "application/json", "X-Service-Name": "user-service"},
            body={"id": 999, "name": "Test User"}
        ),
        timestamp=datetime(2025, 11, 5, 12, 0, 0),
        duration_ms=100
    )

