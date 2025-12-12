"""Capture data models"""

from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional
from datetime import datetime, timezone


class RequestData(BaseModel):
    """HTTP request data"""
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "headers": {"Authorization": "Bearer token", "Content-Type": "application/json"},
                "body": {"username": "user123"}
            }
        }


class ResponseData(BaseModel):
    """HTTP response data"""
    status: int = Field(..., ge=0, le=599, description="HTTP status code (0 for network errors, 100-599 for valid responses)")
    headers: Dict[str, str] = Field(default_factory=dict)
    body: Optional[Any] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "headers": {"Content-Type": "application/json"},
                "body": {"id": 123, "name": "John"}
            }
        }


class Capture(BaseModel):
    """Single API capture (request-response pair)"""
    url: str = Field(..., description="Full URL of the API call")
    method: str = Field(..., description="HTTP method (GET, POST, etc.)")
    request: RequestData
    response: ResponseData
    timestamp: Optional[datetime] = Field(None, description="When the capture occurred (optional, defaults to now)")
    duration_ms: int = Field(default=0, ge=0, description="Request duration in milliseconds (defaults to 0)")
    
    @field_validator('timestamp', mode='before')
    @classmethod
    def validate_timestamp(cls, v: Optional[datetime]) -> datetime:
        if v is None:
            return datetime.now(timezone.utc)
        return v
    
    @field_validator('method')
    @classmethod
    def validate_method(cls, v: str) -> str:
        allowed_methods = {'GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'}
        v_upper = v.upper()
        if v_upper not in allowed_methods:
            raise ValueError(f'Method must be one of {allowed_methods}')
        return v_upper
    
    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://api.example.com/v1/users/123",
                "method": "GET",
                "request": {
                    "headers": {"Authorization": "Bearer token"},
                    "body": None
                },
                "response": {
                    "status": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": {"id": 123, "name": "John"}
                },
                "timestamp": "2025-11-05T10:30:01Z",
                "duration_ms": 145
            }
        }


class CapturesBatchRequest(BaseModel):
    """Batch of captures to add to a session"""
    captures: list[Capture] = Field(..., min_length=1, max_length=50)
    
    class Config:
        json_schema_extra = {
            "example": {
                "captures": [
                    {
                        "url": "https://api.example.com/v1/users/123",
                        "method": "GET",
                        "request": {"headers": {}, "body": None},
                        "response": {"status": 200, "headers": {}, "body": {}},
                        "timestamp": "2025-11-05T10:30:01Z",
                        "duration_ms": 145
                    }
                ]
            }
        }

