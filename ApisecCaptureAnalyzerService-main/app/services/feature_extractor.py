"""Feature extraction service"""

from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
from ..models.capture import Capture
from ..utils.hashing import hash_json_structure, extract_field_names, calculate_json_depth
from .url_parameterizer import get_url_parameterizer


class FeatureVector(Dict[str, Any]):
    """Feature vector extracted from a capture"""
    pass


class FeatureExtractor:
    """
    Extracts features from API captures for clustering analysis.
    """
    
    def __init__(self):
        self.parameterizer = get_url_parameterizer()
    
    def extract_features(self, capture: Capture) -> FeatureVector:
        """
        Extract all features from a capture.
        
        Args:
            capture: API capture to analyze
        
        Returns:
            Feature vector
        """
        url_features = self._extract_url_features(capture)
        header_features = self._extract_header_signature(capture)
        auth_features = self._extract_auth_signature(capture)
        response_features = self._extract_response_signature(capture)
        error_features = self._extract_error_signature(capture)
        
        return FeatureVector({
            "url_features": url_features,
            "header_signature": header_features,
            "auth_signature": auth_features,
            "response_signature": response_features,
            "error_signature": error_features,
            "original_url": capture.url,
            "method": capture.method,
            "status_code": capture.response.status,
            "duration_ms": capture.duration_ms
        })
    
    def _extract_url_features(self, capture: Capture) -> Dict[str, Any]:
        """Extract URL-based features"""
        parsed = urlparse(capture.url)
        base_url, parameterized_path = self.parameterizer.parameterize_url(capture.url)
        
        path_segments = [s for s in parsed.path.split('/') if s]
        
        # Extract a more meaningful base path
        # Skip generic segments and capture the resource identifier
        # e.g., /api/v1/users/123 -> /users (or /v1/users if v1 is significant)
        meaningful_segments = []
        for segment in path_segments:
            # Stop at parameterized segments
            if segment.isdigit() or len(segment) > 20:  # Likely an ID
                break
            # Skip generic API versioning prefixes
            if segment.lower() in ['api']:
                continue
            meaningful_segments.append(segment)
            # Stop after we have 2-3 meaningful segments
            if len(meaningful_segments) >= 2:
                break
        
        base_path = '/' + '/'.join(meaningful_segments) if meaningful_segments else '/'
        
        return {
            "domain": parsed.netloc,
            "subdomain": parsed.netloc.split('.')[0] if '.' in parsed.netloc else None,
            "port": parsed.port or (443 if parsed.scheme == 'https' else 80),
            "base_url": base_url,
            "parameterized_path": parameterized_path,
            "path_depth": len(path_segments),
            "base_path": base_path,
            "full_pattern": f"{base_url}{parameterized_path}"
        }
    
    def _extract_header_signature(self, capture: Capture) -> Dict[str, Any]:
        """
        Extract header signature (strong signal for microservice identification).
        """
        response_headers = {k.lower(): v for k, v in capture.response.headers.items()}
        request_headers = {k.lower(): v for k, v in capture.request.headers.items()}
        
        # Key headers that indicate service identity
        server = response_headers.get('server', '')
        powered_by = response_headers.get('x-powered-by', '')
        
        # Custom headers often indicate service
        custom_headers = set()
        service_indicators = {}
        
        for key, value in response_headers.items():
            if key.startswith('x-'):
                custom_headers.add(key)
                # Look for service name indicators
                if 'service' in key or 'app' in key:
                    service_indicators[key] = value
        
        # Create a fingerprint of consistent headers
        header_keys = sorted(custom_headers)
        header_fingerprint = ':'.join(header_keys)
        
        return {
            "server": server,
            "x_powered_by": powered_by,
            "custom_headers": list(custom_headers),
            "service_indicators": service_indicators,
            "header_fingerprint": header_fingerprint,
            "content_type": response_headers.get('content-type', ''),
            "cors_enabled": 'access-control-allow-origin' in response_headers
        }
    
    def _extract_auth_signature(self, capture: Capture) -> Dict[str, Any]:
        """Extract authentication pattern signature"""
        request_headers = {k.lower(): v for k, v in capture.request.headers.items()}
        
        auth_header = request_headers.get('authorization', '')
        cookie_header = request_headers.get('cookie', '')
        
        auth_type = None
        if auth_header:
            if auth_header.startswith('Bearer'):
                auth_type = 'Bearer'
            elif auth_header.startswith('Basic'):
                auth_type = 'Basic'
            elif auth_header.startswith('Digest'):
                auth_type = 'Digest'
            else:
                auth_type = 'Custom'
        elif cookie_header:
            auth_type = 'Cookie'
        
        # Pattern hash (not actual values)
        auth_pattern = f"{auth_type}:{'header' if auth_header else 'cookie'}"
        
        return {
            "auth_type": auth_type,
            "auth_location": "header" if auth_header else "cookie" if cookie_header else "none",
            "auth_pattern": auth_pattern,
            "has_api_key": 'api-key' in request_headers or 'x-api-key' in request_headers
        }
    
    def _extract_response_signature(self, capture: Capture) -> Dict[str, Any]:
        """Extract response schema signature"""
        response_body = capture.response.body
        
        if not response_body or not isinstance(response_body, dict):
            return {
                "schema_hash": None,
                "schema_depth": 0,
                "field_names": set(),
                "is_json": False
            }
        
        schema_hash = hash_json_structure(response_body)
        field_names = extract_field_names(response_body)
        depth = calculate_json_depth(response_body)
        
        # Common field patterns
        has_id = 'id' in field_names or any('id' in f for f in field_names)
        has_timestamps = any(
            ts in field_names 
            for ts in ['created_at', 'updated_at', 'timestamp', 'createdAt', 'updatedAt']
        )
        
        return {
            "schema_hash": schema_hash,
            "schema_depth": depth,
            "field_names": field_names,
            "field_count": len(field_names),
            "is_json": True,
            "has_id_field": has_id,
            "has_timestamps": has_timestamps
        }
    
    def _extract_error_signature(self, capture: Capture) -> Dict[str, Any]:
        """Extract error response signature"""
        status_code = capture.response.status
        is_error = status_code >= 400
        
        error_format = None
        error_fields = set()
        
        if is_error and isinstance(capture.response.body, dict):
            error_fields = set(capture.response.body.keys())
            # Common error formats
            if 'code' in error_fields and 'message' in error_fields:
                error_format = 'code_message'
            elif 'error' in error_fields:
                error_format = 'error_object'
            elif 'errors' in error_fields:
                error_format = 'errors_array'
            else:
                error_format = 'custom'
        
        return {
            "is_error": is_error,
            "status_code": status_code,
            "error_format": error_format,
            "error_fields": error_fields,
            "status_category": f"{status_code // 100}xx"
        }
    
    def extract_features_batch(self, captures: List[Capture]) -> List[FeatureVector]:
        """
        Extract features from multiple captures.
        
        Args:
            captures: List of captures
        
        Returns:
            List of feature vectors
        """
        print(f"[FeatureExtractor] Processing {len(captures)} captures")
        
        # Log ALL unique paths for debugging
        unique_paths = {}
        for c in captures:
            path = c.url.split('?')[0]  # Remove query params
            if '://' in path:
                path = '/' + '/'.join(path.split('/')[3:]) if len(path.split('/')) > 3 else '/'
            key = f"{c.method} {path}"
            unique_paths[key] = unique_paths.get(key, 0) + 1
        
        print(f"[FeatureExtractor] Unique URLs: {len(unique_paths)}")
        print(f"[FeatureExtractor] All captured endpoints:")
        for endpoint, count in sorted(unique_paths.items(), key=lambda x: -x[1])[:20]:
            print(f"[FeatureExtractor]   • {endpoint} (n={count})")
        if len(unique_paths) > 20:
            print(f"[FeatureExtractor]   ... and {len(unique_paths) - 20} more")
        
        features = [self.extract_features(capture) for capture in captures]
        
        return features


# Singleton instance
_feature_extractor = FeatureExtractor()


def get_feature_extractor() -> FeatureExtractor:
    """Get the feature extractor instance"""
    return _feature_extractor

