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
                for group in endpoint_groups:
                    endpoints = group.get("endpoints", [])
                    for endpoint in endpoints:
                        method = self._normalize_method(endpoint.get("method", ""))
                        path = self._normalize_path(endpoint.get("path", ""))
                        endpoint_id = endpoint.get("id", "")
                        
                        if method and path and endpoint_id:
                            endpoint_map[f"{method}:{path}"] = endpoint_id
                
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
            
            payload = [{
                "method": method.lower(),
                "endpoint": self._normalize_path(endpoint_path),
                "payload": cleaned_body if cleaned_body else ""
            }]
            
            logger.info(f"➕ ADD ENDPOINT: POST {url}")
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
    
    def push_endpoint(
        self,
        app_id: str,
        instance_id: str,
        api_key: str,
        endpoint_data: Dict[str, Any]
    ) -> bool:
        """
        Push an endpoint (create or update based on existence)
        
        Args:
            app_id: Application ID
            instance_id: Instance ID
            api_key: API key
            endpoint_data: Endpoint capture data with method, endpoint, etc.
        
        Returns:
            True if successful
        """
        if not api_key:
            logger.error("API key is missing or empty in push_endpoint")
            return False
        
        # Strip whitespace from API key
        api_key = str(api_key).strip()
        if not api_key:
            logger.error("API key is empty after stripping whitespace in push_endpoint")
            return False
        
        method = self._normalize_method(endpoint_data.get("method", "GET"))
        endpoint_path = self._normalize_path(endpoint_data.get("endpoint", "/"))
        
        # Extract request body if available (from request type endpoints)
        request_body = endpoint_data.get("request_body", "")
        
        # Clean the request body - remove any trailing newlines/whitespace but preserve JSON structure
        if request_body:
            request_body = str(request_body).strip()
            # Only remove trailing newlines, don't strip internal whitespace
            request_body = request_body.rstrip('\n\r')
            logger.info(f"  📦 Extracted request body: {repr(request_body[:200])} (length: {len(request_body)})")
            
            # Validate it looks like JSON (starts with { or [)
            if request_body and not (request_body.startswith('{') or request_body.startswith('[')):
                logger.warning(f"  ⚠️  Request body doesn't look like JSON: {repr(request_body[:50])}")
        else:
            logger.info(f"  ⚠️  No request body found for {method.upper()} {endpoint_path}")
        
        # Check if endpoint exists (with fallback if listing fails)
        logger.info(f"🔍 PUSH ENDPOINT: Checking if endpoint exists: {method.upper()} {endpoint_path}")
        existing_endpoints = self.list_endpoints(app_id, instance_id, api_key)
        endpoint_key = f"{method}:{endpoint_path}"
        
        # If listing succeeded and endpoint exists, update it
        if existing_endpoints and endpoint_key in existing_endpoints:
            endpoint_id = existing_endpoints[endpoint_key]
            logger.info(f"🔄 Endpoint exists, updating: {endpoint_key} (ID: {endpoint_id})")
            return self.update_endpoint(app_id, instance_id, api_key, endpoint_id, request_body=request_body, query_params=[])
        else:
            # Endpoint doesn't exist or listing failed - try to add
            if not existing_endpoints:
                logger.info(f"⚠️  Could not list endpoints (may be new instance or API issue), attempting to add: {endpoint_key}")
            else:
                logger.info(f"✨ New endpoint, creating: {endpoint_key}")
            return self.add_endpoint(app_id, instance_id, api_key, method, endpoint_path, request_body)
    
    
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
