"""In-memory session storage (can be replaced with Redis)"""

from typing import Dict, Optional
from datetime import datetime, timedelta
from ..models.session import SessionData, SessionStatus
from ..core.config import settings
import threading


class SessionStore:
    """
    In-memory session storage.
    
    In production, this should be replaced with Redis or similar.
    This implementation uses a simple dict with thread-safety.
    """
    
    def __init__(self):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = threading.Lock()
    
    def create_session(self, session_data: SessionData) -> SessionData:
        """Create a new session"""
        with self._lock:
            self._sessions[session_data.session_id] = session_data
        return session_data
    
    def get_session(self, session_id: str) -> Optional[SessionData]:
        """Get a session by ID"""
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                # Check if expired
                if datetime.utcnow() > session.expires_at:
                    session.status = SessionStatus.EXPIRED
            return session
    
    def update_session(self, session_id: str, session_data: SessionData) -> SessionData:
        """Update an existing session"""
        with self._lock:
            self._sessions[session_id] = session_data
        return session_data
    
    def delete_session(self, session_id: str) -> bool:
        """Delete a session"""
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False
    
    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        with self._lock:
            current_time = datetime.utcnow()
            expired_ids = [
                sid for sid, session in self._sessions.items()
                if current_time > session.expires_at
            ]
            for sid in expired_ids:
                del self._sessions[sid]
    
    def session_exists(self, session_id: str) -> bool:
        """Check if a session exists"""
        with self._lock:
            return session_id in self._sessions
    
    def get_session_count(self) -> int:
        """Get total number of active sessions"""
        with self._lock:
            return len(self._sessions)


# Singleton instance
_session_store = SessionStore()


def get_session_store() -> SessionStore:
    """Get the session store instance"""
    return _session_store

