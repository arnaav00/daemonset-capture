"""Session data models"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from .capture import Capture


class SessionStatus(str, Enum):
    """Session status enumeration"""
    ACTIVE = "active"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    EXPIRED = "expired"


class StartSessionRequest(BaseModel):
    """Request to start a new session"""
    domain: Optional[str] = Field(None, description="Domain being analyzed")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Optional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "domain": "example.com",
                "metadata": {
                    "user_agent": "Chrome/120.0.0.0",
                    "plugin_version": "1.0.0"
                }
            }
        }


class StartSessionResponse(BaseModel):
    """Response from starting a session"""
    session_id: str
    created_at: datetime
    expires_at: datetime
    status: SessionStatus = SessionStatus.ACTIVE


class AddCapturesResponse(BaseModel):
    """Response from adding captures to a session"""
    session_id: str
    captures_added: int
    total_captures_in_session: int
    status: SessionStatus


class SessionData(BaseModel):
    """Internal session data structure"""
    session_id: str
    domain: Optional[str]
    metadata: Dict[str, Any]
    captures: List[Capture]
    created_at: datetime
    expires_at: datetime
    status: SessionStatus
    
    class Config:
        arbitrary_types_allowed = True

