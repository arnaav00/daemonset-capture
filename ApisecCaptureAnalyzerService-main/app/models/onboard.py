"""Onboarding models for external API integration"""

from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import Enum


class OnboardType(str, Enum):
    """Type of onboarding operation"""
    NEW = "new"
    UPDATE = "update"


class OnboardRequest(BaseModel):
    """Request to onboard a microservice to external API"""
    api_key: str = Field(..., description="API key for external API authentication")
    
    class Config:
        json_schema_extra = {
            "example": {
                "api_key": "your-external-api-key-here"
            }
        }


class OnboardResponse(BaseModel):
    """Response from onboard operation"""
    success: bool
    microservice_id: str
    microservice_name: str
    onboard_type: str
    application_id: Optional[str] = None
    host_urls: Optional[list] = None
    application_url: Optional[str] = None
    instances_created: Optional[bool] = None
    message: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "microservice_id": "ms-uuid-1",
                "microservice_name": "user-service",
                "onboard_type": "new",
                "application_id": "app-123",
                "host_urls": ["https://api.example.com"],
                "application_url": "https://cst.dev.apisecapps.com/application/app-123",
                "instances_created": True,
                "message": "Application created successfully: https://cst.dev.apisecapps.com/application/app-123"
            }
        }


