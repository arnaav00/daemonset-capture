#!/usr/bin/env python3
"""
API Client for pushing endpoints to dev website
"""

import json
import httpx
import logging
import sys
import time
import base64
import os
from typing import Dict, Optional, List, Any
from datetime import datetime
from io import BytesIO

# Try to import yaml for OpenAPI spec upload
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("WARNING: PyYAML not available, OpenAPI spec upload may fail", file=sys.stderr)

logger = logging.getLogger(__name__)
# Set logger to INFO level to show all API operations
logger.setLevel(logging.INFO)

# Simple debug logging with print statements (visible in kubectl logs)
def _debug_log(msg: str):
    """Print debug message to stderr (visible in kubectl logs)"""
    print(f"🔍 DEBUG: {msg}", file=sys.stderr, flush=True)


class DevWebsiteAPIClient:
    """Client for pushing endpoint data to the dev website"""
    
    def __init__(self, base_url: str = "https://api.dev.apisecapps.com", timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        # Cache for endpoint listings per instance
        self._endpoint_cache: Dict[str, Dict[str, str]] = {}  # instance_key -> {method:path -> endpoint_id}
        self._cache_lock = time.time()
        self._cache_ttl = 300  # 5 minutes
    
    def _generate_endpoint_id(self, method: str, endpoint_path: str) -> str:
        """Generate endpoint ID: base64(METHOD:ENDPOINT_PATH)"""
        method_upper = method.upper()
        encoded = f"{method_upper}:{endpoint_path}".encode('utf-8')
        return base64.b64encode(encoded).decode('utf-8')
    
    def _normalize_path(self, path: str) -> str:
        """Normalize endpoint path for comparison"""
        # Ensure path starts with /
        if not path.startswith('/'):
            path = '/' + path
        return path
    
    def _parameterize_path(self, path: str) -> str:
        """
        Parameterize an endpoint path by replacing numeric IDs and UUIDs with {id}
        
        Examples:
            /v1/users/1 -> /v1/users/{id}
            /api/v1/resource/123 -> /api/v1/resource/{id}
            /v1/users/550e8400-e29b-41d4-a716-446655440000 -> /v1/users/{id}
            /v1/users/123/orders/456 -> /v1/users/{id}/orders/{id}
            /v1/users/{id} -> /v1/users/{id} (already parameterized, unchanged)
        
        Args:
            path: The concrete path to parameterize
            
        Returns:
            The parameterized path
        """
        import re
        
        _debug_log(f"[PARAM_FUNC] ENTRY: path='{path}'")
        
        if not path or path == '/':
            _debug_log(f"[PARAM_FUNC] EXIT (empty/root): '{path}'")
            return path
        
        # Strip query string if present (shouldn't happen, but be safe)
        original_path = path
        if '?' in path:
            path = path.split('?')[0]
            _debug_log(f"[PARAM_FUNC] Stripped query: '{original_path}' -> '{path}'")
        
        # UUID pattern (8-4-4-4-12 hex digits)
        uuid_pattern = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
        # Numeric pattern (pure numbers, potentially large)
        numeric_pattern = re.compile(r'^\d+$')
        # Already parameterized patterns (e.g., {id}, {userId}, :id, @id)
        # Check for {name}, :name, or @name format
        is_parameterized = lambda s: (
            (s.startswith('{') and s.endswith('}')) or
            s.startswith(':') or
            s.startswith('@')
        )
        
        segments = path.split('/')
        _debug_log(f"[PARAM_FUNC] Split into {len(segments)} segments: {segments}")
        parameterized_segments = []
        changes_made = []
        
        for idx, segment in enumerate(segments):
            if not segment:
                # Preserve empty segments (leading/trailing slashes)
                parameterized_segments.append(segment)
                _debug_log(f"[PARAM_FUNC] Segment {idx}: '' -> preserved (empty)")
                continue
            
            # Skip if already parameterized (e.g., {id}, {userId}, :id)
            if is_parameterized(segment):
                parameterized_segments.append(segment)
                _debug_log(f"[PARAM_FUNC] Segment {idx}: '{segment}' -> preserved (already param)")
            # Check if segment is a UUID
            elif uuid_pattern.match(segment):
                parameterized_segments.append('{id}')
                changes_made.append(f"segment[{idx}] '{segment}' -> '{{id}}' (UUID)")
                _debug_log(f"[PARAM_FUNC] Segment {idx}: '{segment}' -> '{{id}}' (UUID)")
            # Check if segment is purely numeric (likely an ID)
            elif numeric_pattern.match(segment):
                parameterized_segments.append('{id}')
                changes_made.append(f"segment[{idx}] '{segment}' -> '{{id}}' (numeric)")
                _debug_log(f"[PARAM_FUNC] Segment {idx}: '{segment}' -> '{{id}}' (numeric)")
            else:
                # Keep literal segments as-is
                parameterized_segments.append(segment)
                _debug_log(f"[PARAM_FUNC] Segment {idx}: '{segment}' -> preserved (literal)")
        
        result = '/'.join(parameterized_segments)
        _debug_log(f"[PARAM_FUNC] RESULT: '{path}' -> '{result}'")
        if changes_made:
            logger.info(f"[PARAM_FUNC] Parameterized '{path}' -> '{result}': {', '.join(changes_made)}")
            _debug_log(f"[PARAM_FUNC] Changes: {', '.join(changes_made)}")
        return result
    
    def _normalize_method(self, method: str) -> str:
        """Normalize HTTP method for comparison"""
        return method.lower()
    
    def list_endpoints(self, app_id: str, instance_id: str, api_key: str) -> Dict[str, str]:
        """
        List all existing endpoints for an instance
        Returns dict mapping (method, path) -> endpoint_id
        """
        cache_key = f"{app_id}:{instance_id}"
        current_time = time.time()
        
        # Return cached if still valid
        if cache_key in self._endpoint_cache and (current_time - self._cache_lock) < self._cache_ttl:
            return self._endpoint_cache[cache_key]
        
        try:
            # Add query params that work (as user confirmed GET works with these)
            url = f"{self.base_url}/v1/applications/{app_id}/instances/{instance_id}/endpoints?include=metadata&slim=true"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"📋 LIST ENDPOINTS: GET {url}")
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                endpoint_map = {}
                
                # Parse endpointGroups structure
                endpoint_groups = data.get("endpointGroups", [])
                logger.debug(f"[LIST_ENDPOINTS] Found {len(endpoint_groups)} endpoint groups")
                for group in endpoint_groups:
                    endpoints = group.get("endpoints", [])
                    for idx, endpoint in enumerate(endpoints):
                        method = self._normalize_method(endpoint.get("method", ""))
                        raw_path_from_platform = endpoint.get("path", "")
                        path = self._normalize_path(raw_path_from_platform)
                        # Parameterize paths from platform to match our parameterized paths
                        parameterized_path = self._parameterize_path(path)
                        endpoint_id = endpoint.get("id", "")
                        
                        if method and parameterized_path and endpoint_id:
                            # Use parameterized path as key for matching
                            endpoint_key = f"{method}:{parameterized_path}"
                            endpoint_map[endpoint_key] = endpoint_id
                            # Log first 5 to show parameterization is happening
                            if idx < 5 and raw_path_from_platform != parameterized_path:
                                logger.info(f"[LIST_ENDPOINTS] Parameterized platform path: '{raw_path_from_platform}' -> '{parameterized_path}'")
                
                # Cache the result
                self._endpoint_cache[cache_key] = endpoint_map
                self._cache_lock = current_time
                
                logger.debug(f"Listed {len(endpoint_map)} existing endpoints for instance {instance_id}")
                return endpoint_map
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # No endpoints yet, return empty dict
                logger.info(f"  No endpoints found (404), returning empty list")
                return {}
            logger.error(f"✗ HTTP error listing endpoints: HTTP {e.response.status_code}")
            logger.error(f"  Response: {e.response.text}")
            return {}
        except Exception as e:
            logger.error(f"✗ Error listing endpoints: {str(e)}")
            return {}
    
    def add_endpoint(
        self,
        app_id: str,
        instance_id: str,
        api_key: str,
        method: str,
        endpoint_path: str,
        request_body: str = ""
    ) -> bool:
        """
        Create a new endpoint
        
        Args:
            app_id: Application ID
            instance_id: Instance ID
            api_key: API key
            method: HTTP method (get, post, etc.)
            endpoint_path: Endpoint path (e.g., "/workshop/api/mechanic_address/")
            request_body: Request body content (for POST/PUT requests)
        
        Returns:
            True if successful
        """
        try:
            if not api_key:
                logger.error("API key is missing or empty in add_endpoint")
                return False
            
            # Strip whitespace from API key
            api_key = str(api_key).strip()
            if not api_key:
                logger.error("API key is empty after stripping whitespace")
                return False
            
            url = f"{self.base_url}/v1/applications/{app_id}/instances/{instance_id}/add-endpoints"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Clean and format request body
            # Remove leading/trailing whitespace and newlines
            cleaned_body = ""
            if request_body:
                cleaned_body = str(request_body).strip()
                # Remove trailing newlines that might be in the captured body
                cleaned_body = cleaned_body.rstrip('\n\r')
                # Ensure it's not None or empty string after cleaning
                if not cleaned_body:
                    cleaned_body = ""
            
            # Log the actual body being sent for debugging
            logger.info(f"  Request body (cleaned): {repr(cleaned_body[:200])} (length: {len(cleaned_body)})")
            
            # endpoint_path should already be parameterized from push_endpoint()
            # Just normalize it (ensure it starts with /)
            final_path = self._normalize_path(endpoint_path)
            _debug_log(f"[ADD_ENDPOINT] Creating endpoint with path: '{final_path}'")
            _debug_log(f"[ADD_ENDPOINT] Method: {method.lower()}")
            logger.info(f"[ADD_ENDPOINT] Creating endpoint with path: {final_path}")
            logger.info(f"[ADD_ENDPOINT] Method: {method.lower()}")
            
            payload = [{
                "method": method.lower(),
                "endpoint": final_path,
                "payload": cleaned_body if cleaned_body else ""
            }]
            
            _debug_log(f"[ADD_ENDPOINT] Payload: {json.dumps(payload)}")
            _debug_log(f"[ADD_ENDPOINT] POST {url}")
            _debug_log(f"[ADD_ENDPOINT] Payload: {json.dumps(payload)}")
            logger.info(f"➕ ADD ENDPOINT: POST {url}")
            logger.info(f"[ADD_ENDPOINT] Payload being sent: {json.dumps(payload, indent=2)}")
            logger.info(f"  Method: {method.upper()}, Path: {endpoint_path}")
            logger.info(f"  Payload: {json.dumps(payload, indent=2)}")
            logger.info(f"  Headers: Authorization=Bearer {api_key[:30]}..., Content-Type=application/json")
            logger.debug(f"  API key length: {len(api_key)}, first 20 chars: {api_key[:20]}...")
            
            # Ensure API key is properly formatted (no extra whitespace)
            api_key_clean = str(api_key).strip()
            auth_header = f"Bearer {api_key_clean}"
            headers_final = {
                "Authorization": auth_header,
                "Content-Type": "application/json"
            }
            
            # Prepare JSON body
            json_body = json.dumps(payload)
            
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                # Use data= with explicit JSON string to match GET request pattern
                # GET works with headers, so POST should too with same approach
                response = client.post(
                    url, 
                    data=json_body,
                    headers=headers_final
                )
                logger.info(f"  Response: HTTP {response.status_code}")
                logger.debug(f"  Response body: {response.text[:200]}")
                
                # Log request details for debugging
                if response.status_code != 200 and response.status_code != 201:
                    logger.error(f"  Request URL: {url}")
                    logger.error(f"  Request headers sent: {dict(headers_final)}")
                    logger.error(f"  Request body: {json.dumps(payload)}")
                
                response.raise_for_status()
                
                # Invalidate cache
                cache_key = f"{app_id}:{instance_id}"
                if cache_key in self._endpoint_cache:
                    del self._endpoint_cache[cache_key]
                
                _debug_log(f"[ADD_ENDPOINT] *** SUCCESS: Created endpoint {method.upper()} {endpoint_path} ***")
                logger.info(f"✓ Successfully created endpoint: {method.upper()} {endpoint_path}")
                return True
                
        except httpx.HTTPStatusError as e:
            logger.error(f"✗ HTTP error adding endpoint: HTTP {e.response.status_code}")
            logger.error(f"  Response: {e.response.text}")
            logger.error(f"  URL: {url}")
            logger.error(f"  Headers: Authorization=Bearer {api_key[:20]}...")
            logger.error(f"  Payload: {json.dumps(payload, indent=2)}")
            # Try to parse error details
            try:
                error_json = e.response.json()
                logger.error(f"  Error details: {json.dumps(error_json, indent=2)}")
            except:
                pass
            return False
        except Exception as e:
            logger.error(f"Error adding endpoint: {str(e)}")
            return False
    
    def update_endpoint(
        self,
        app_id: str,
        instance_id: str,
        api_key: str,
        endpoint_id: str,
        request_body: str = "",
        query_params: Optional[List[Dict]] = None
    ) -> bool:
        """
        Update an existing endpoint
        
        Args:
            app_id: Application ID
            instance_id: Instance ID
            api_key: API key
            endpoint_id: Base64 encoded endpoint ID
            request_body: Request body content (JSON string)
            query_params: Optional list of query parameters
        
        Returns:
            True if successful
        """
        try:
            url = f"{self.base_url}/v1/applications/{app_id}/instances/{instance_id}/endpoints/{endpoint_id}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            event_data = {}
            if query_params:
                event_data["queryParams"] = query_params
            
            # Include request body if provided
            if request_body:
                # Clean request body but preserve JSON structure
                cleaned_body = str(request_body).strip().rstrip('\n\r')
                event_data["requestBody"] = {
                    "contentType": "JSON",
                    "content": cleaned_body
                }
                logger.info(f"  📝 Updating endpoint with request body: {repr(cleaned_body[:200])} (length: {len(cleaned_body)})")
            else:
                logger.info(f"  ⚠️  No request body provided for update")
            
            payload = {
                "eventType": "UPDATE",
                "eventData": event_data
            }
            
            logger.info(f"🔄 UPDATE ENDPOINT: PUT {url}")
            logger.info(f"  Payload: {json.dumps(payload, indent=2)}")
            
            # Ensure API key is properly formatted
            auth_header = f"Bearer {api_key.strip()}"
            headers_final = {
                "Authorization": auth_header,
                "Content-Type": "application/json"
            }
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.put(
                    url,
                    content=json.dumps(payload),
                    headers=headers_final
                )
                response.raise_for_status()
                
                logger.info(f"Successfully updated endpoint: {endpoint_id}")
                return True
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error updating endpoint: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"Error updating endpoint: {str(e)}")
            return False
    
    def _endpoint_to_bolt_json(self, endpoint_data: Dict[str, Any]) -> str:
        """
        Convert endpoint data to Bolt JSON format
        
        Args:
            endpoint_data: Endpoint capture data with method, endpoint, headers, request_body, etc.
        
        Returns:
            JSON string in Bolt format: {"requests": [{"method": "...", "url": "...", "requestHeaders": {...}, "requestBody": "..."}]}
        """
        method = endpoint_data.get("method", "GET").upper()
        path = endpoint_data.get("endpoint", "/")
        
        # Ensure path starts with /
        if not path.startswith('/'):
            path = '/' + path
        
        # Extract headers (convert to dict if needed)
        headers = endpoint_data.get("headers", {})
        if not isinstance(headers, dict):
            headers = {}
        
        # Extract request body
        request_body = endpoint_data.get("request_body", "")
        if request_body:
            request_body = str(request_body).strip().rstrip('\n\r')
        
        # Build Bolt request object
        bolt_request = {
            "method": method,
            "url": path,  # Bolt parser extracts path from URL, query params can be included here if needed
            "requestHeaders": headers,
        }
        
        if request_body:
            bolt_request["requestBody"] = request_body
        
        # Wrap in requests array
        bolt_json = {
            "requests": [bolt_request]
        }
        
        return json.dumps(bolt_json)
    
    def bolt_preview(
        self,
        app_id: str,
        instance_id: str,
        api_key: str,
        bolt_json: str
    ) -> Optional[Dict[str, Any]]:
        """
        Call Bolt preview endpoint to match requests against existing endpoints
        
        Args:
            app_id: Application ID
            instance_id: Instance ID
            api_key: API key
            bolt_json: Bolt JSON string with requests array
        
        Returns:
            Preview response dict with endpointSuggestions, or None if failed
        """
        try:
            url = f"{self.base_url}/v1/applications/{app_id}/instances/{instance_id}/bolt/preview"
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            # Prepare multipart file upload (bolt expects multipart form data with "file" field)
            files = {
                "file": ("bolt.json", BytesIO(bolt_json.encode('utf-8')), "application/json")
            }
            
            _debug_log(f"[BOLT_PREVIEW] POST {url}")
            logger.info(f"🔍 BOLT PREVIEW: POST {url}")
            
            with httpx.Client(timeout=self.timeout) as client:
                # Remove Content-Type header to let httpx set it for multipart
                headers.pop("Content-Type", None)
                response = client.post(url, headers=headers, files=files)
                response.raise_for_status()
                
                result = response.json()
                _debug_log(f"[BOLT_PREVIEW] Response: {result}")
                logger.info(f"✓ Bolt preview successful: {result.get('matchedRequests', 0)} matched, {result.get('unmatchedRequests', 0)} unmatched")
                
                return result
                
        except httpx.HTTPStatusError as e:
            _debug_log(f"[BOLT_PREVIEW] HTTP error: {e.response.status_code} - {e.response.text}")
            logger.error(f"HTTP error in bolt_preview: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            _debug_log(f"[BOLT_PREVIEW] Error: {str(e)}")
            logger.error(f"Error in bolt_preview: {str(e)}")
            return None
    
    def bolt_commit(
        self,
        app_id: str,
        instance_id: str,
        api_key: str,
        endpoint_selections: List[Dict[str, Any]]
    ) -> bool:
        """
        Call Bolt commit endpoint to apply endpoint updates
        
        Args:
            app_id: Application ID
            instance_id: Instance ID
            api_key: API key
            endpoint_selections: List of endpoint selection dicts with endpointId, include, headers, queryParams, pathParams, requestBodyExample
        
        Returns:
            True if successful
        """
        try:
            url = f"{self.base_url}/v1/applications/{app_id}/instances/{instance_id}/bolt/commit"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "applyRequestBodies": True,
                "endpoints": endpoint_selections
            }
            
            _debug_log(f"[BOLT_COMMIT] POST {url} with {len(endpoint_selections)} endpoints")
            logger.info(f"💾 BOLT COMMIT: POST {url} with {len(endpoint_selections)} endpoints")
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                
                result = response.json()
                _debug_log(f"[BOLT_COMMIT] Response: {result}")
                logger.info(f"✓ Bolt commit successful: {result.get('endpointsUpdated', 0)} updated, {result.get('endpointsAdded', 0)} added")
                
                return True
                
        except httpx.HTTPStatusError as e:
            _debug_log(f"[BOLT_COMMIT] HTTP error: {e.response.status_code} - {e.response.text}")
            logger.error(f"HTTP error in bolt_commit: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            _debug_log(f"[BOLT_COMMIT] Error: {str(e)}")
            logger.error(f"Error in bolt_commit: {str(e)}")
            return False
    
    def push_endpoint(
        self,
        app_id: str,
        instance_id: str,
        api_key: str,
        endpoint_data: Dict[str, Any]
    ) -> bool:
        """
        Push an endpoint using Bolt API (preview + commit)
        Uses server-side matching instead of client-side parameterization
        
        Args:
            app_id: Application ID
            instance_id: Instance ID
            api_key: API key
            endpoint_data: Endpoint capture data with method, endpoint, etc.
        
        Returns:
            True if successful
        """
        _debug_log(f"[PUSH_ENDPOINT] ===== ENTRY (BOLT API) ===== app_id={app_id}, instance_id={instance_id}")
        logger.info(f"[PUSH_ENDPOINT] ENTRY (BOLT API): app_id={app_id}, instance_id={instance_id}")
        
        if not api_key:
            _debug_log("[PUSH_ENDPOINT] ERROR: API key is missing")
            logger.error("API key is missing or empty in push_endpoint")
            return False
        
        # Strip whitespace from API key
        api_key = str(api_key).strip()
        if not api_key:
            _debug_log("[PUSH_ENDPOINT] ERROR: API key is empty after stripping")
            logger.error("API key is empty after stripping whitespace in push_endpoint")
            return False
        
        method = endpoint_data.get("method", "GET")
        path = endpoint_data.get("endpoint", "/")
        _debug_log(f"[PUSH_ENDPOINT] Method: {method}, Path: {path}")
        logger.info(f"🔍 PUSH ENDPOINT (Bolt): {method.upper()} {path}")
        
        # Step 1: Convert endpoint to Bolt JSON format
        bolt_json = self._endpoint_to_bolt_json(endpoint_data)
        _debug_log(f"[PUSH_ENDPOINT] Bolt JSON: {bolt_json}")
        logger.debug(f"Bolt JSON: {bolt_json}")
        
        # Step 2: Call preview to get matches
        preview_result = self.bolt_preview(app_id, instance_id, api_key, bolt_json)
        if not preview_result:
            _debug_log("[PUSH_ENDPOINT] Preview failed")
            logger.error("Bolt preview failed")
            return False
        
        # Step 3: Extract endpoint suggestions
        suggestions = preview_result.get("endpointSuggestions", [])
        unmatched_requests = preview_result.get("unmatched", [])
        
        if not suggestions:
            _debug_log("[PUSH_ENDPOINT] No endpoint suggestions returned (unmatched)")
            logger.warning(f"⚠️  No matching endpoint found for {method.upper()} {path} - endpoint doesn't exist yet")
            
            # Fallback: If endpoint doesn't exist, use old add_endpoint logic to create it
            # IMPORTANT: Parameterize the path first so that future requests with different IDs 
            # (e.g., /api/v2/orders/3) will match this endpoint via Bolt preview
            # Bolt's PathTemplate.match() matches concrete paths against parameterized templates
            logger.info(f"🔄 Falling back to add_endpoint() to create new endpoint (with parameterized path)")
            method_normalized = self._normalize_method(method)
            path_normalized = self._normalize_path(path)
            # Parameterize the path so Bolt can match future requests against it
            path_parameterized = self._parameterize_path(path_normalized)
            _debug_log(f"[PUSH_ENDPOINT] Parameterized path for new endpoint: '{path_normalized}' -> '{path_parameterized}'")
            logger.info(f"📝 Creating endpoint with parameterized path: {path_parameterized}")
            
            request_body = endpoint_data.get("request_body", "")
            if request_body:
                request_body = str(request_body).strip().rstrip('\n\r')
            
            return self.add_endpoint(app_id, instance_id, api_key, method_normalized, path_parameterized, request_body)
        
        # Step 4: Build commit payload from first suggestion (we only send one endpoint at a time)
        suggestion = suggestions[0]
        endpoint_id = suggestion.get("endpointId")
        if not endpoint_id:
            _debug_log("[PUSH_ENDPOINT] No endpointId in suggestion")
            logger.error("No endpointId in Bolt preview suggestion")
            return False
        
        # Extract headers and request body from original endpoint_data
        headers = endpoint_data.get("headers", {})
        request_body = endpoint_data.get("request_body", "")
        if request_body:
            request_body = str(request_body).strip().rstrip('\n\r')
        
        # Build endpoint selection for commit
        endpoint_selection = {
            "endpointId": endpoint_id,
            "include": True,
            "pathParams": suggestion.get("pathParams", {}),
            "queryParams": suggestion.get("queryParams", {}),
            "headers": headers,  # Use headers from captured endpoint
        }
        
        # Add requestBodyExample only if request body exists
        if request_body:
            endpoint_selection["requestBodyExample"] = {
                "contentType": headers.get("Content-Type", "application/json"),
                "content": request_body
            }
        
        _debug_log(f"[PUSH_ENDPOINT] Commit payload: {json.dumps(endpoint_selection)}")
        logger.info(f"💾 Committing endpoint: {endpoint_id}")
        
        # Step 5: Commit the endpoint
        success = self.bolt_commit(app_id, instance_id, api_key, [endpoint_selection])
        
        if success:
            _debug_log(f"[PUSH_ENDPOINT] SUCCESS: {method.upper()} {path} -> {endpoint_id}")
            logger.info(f"✓ Successfully pushed endpoint via Bolt API: {method.upper()} {path}")
        else:
            _debug_log(f"[PUSH_ENDPOINT] FAILED: Commit failed for {method.upper()} {path}")
            logger.error(f"❌ Bolt commit failed for {method.upper()} {path}")
        
        return success
    
    
    def get_application_by_name(self, application_name: str, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Get application by name by fetching all applications and searching
        
        Args:
            application_name: Name of the application
            api_key: API key for authentication
        
        Returns:
            Application dict with applicationId and instances, or None if not found
        """
        try:
            url = f"{self.base_url}/v1/applications?include=metadata"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            logger.info(f"🔍 LISTING ALL APPLICATIONS: GET {url}")
            
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                
                # Response has structure: {"applications": [...], "nextToken": ...}
                applications = data.get("applications", [])
                
                logger.info(f"  Found {len(applications)} total applications")
                
                # Log all application names for debugging
                app_names = [app.get("applicationName") for app in applications]
                logger.info(f"  Application names in response: {app_names}")
                
                # Search for matching application name (exact match, case-sensitive)
                for app in applications:
                    app_name = app.get("applicationName")
                    logger.info(f"  Comparing: '{app_name}' == '{application_name}'? {app_name == application_name}")
                    if app_name == application_name:
                        app_id = app.get("applicationId")
                        instances = app.get("instances", [])
                        logger.info(f"  ✓ Found matching application: '{application_name}' (appId: {app_id}, instances: {len(instances)})")
                        if instances:
                            instance_id = instances[0].get("instanceId")
                            logger.info(f"    First instance: instanceId={instance_id}")
                        return app
                
                logger.info(f"  ✗ No application found with name '{application_name}'")
                logger.info(f"  Available names: {app_names}")
                return None
                
        except httpx.HTTPStatusError as e:
            logger.error(f"Error listing applications: {e.response.status_code} - {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"Error listing applications: {str(e)}")
            return None
    
    def create_application(
        self,
        service_name: str,
        api_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new application with empty instance (auto-onboarding)
        First checks if application with same name exists, if so reuses it
        Otherwise uploads an empty/minimal OpenAPI spec to get applicationId, then creates instance
        
        Args:
            service_name: Name of the service
            api_key: API key for authentication
        
        Returns:
            Dictionary with applicationId and instanceId, or None on failure
        """
        logger.info(f"🚀 create_application() called with service_name='{service_name}'")
        try:
            # First check if application with this name already exists
            logger.info(f"🔍 CHECKING: Looking for existing application with name '{service_name}'")
            logger.info(f"  Calling get_application_by_name('{service_name}')...")
            
            try:
                existing_app = self.get_application_by_name(service_name, api_key)
                logger.info(f"  get_application_by_name returned: {existing_app is not None}")
            except Exception as check_error:
                logger.error(f"  ❌ ERROR in get_application_by_name: {check_error}")
                logger.error(f"  Exception type: {type(check_error).__name__}")
                import traceback
                logger.error(f"  Traceback: {traceback.format_exc()}")
                existing_app = None
            
            if existing_app:
                application_id = existing_app.get("applicationId")
                logger.info(f"✓ REUSING EXISTING APPLICATION: appId={application_id}, name='{service_name}'")
                
                # Check if it has instances
                instances = existing_app.get("instances", [])
                logger.info(f"  Application has {len(instances)} instance(s)")
                
                if instances and len(instances) > 0:
                    # Use first instance
                    instance_id = instances[0].get("instanceId")
                    instance_name = instances[0].get("instanceName", "unnamed")
                    logger.info(f"✓ REUSING EXISTING INSTANCE: instanceId={instance_id}, name='{instance_name}'")
                    logger.info(f"✅ Returning existing appId={application_id}, instanceId={instance_id}")
                    return {
                        "applicationId": application_id,
                        "instanceId": instance_id
                    }
                else:
                    # Create new instance for existing application (shouldn't happen but handle it)
                    logger.warning(f"⚠️  Existing application has no instances, creating new one")
                    logger.info(f"📦 Creating new instance for existing application")
                    instance_id = self._create_instance_for_app(application_id, service_name, api_key)
                    if instance_id:
                        logger.info(f"✅ Created instance for existing app: instanceId={instance_id}")
                        return {
                            "applicationId": application_id,
                            "instanceId": instance_id
                        }
                    logger.error(f"❌ Failed to create instance for existing application")
                    return None
            
            # No existing application, create new one
            logger.info(f"✨ Creating new application: name='{service_name}'")
            
            # Generate empty/minimal OpenAPI spec (no host URL needed, instance will use "/")
            openapi_spec = self._generate_empty_openapi_spec(service_name)
            
            # Upload OpenAPI spec
            upload_url = f"{self.base_url}/v1/applications/oas"
            
            logger.info(f"🚀 CREATE APPLICATION: POST {upload_url}")
            logger.info(f"  Service name: {service_name}")
            logger.info(f"  Origin: K8S_DAEMONSET")
            
            # Serialize to YAML
            if YAML_AVAILABLE:
                spec_content = yaml.dump(openapi_spec, default_flow_style=False, sort_keys=False)
                spec_bytes = spec_content.encode('utf-8')
                content_type = 'application/x-yaml'
                filename = 'openapi-spec.yaml'
            else:
                spec_content = json.dumps(openapi_spec, indent=2)
                spec_bytes = spec_content.encode('utf-8')
                content_type = 'application/json'
                filename = 'openapi-spec.json'
            
            files = {
                'fileUpload': (filename, BytesIO(spec_bytes), content_type)
            }
            data = {
                'applicationName': service_name,
                'origin': 'K8S_DAEMONSET'
            }
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            logger.debug(f"  Spec size: {len(spec_bytes)} bytes")
            
            with httpx.Client(timeout=self.timeout) as client:
                # Upload spec
                # Log request details for debugging
                logger.info(f"  Request URL: {upload_url}")
                logger.info(f"  API key (first 30 chars): {api_key[:30]}...")
                logger.info(f"  Headers: Authorization=Bearer {api_key[:30]}...")
                
                response = client.post(upload_url, files=files, data=data, headers=headers)
                logger.info(f"  Response: HTTP {response.status_code}")
                
                # If 401, log full error details
                if response.status_code == 401:
                    logger.error(f"  ✗ 401 Unauthorized - API key may be invalid or expired")
                    logger.error(f"  Response body: {response.text}")
                    logger.error(f"  Check API key in ConfigMap and verify it has correct permissions")
                
                logger.debug(f"  Response body: {response.text[:500]}")
                response.raise_for_status()
                upload_result = response.json()
                
                application_id = upload_result.get("applicationId")
                logger.info(f"✓ Application created: appId={application_id}")
                
                if not application_id:
                    logger.error("Failed to get applicationId from upload response")
                    return None
                
                # Create instance explicitly using /instances/batch endpoint
                instance_id = self._create_instance_for_app(application_id, service_name, api_key)
                
                if not instance_id:
                    logger.error(f"Could not create instanceId for application {application_id}")
                    return None
                
                logger.info(f"Successfully created application: appId={application_id}, instanceId={instance_id}")
                return {
                    "applicationId": application_id,
                    "instanceId": instance_id
                }
                
        except Exception as e:
            logger.error(f"Error creating application: {str(e)}")
            return None
    
    def _create_instance_for_app(self, application_id: str, service_name: str, api_key: str) -> Optional[str]:
        """
        Create an instance for an existing application
        
        Args:
            application_id: Application ID
            service_name: Service name (for instance naming)
            api_key: API key
        
        Returns:
            Instance ID if successful, None otherwise
        """
        try:
            headers_json = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            instances_url = f"{self.base_url}/v1/applications/{application_id}/instances/batch"
            payload = {
                "instanceRequestItems": [{
                    "hostUrl": "/",
                    "instanceName": f"{service_name}_instance"
                }]
            }
            
            logger.info(f"📦 CREATE INSTANCE: POST {instances_url}")
            logger.info(f"  Payload: {json.dumps(payload, indent=2)}")
            
            # Ensure API key is properly formatted
            auth_header_final = f"Bearer {api_key.strip()}"
            headers_json_final = {
                "Authorization": auth_header_final,
                "Content-Type": "application/json"
            }
            
            with httpx.Client(timeout=self.timeout) as client:
                try:
                    response = client.post(
                        instances_url,
                        content=json.dumps(payload),
                        headers=headers_json_final
                    )
                    logger.info(f"  Response: HTTP {response.status_code}")
                    logger.debug(f"  Response body: {response.text[:500]}")
                    response.raise_for_status()
                    instance_result = response.json()
                    
                    # Extract instanceId from response
                    instance_id = None
                    if isinstance(instance_result, list) and len(instance_result) > 0:
                        instance_id = instance_result[0].get("instanceId")
                    elif isinstance(instance_result, dict):
                        instance_id = instance_result.get("instanceId")
                        # Check if response has items array
                        if not instance_id and "items" in instance_result:
                            items = instance_result.get("items", [])
                            if items and len(items) > 0:
                                instance_id = items[0].get("instanceId")
                    
                    if instance_id:
                        logger.info(f"✓ Instance created: instanceId={instance_id}")
                        return instance_id
                    
                    # If still no instanceId, fetch from application (with retry)
                    logger.warning("No instanceId in batch response, fetching from application")
                    max_retries = 5
                    for attempt in range(max_retries):
                        try:
                            import time
                            time.sleep(1)  # Wait a bit for instance to be created
                            app_url = f"{self.base_url}/v1/applications/{application_id}"
                            get_response = client.get(app_url, headers=headers_json)
                            if get_response.status_code == 200:
                                app_data = get_response.json()
                                instances = app_data.get("instances", [])
                                if instances and len(instances) > 0:
                                    instance_id = instances[0].get("instanceId")
                                    logger.info(f"Found instanceId from application fetch: {instance_id}")
                                    return instance_id
                        except Exception as fetch_error:
                            logger.debug(f"Error fetching application (attempt {attempt + 1}): {fetch_error}")
                            if attempt < max_retries - 1:
                                import time
                                time.sleep(1)
                    
                    return None
                    
                except Exception as e:
                    logger.error(f"Error creating instance: {e}")
                    # Try fetching application to see if instance was created automatically
                    try:
                        app_url = f"{self.base_url}/v1/applications/{application_id}"
                        get_response = client.get(app_url, headers=headers_json)
                        if get_response.status_code == 200:
                            app_data = get_response.json()
                            instances = app_data.get("instances", [])
                            if instances and len(instances) > 0:
                                instance_id = instances[0].get("instanceId")
                                logger.info(f"Found instanceId from application fetch: {instance_id}")
                                return instance_id
                    except Exception as fetch_error:
                        logger.warning(f"Could not fetch application: {fetch_error}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error in _create_instance_for_app: {str(e)}")
            return None
    
    def _generate_empty_openapi_spec(self, service_name: str) -> Dict[str, Any]:
        """Generate an empty/minimal OpenAPI spec for creating application"""
        return {
            "openapi": "3.0.0",
            "info": {
                "title": service_name,
                "version": "1.0.0",
                "description": f"Auto-onboarded service: {service_name}"
            },
            "servers": [
                {
                    "url": "/",
                    "description": "Default server"
                }
            ],
            "paths": {}
        }
