#!/usr/bin/env python3
"""
De-duplication logic for endpoints
"""

import hashlib
import logging
from typing import Dict, Set, Optional
from datetime import datetime, timedelta
from threading import Lock

logger = logging.getLogger(__name__)


class EndpointDeduplicator:
    """De-duplicates endpoints to avoid pushing duplicates"""
    
    def __init__(self, ttl_seconds: int = 3600):
        """
        Args:
            ttl_seconds: Time-to-live for deduplication cache (default: 1 hour)
        """
        self.ttl_seconds = ttl_seconds
        self.seen_endpoints: Dict[str, datetime] = {}  # hash -> timestamp
        self.lock = Lock()
        self._cleanup_interval = timedelta(seconds=300)  # Cleanup every 5 minutes
        self._last_cleanup = datetime.utcnow()
    
    def _generate_hash(self, endpoint_data: Dict) -> str:
        """Generate a hash for an endpoint based on its unique characteristics"""
        # Hash based on service, method, endpoint path, and status code
        key_parts = [
            endpoint_data.get("service", ""),
            endpoint_data.get("method", ""),
            endpoint_data.get("endpoint", ""),
            str(endpoint_data.get("status_code", "")),
            endpoint_data.get("type", "")  # request vs response
        ]
        
        # For requests, also consider headers signature to distinguish similar requests
        if endpoint_data.get("type") == "request":
            headers = endpoint_data.get("request_headers", {})
            # Create a signature from important headers (excluding variable ones like Date, User-Agent)
            important_headers = {}
            for h in ["Content-Type", "Accept", "Authorization"]:
                if h in headers:
                    important_headers[h] = headers[h]
            key_parts.append(str(sorted(important_headers.items())))
        
        key_string = "|".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def is_duplicate(self, endpoint_data: Dict) -> bool:
        """
        Check if an endpoint has been seen recently
        
        Returns:
            True if duplicate, False if new
        """
        endpoint_hash = self._generate_hash(endpoint_data)
        
        with self.lock:
            # Cleanup old entries periodically
            now = datetime.utcnow()
            if (now - self._last_cleanup) > self._cleanup_interval:
                self._cleanup_expired()
                self._last_cleanup = now
            
            # Check if we've seen this endpoint
            if endpoint_hash in self.seen_endpoints:
                seen_time = self.seen_endpoints[endpoint_hash]
                age = (now - seen_time).total_seconds()
                
                if age < self.ttl_seconds:
                    # Still within TTL, it's a duplicate
                    logger.debug(f"Duplicate endpoint detected: {endpoint_data.get('method')} {endpoint_data.get('endpoint')}")
                    return True
                else:
                    # Expired, remove it
                    del self.seen_endpoints[endpoint_hash]
            
            # Mark as seen
            self.seen_endpoints[endpoint_hash] = now
            return False
    
    def _cleanup_expired(self):
        """Remove expired entries from the cache"""
        now = datetime.utcnow()
        expired_hashes = [
            h for h, timestamp in self.seen_endpoints.items()
            if (now - timestamp).total_seconds() >= self.ttl_seconds
        ]
        
        for h in expired_hashes:
            del self.seen_endpoints[h]
        
        if expired_hashes:
            logger.debug(f"Cleaned up {len(expired_hashes)} expired endpoint entries")
    
    def clear(self):
        """Clear all cached endpoints"""
        with self.lock:
            self.seen_endpoints.clear()
            logger.info("Cleared all endpoint deduplication cache")

