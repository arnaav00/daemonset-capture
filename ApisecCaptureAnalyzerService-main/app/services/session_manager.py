"""Session management service"""

import uuid
from datetime import datetime, timedelta
from typing import List
from ..models.session import SessionData, SessionStatus, StartSessionRequest, StartSessionResponse, AddCapturesResponse
from ..models.capture import Capture
from ..storage.session_store import get_session_store
from ..core.config import settings
from fastapi import HTTPException, status


class SessionManager:
    """Manages session lifecycle"""
    
    def __init__(self):
        self.store = get_session_store()
    
    def start_session(self, request: StartSessionRequest) -> StartSessionResponse:
        """
        Start a new capture session.
        
        Args:
            request: Session start request
        
        Returns:
            Session information
        """
        session_id = str(uuid.uuid4())
        created_at = datetime.utcnow()
        expires_at = created_at + timedelta(seconds=settings.session_ttl_seconds)
        
        session_data = SessionData(
            session_id=session_id,
            domain=request.domain,
            metadata=request.metadata or {},
            captures=[],
            created_at=created_at,
            expires_at=expires_at,
            status=SessionStatus.ACTIVE
        )
        
        self.store.create_session(session_data)
        
        return StartSessionResponse(
            session_id=session_id,
            created_at=created_at,
            expires_at=expires_at,
            status=SessionStatus.ACTIVE
        )
    
    def add_captures(self, session_id: str, captures: List[Capture]) -> AddCapturesResponse:
        """
        Add captures to an existing session.
        
        Args:
            session_id: Session identifier
            captures: List of captures to add
        
        Returns:
            Updated session information
        
        Raises:
            HTTPException: If session not found, expired, or limits exceeded
        """
        # Validate batch size
        if len(captures) > settings.max_captures_per_batch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Batch size exceeds maximum of {settings.max_captures_per_batch}"
            )
        
        # Get session
        session = self.store.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        
        # Check if expired
        if session.status == SessionStatus.EXPIRED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_id} has expired"
            )
        
        # Check if already completed
        if session.status == SessionStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_id} is already completed"
            )
        
        # Check total capture limit
        new_total = len(session.captures) + len(captures)
        if new_total > settings.max_captures_per_session:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Adding captures would exceed session limit of {settings.max_captures_per_session}"
            )
        
        # Add captures
        session.captures.extend(captures)
        self.store.update_session(session_id, session)
        
        return AddCapturesResponse(
            session_id=session_id,
            captures_added=len(captures),
            total_captures_in_session=len(session.captures),
            status=session.status
        )
    
    def get_session(self, session_id: str) -> SessionData:
        """
        Get session data.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Session data
        
        Raises:
            HTTPException: If session not found
        """
        session = self.store.get_session(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        return session
    
    def mark_session_analyzing(self, session_id: str):
        """Mark session as analyzing"""
        session = self.get_session(session_id)
        session.status = SessionStatus.ANALYZING
        self.store.update_session(session_id, session)
    
    def mark_session_completed(self, session_id: str):
        """Mark session as completed"""
        session = self.get_session(session_id)
        session.status = SessionStatus.COMPLETED
        self.store.update_session(session_id, session)
    
    def cleanup_expired(self):
        """Clean up expired sessions"""
        self.store.cleanup_expired_sessions()


# Singleton instance
_session_manager = SessionManager()


def get_session_manager() -> SessionManager:
    """Get the session manager instance"""
    return _session_manager

