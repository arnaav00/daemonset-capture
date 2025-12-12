"""Analysis result models"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime


class EndpointInfo(BaseModel):
    """Information about a specific endpoint"""
    path: str = Field(..., description="Parameterized path pattern")
    methods: List[str] = Field(..., description="HTTP methods used")
    sample_count: int = Field(..., ge=1, description="Number of samples in this endpoint")
    
    class Config:
        json_schema_extra = {
            "example": {
                "path": "/v1/users/{id}",
                "methods": ["GET", "PUT", "DELETE"],
                "sample_count": 42
            }
        }


class MicroserviceSignature(BaseModel):
    """Signature characteristics of a microservice"""
    primary_response_schema: Optional[Dict[str, Any]] = None
    common_headers: Dict[str, str] = Field(default_factory=dict)
    auth_pattern: Optional[str] = None
    server_signature: Optional[str] = None
    error_format: Optional[Dict[str, Any]] = None


class IdentifiedMicroservice(BaseModel):
    """A single identified microservice"""
    microservice_id: str
    identified_name: str = Field(..., description="Generated name for the microservice")
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    base_url: str = Field(..., description="Base URL pattern")
    signature: MicroserviceSignature
    endpoints: List[EndpointInfo]
    # openapi_spec_url removed - use /onboard endpoint to send spec to external API
    
    class Config:
        json_schema_extra = {
            "example": {
                "microservice_id": "ms-uuid-1",
                "identified_name": "user-service",
                "confidence_score": 0.92,
                "base_url": "https://api.example.com/v1/users",
                "signature": {
                    "auth_pattern": "Bearer JWT",
                    "server_signature": "nginx/Express"
                },
                "endpoints": [
                    {
                        "path": "/v1/users/{id}",
                        "methods": ["GET", "PUT"],
                        "sample_count": 42
                    }
                ]
            }
        }


class AnalysisResult(BaseModel):
    """Complete analysis result"""
    session_id: str
    analysis_timestamp: datetime
    total_captures_analyzed: int
    microservices_identified: int
    microservices: List[IdentifiedMicroservice]
    raw_data_url: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "uuid-here",
                "analysis_timestamp": "2025-11-05T10:35:00Z",
                "total_captures_analyzed": 450,
                "microservices_identified": 3,
                "microservices": [],
                "raw_data_url": "s3://bucket/session-id/raw.json"
            }
        }

