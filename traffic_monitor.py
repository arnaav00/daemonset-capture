#!/usr/bin/env python3
"""
Kubernetes DaemonSet Traffic Monitor
Captures API endpoint requests/responses at the node level
"""

import json
import socket
import struct
import sys
import time
import os
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import subprocess
import threading
import queue
import logging
import re

# Try to import scapy for packet capture, fallback to raw sockets
try:
    from scapy.all import sniff, IP, TCP, UDP, Raw, get_if_list
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False
    get_if_list = None
    print("WARNING: scapy not available, using raw socket capture", file=sys.stderr)

# Try to import integration components (optional)
try:
    from service_mapper import ServiceMapper
    from api_client import DevWebsiteAPIClient
    from deduplicator import EndpointDeduplicator
    INTEGRATION_AVAILABLE = True
except ImportError as e:
    INTEGRATION_AVAILABLE = False
    print(f"WARNING: Integration components not available: {e}", file=sys.stderr)
    print("Endpoint pushing to dev website will be disabled", file=sys.stderr)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
    force=True  # Force reconfiguration
)

# Set API client logger to INFO to see all API operations
api_logger = logging.getLogger('api_client')
api_logger.setLevel(logging.INFO)
service_logger = logging.getLogger('service_mapper')
service_logger.setLevel(logging.INFO)

class TrafficMonitor:
    def __init__(self, output_file: str = "/tmp/endpoints.json", node_name: str = None):
        self.output_file = output_file
        self.node_name = node_name or os.environ.get('NODE_NAME', 'unknown-node')
        self.endpoints = []
        self.endpoint_lock = threading.Lock()
        self.http_connections = {}  # Track HTTP connections
        self.tcp_streams = {}  # Track TCP streams for reassembly
        self.stream_last_packet_time = {}  # Track when last packet arrived for each stream
        self.output_queue = queue.Queue()
        self.running = True
        
        # Integration components (optional)
        self.service_mapper = None
        self.api_client = None
        self.deduplicator = None
        self.enable_integration = os.environ.get('ENABLE_DEV_WEBSITE_INTEGRATION', 'false').lower() == 'true'
        
        # Lock for preventing concurrent auto-onboarding of the same service
        self._onboarding_locks: Dict[str, threading.Lock] = {}
        self._onboarding_lock = threading.Lock()  # Lock for managing the locks dict
        
        if INTEGRATION_AVAILABLE and self.enable_integration:
            try:
                config_path = os.environ.get('SERVICE_CONFIG_PATH', '/etc/traffic-monitor/service_config.json')
                clear_mappings = os.environ.get('CLEAR_SAVED_MAPPINGS', 'false').lower() == 'true'
                
                print(f"🔧 Initializing integration components...", file=sys.stderr, flush=True)
                print(f"  Config path: {config_path}", file=sys.stderr, flush=True)
                
                # Initialize service mapper - may have JSON parse errors but should continue
                try:
                    self.service_mapper = ServiceMapper(config_path=config_path)
                except Exception as mapper_error:
                    print(f"  ⚠️ WARNING: ServiceMapper initialization had errors: {mapper_error}", file=sys.stderr, flush=True)
                    print(f"  Continuing with defaults...", file=sys.stderr, flush=True)
                    # Re-initialize with defaults
                    self.service_mapper = ServiceMapper(config_path=config_path)
                
                # Clear saved mappings if requested
                if clear_mappings:
                    print(f"  🗑️  Clearing saved service mappings...", file=sys.stderr, flush=True)
                    self.service_mapper.clear_saved_mappings()
                
                dev_api_url = self.service_mapper.get_dev_api_url()
                api_key = self.service_mapper.get_api_key()
                print(f"  Dev API URL: {dev_api_url}", file=sys.stderr, flush=True)
                print(f"  API key present: {bool(api_key)}", file=sys.stderr, flush=True)
                if api_key:
                    print(f"  API key length: {len(api_key)}", file=sys.stderr, flush=True)
                
                auto_onboard = self.service_mapper.is_auto_onboard_enabled()
                print(f"  Auto-onboard enabled: {auto_onboard}", file=sys.stderr, flush=True)
                
                # Show current mappings
                existing_mappings = self.service_mapper.config.get("serviceMappings", {})
                if existing_mappings:
                    print(f"  ⚠️  Existing service mappings found:", file=sys.stderr, flush=True)
                    for svc, mapping in existing_mappings.items():
                        print(f"    - {svc}: appId={mapping.get('appId')}, instanceId={mapping.get('instanceId')}", 
                              file=sys.stderr, flush=True)
                    print(f"  💡 To clear these and force re-onboarding, set CLEAR_SAVED_MAPPINGS=true", 
                          file=sys.stderr, flush=True)
                else:
                    print(f"  ✓ No existing service mappings", file=sys.stderr, flush=True)
                
                self.api_client = DevWebsiteAPIClient(base_url=dev_api_url)
                self.deduplicator = EndpointDeduplicator()
                print(f"✓ Integration enabled: Dev website URL={dev_api_url}", file=sys.stderr, flush=True)
            except Exception as e:
                print(f"❌ ERROR: Failed to initialize integration components: {e}", file=sys.stderr, flush=True)
                import traceback
                traceback.print_exc(file=sys.stderr)
                self.enable_integration = False
        elif self.enable_integration:
            print("⚠️ WARNING: Integration requested but components not available", file=sys.stderr, flush=True)
        
        # Start output writer thread
        self.writer_thread = threading.Thread(target=self._write_outputs, daemon=True)
        self.writer_thread.start()
    
    def _extract_service_name(self, host: str, dst_ip: str = None) -> str:
        """Extract service name from Host header or IP address"""
        logger = logging.getLogger(__name__)
        
        if not host:
            logger.debug(f"  _extract_service_name called with empty host, dst_ip={dst_ip}")
            if dst_ip:
                # Try to resolve service name from destination IP via Kubernetes API
                service_name = self._get_service_name_from_ip(dst_ip)
                if service_name != "unknown":
                    logger.debug(f"  Identified service '{service_name}' from dst_ip '{dst_ip}'")
                    return service_name
            logger.debug(f"  Host is empty and dst_ip could not be resolved, returning 'unknown'")
            return "unknown"
        
        host_without_port = host.split(':')[0]
        service_name_from_host = host_without_port.split('.')[0]
        
        # Check if it's an IP address
        try:
            socket.inet_aton(service_name_from_host)
            # It's an IP, not a service name from host header. Try to resolve from dst_ip.
            logger.debug(f"  Host header is IP ({service_name_from_host}), trying to resolve from dst_ip={dst_ip}")
            if dst_ip:
                service_name = self._get_service_name_from_ip(dst_ip)
                if service_name != "unknown":
                    logger.debug(f"  Identified service '{service_name}' from dst_ip '{dst_ip}' (Host was IP)")
                    return service_name
            logger.debug(f"  Host header is IP and dst_ip could not be resolved, returning 'unknown'")
            return "unknown"
        except (socket.error, ValueError):
            # Not an IP, assume it's a service name from host header
            logger.debug(f"  Identified service '{service_name_from_host}' from host header '{host}'")
            print(f"✓ Identified service from Host header: '{service_name_from_host}' (from host='{host}')", 
                  file=sys.stderr, flush=True)
            return service_name_from_host
    
    def _get_service_name_from_ip(self, ip_address: str) -> str:
        """Queries Kubernetes API to map an IP address to a service name."""
        logger = logging.getLogger(__name__)
        # This requires kubectl to be available in the container and proper RBAC permissions
        # For simplicity, we'll use a basic lookup. In a real scenario, consider a more robust client.
        try:
            # First, try to get the pod name for the IP
            pod_name_cmd = ["kubectl", "get", "pods", "-A", "-o", 
                           f"jsonpath={{.items[?(@.status.podIP=='{ip_address}')].metadata.name}}"]
            pod_name_result = subprocess.run(pod_name_cmd, capture_output=True, text=True, check=False, timeout=2)
            pod_name = pod_name_result.stdout.strip()
            
            if pod_name:
                # If a pod is found, try to infer service name from pod labels or owner references
                # This is a heuristic and might not always be accurate
                pod_desc_cmd = ["kubectl", "describe", "pod", pod_name.split()[0], "-n", "default"]
                pod_desc_result = subprocess.run(pod_desc_cmd, capture_output=True, text=True, check=False, timeout=2)
                
                # Look for common labels like 'app' or 'service'
                import re
                match = re.search(r'Labels:\s*app=(?P<app_name>[^\s]+)', pod_desc_result.stdout)
                if match:
                    logger.debug(f"  Resolved service name '{match.group('app_name')}' from pod '{pod_name}' labels.")
                    return match.group('app_name')
                
                match = re.search(r'Labels:\s*service=(?P<svc_name>[^\s]+)', pod_desc_result.stdout)
                if match:
                    logger.debug(f"  Resolved service name '{match.group('svc_name')}' from pod '{pod_name}' labels.")
                    return match.group('svc_name')
                
                # Fallback: try to get service that targets this pod's IP
                service_cmd = ["kubectl", "get", "services", "-A", "-o", 
                              f"jsonpath={{.items[?(@.spec.clusterIP=='{ip_address}')].metadata.name}}"]
                service_result = subprocess.run(service_cmd, capture_output=True, text=True, check=False, timeout=2)
                service_name = service_result.stdout.strip()
                if service_name:
                    logger.debug(f"  Resolved service name '{service_name}' from clusterIP '{ip_address}'.")
                    return service_name.split()[0]
            
            logger.debug(f"  Could not resolve service name for IP '{ip_address}' from Kubernetes API.")
            return "unknown"
        except FileNotFoundError:
            # kubectl not available in container - this is expected, just return unknown
            return "unknown"
        except subprocess.TimeoutExpired:
            logger.debug(f"  Timeout querying Kubernetes API for IP '{ip_address}'")
            return "unknown"
        except Exception as e:
            # Silently fail - kubectl lookup is optional, Host header should handle it
            return "unknown"
        
    def _write_outputs(self):
        """Write captured endpoints to file periodically"""
        while self.running:
            try:
                endpoint = self.output_queue.get(timeout=5)
                if endpoint:
                    self._write_endpoint(endpoint)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error writing endpoint: {e}", file=sys.stderr)
    
    def _write_endpoint(self, endpoint: Dict):
        """Write single endpoint to JSON file and optionally push to dev website"""
        # Always write to file for backwards compatibility
        try:
            with open(self.output_file, 'a') as f:
                f.write(json.dumps(endpoint) + '\n')
            # Also print to stdout for kubectl logs
            print(f"ENDPOINT_CAPTURE: {json.dumps(endpoint)}")
        except Exception as e:
            print(f"Error writing to file: {e}", file=sys.stderr)
        
        # Push to dev website if integration is enabled
        if not self.enable_integration:
            # Integration not enabled, skip silently
            return
        
        if not (self.deduplicator and self.service_mapper and self.api_client):
            print(f"⚠️ WARNING: Integration enabled but components missing: deduplicator={bool(self.deduplicator)}, "
                  f"service_mapper={bool(self.service_mapper)}, api_client={bool(self.api_client)}", 
                  file=sys.stderr, flush=True)
            return
        
        # Integration is enabled and all components are available
        if self.enable_integration and self.deduplicator and self.service_mapper and self.api_client:
            try:
                service_name = endpoint.get("service", "unknown")
                method = endpoint.get("method", "UNKNOWN")
                endpoint_path = endpoint.get("endpoint", "/")
                
                print(f"🔄 Processing endpoint for integration: {service_name} {method} {endpoint_path}", 
                      file=sys.stderr, flush=True)
                
                # Only push REQUEST type endpoints to platform (not responses)
                endpoint_type = endpoint.get("type", "")
                if endpoint_type != "request":
                    print(f"  ⏭️  Skipping {endpoint_type} endpoint (only requests are pushed to platform)", 
                          file=sys.stderr, flush=True)
                    return  # Skip responses, only push requests
                
                # Check de-duplication first
                if self.deduplicator.is_duplicate(endpoint):
                    print(f"  ⏭️  Skipping duplicate endpoint", file=sys.stderr, flush=True)
                    return  # Skip duplicate
                
                if service_name == "unknown":
                    print(f"  ⏭️  Skipping unknown service", file=sys.stderr, flush=True)
                    return  # Skip unknown services
                
                # Get API key (top-level)
                api_key = self.service_mapper.get_api_key()
                if not api_key:
                    print(f"  ❌ WARNING: No API key configured, skipping endpoint push for service '{service_name}'", 
                          file=sys.stderr, flush=True)
                    return  # No API key configured
                
                print(f"  ✓ API key present, proceeding with push", file=sys.stderr, flush=True)
                
                # Get service mapping (check again with lock to prevent race condition)
                mapping = self.service_mapper.get_service_mapping(service_name)
                
                if mapping:
                    # Service is configured, push the endpoint
                    app_id = mapping.get("appId")
                    instance_id = mapping.get("instanceId")
                    
                    print(f"  ✓ Service '{service_name}' is mapped: appId={app_id}, instanceId={instance_id}", 
                          file=sys.stderr, flush=True)
                    
                    if app_id and instance_id:
                        # Push to dev website in a separate thread to avoid blocking
                        print(f"  🚀 Starting thread to push endpoint to dev website", file=sys.stderr, flush=True)
                        threading.Thread(
                            target=self._push_endpoint_to_dev_website,
                            args=(app_id, instance_id, api_key, endpoint),
                            daemon=True
                        ).start()
                    else:
                        print(f"  ❌ Missing appId or instanceId for service '{service_name}'", 
                              file=sys.stderr, flush=True)
                elif self.service_mapper.is_auto_onboard_enabled():
                    print(f"  ✨ Auto-onboarding enabled, attempting to onboard service '{service_name}'", 
                          file=sys.stderr, flush=True)
                    # Check again with lock to prevent concurrent onboarding
                    with self._onboarding_lock:
                        if service_name not in self._onboarding_locks:
                            self._onboarding_locks[service_name] = threading.Lock()
                        service_lock = self._onboarding_locks[service_name]
                    
                    # Try to acquire lock - if we get it, proceed with onboarding
                    # If we can't get it immediately, another thread is already onboarding
                    if service_lock.acquire(blocking=False):
                        print(f"  🔒 Acquired lock for service '{service_name}', proceeding with onboarding", 
                              file=sys.stderr, flush=True)
                        try:
                            # Double-check mapping wasn't added while waiting for lock
                            mapping = self.service_mapper.get_service_mapping(service_name)
                            if not mapping:
                                # Auto-onboard new service
                                threading.Thread(
                                    target=self._auto_onboard_service,
                                    args=(service_name, endpoint, api_key, service_lock),
                                    daemon=True
                                ).start()
                            else:
                                # Mapping was added, release lock and push endpoint
                                service_lock.release()
                                app_id = mapping.get("appId")
                                instance_id = mapping.get("instanceId")
                                if app_id and instance_id:
                                    threading.Thread(
                                        target=self._push_endpoint_to_dev_website,
                                        args=(app_id, instance_id, api_key, endpoint),
                                        daemon=True
                                    ).start()
                        except Exception as e:
                            service_lock.release()
                            print(f"Error in auto-onboarding check: {e}", file=sys.stderr, flush=True)
                    else:
                        # Another thread is onboarding this service, skip for now
                        # The endpoint will be processed after onboarding completes
                        print(f"  ⏳ Another thread is onboarding '{service_name}', skipping this endpoint", 
                              file=sys.stderr, flush=True)
            except Exception as e:
                print(f"Error in integration logic: {e}", file=sys.stderr, flush=True)
    
    def _push_endpoint_to_dev_website(self, app_id: str, instance_id: str, api_key: str, endpoint: Dict):
        """Push endpoint to dev website (called in separate thread)"""
        try:
            if not api_key:
                print(f"ERROR: API key is missing when pushing endpoint {endpoint.get('method')} {endpoint.get('endpoint')}", 
                      file=sys.stderr, flush=True)
                return
            
            success = self.api_client.push_endpoint(app_id, instance_id, api_key, endpoint)
            if success:
                print(f"✓ Pushed endpoint to dev website: {endpoint.get('method')} {endpoint.get('endpoint')} "
                      f"(appId={app_id}, instanceId={instance_id})", file=sys.stderr, flush=True)
            else:
                print(f"✗ Failed to push endpoint: {endpoint.get('method')} {endpoint.get('endpoint')}", 
                      file=sys.stderr, flush=True)
        except Exception as e:
            print(f"Error pushing endpoint to dev website: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
    
    def _auto_onboard_service(self, service_name: str, endpoint: Dict, api_key: str, service_lock: threading.Lock):
        """Auto-onboard a new service (called in separate thread, holds service_lock)"""
        try:
            print(f"🚀 STARTING AUTO-ONBOARDING for service '{service_name}'", file=sys.stderr, flush=True)
            
            # Double-check mapping wasn't added by another thread while waiting
            # Reload config to get latest state
            self.service_mapper._load_config()
            mapping = self.service_mapper.get_service_mapping(service_name)
            if mapping:
                # Mapping exists now, use it
                app_id = mapping.get("appId")
                instance_id = mapping.get("instanceId")
                service_lock.release()
                print(f"✓ Service '{service_name}' already onboarded: appId={app_id}, instanceId={instance_id}", 
                      file=sys.stderr, flush=True)
                # Push this endpoint
                self._push_endpoint_to_dev_website(app_id, instance_id, api_key, endpoint)
                return
            
            # FIRST: Check if application with this name already exists on the platform
            print(f"🔍 STEP 1: Checking platform for existing application with name '{service_name}'", file=sys.stderr, flush=True)
            print(f"  Making GET request to /v1/applications?include=metadata...", file=sys.stderr, flush=True)
            existing_app = self.api_client.get_application_by_name(service_name, api_key)
            
            if existing_app:
                application_id = existing_app.get("applicationId")
                instances = existing_app.get("instances", [])
                print(f"✓ STEP 1 RESULT: Found existing application on platform", file=sys.stderr, flush=True)
                print(f"  appId: {application_id}", file=sys.stderr, flush=True)
                print(f"  instances count: {len(instances)}", file=sys.stderr, flush=True)
                
                if instances and len(instances) > 0:
                    instance_id = instances[0].get("instanceId")
                    instance_name = instances[0].get("instanceName", "unnamed")
                    print(f"✓ STEP 2: Using existing instance", file=sys.stderr, flush=True)
                    print(f"  instanceId: {instance_id}", file=sys.stderr, flush=True)
                    print(f"  instanceName: {instance_name}", file=sys.stderr, flush=True)
                    
                    # STEP 3: Save the mapping to prevent future creation
                    print(f"📝 STEP 3: Saving service mapping to prevent future app creation...", file=sys.stderr, flush=True)
                    self.service_mapper.set_service_mapping(service_name, application_id, instance_id)
                    
                    # STEP 4: Reload config to ensure mapping is loaded
                    print(f"🔄 STEP 4: Reloading config to verify mapping was saved...", file=sys.stderr, flush=True)
                    self.service_mapper._load_config()
                    
                    # STEP 5: Verify mapping exists (should prevent CREATE APPLICATION)
                    verify_mapping = self.service_mapper.get_service_mapping(service_name)
                    if verify_mapping:
                        print(f"✓ STEP 5: Verified mapping exists - will NOT create new application", file=sys.stderr, flush=True)
                        print(f"  Saved mapping: appId={verify_mapping.get('appId')}, instanceId={verify_mapping.get('instanceId')}", file=sys.stderr, flush=True)
                    else:
                        print(f"⚠️  WARNING: Mapping verification failed, but continuing...", file=sys.stderr, flush=True)
                    
                    service_lock.release()
                    
                    print(f"✅ SUCCESS: Reused existing application and saved mapping", file=sys.stderr, flush=True)
                    print(f"  Service: '{service_name}' -> appId={application_id}, instanceId={instance_id}", file=sys.stderr, flush=True)
                    # Push this endpoint
                    self._push_endpoint_to_dev_website(application_id, instance_id, api_key, endpoint)
                    return
                else:
                    print(f"⚠️  Existing application has no instances, will create one via create_application()", file=sys.stderr, flush=True)
            else:
                print(f"✗ STEP 1 RESULT: No existing application found with name '{service_name}'", file=sys.stderr, flush=True)
            
            # No existing application found, create new one
            print(f"✨ STEP 1 COMPLETE: Proceeding to create new application for '{service_name}'", file=sys.stderr, flush=True)
            result = self.api_client.create_application(
                service_name=service_name,
                api_key=api_key
            )
            
            if result and result.get("applicationId"):
                app_id = result["applicationId"]
                instance_id = result.get("instanceId")
                
                print(f"✓ Step 1 COMPLETE: Application created - appId={app_id}", file=sys.stderr, flush=True)
                
                # Save the mapping automatically
                if instance_id:
                    print(f"✓ Step 2 COMPLETE: Instance created - instanceId={instance_id}", file=sys.stderr, flush=True)
                    print(f"📝 Step 3: Saving service mapping...", file=sys.stderr, flush=True)
                    self.service_mapper.set_service_mapping(service_name, app_id, instance_id)
                    print(f"✓ Step 3 COMPLETE: Service mapping saved", file=sys.stderr, flush=True)
                    print(f"✅ SUCCESS: Auto-onboarded service '{service_name}': appId={app_id}, instanceId={instance_id}", 
                          file=sys.stderr, flush=True)
                    
                    # Release lock now that mapping is saved
                    service_lock.release()
                    
                    # Now push this endpoint
                    print(f"📝 Step 4: Pushing initial endpoint...", file=sys.stderr, flush=True)
                    self._push_endpoint_to_dev_website(app_id, instance_id, api_key, endpoint)
                else:
                    print(f"❌ ERROR: Step 2 FAILED - Auto-onboarded '{service_name}' but no instanceId returned", 
                          file=sys.stderr, flush=True)
                    print(f"  Application was created but instance creation failed", file=sys.stderr, flush=True)
                    service_lock.release()
            else:
                print(f"❌ ERROR: Step 1 FAILED - Failed to auto-onboard service '{service_name}'", 
                      file=sys.stderr, flush=True)
                if result:
                    print(f"  Result: {result}", file=sys.stderr, flush=True)
                service_lock.release()
        except Exception as e:
            print(f"Error in auto-onboarding: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            service_lock.release()
    
    def _is_complete_http_message(self, data: bytes) -> tuple[bool, int]:
        """Check if data contains a complete HTTP message (headers + full body if Content-Length specified)
        
        Returns:
            (is_complete, expected_total_length)
            - is_complete: True if message is complete
            - expected_total_length: Total expected length (header_length + content_length) or None if unknown
        """
        # HTTP headers end with \r\n\r\n
        if b'\r\n\r\n' not in data:
            return (False, None)
        
        # Split headers and body
        header_data, body_data = data.split(b'\r\n\r\n', 1)
        header_length = len(header_data) + 4  # +4 for \r\n\r\n
        
        # Parse Content-Length header
        header_lines = header_data.split(b'\r\n')
        content_length = None
        for line in header_lines[1:]:  # Skip request/status line
            if not line:  # Empty line indicates end of headers
                break
            if b':' in line:
                key, value = line.split(b':', 1)
                key_lower = key.decode('utf-8', errors='ignore').strip().lower()
                if key_lower == 'content-length':
                    try:
                        content_length_str = value.decode('utf-8', errors='ignore').strip()
                        content_length = int(content_length_str)
                        print(f"  🔍 DEBUG _is_complete_http_message: Found Content-Length = {content_length} (from header value: '{content_length_str}')", file=sys.stderr, flush=True)
                        break
                    except ValueError as e:
                        print(f"  ⚠️  WARNING: Could not parse Content-Length value '{value.decode('utf-8', errors='ignore')}': {e}", file=sys.stderr, flush=True)
                        pass
        
        # If Content-Length is specified, check if we have the full body
        if content_length is not None:
            expected_total = header_length + content_length
            if len(data) < expected_total:
                # Body is incomplete, need more data
                return (False, expected_total)
            # We have enough data, but make sure we only use exactly content_length bytes
            return (True, expected_total)
        
        # If no Content-Length, we can't know the expected length
        # For requests without Content-Length, body is typically empty (GET, HEAD, etc.)
        # For responses without Content-Length, it might be chunked or connection-close
        # In this case, we'll consider it complete if we have headers
        return (True, None)
    
    def _parse_http_request(self, data: bytes, src_ip: str, dst_ip: str, src_port: int, dst_port: int) -> Optional[Dict]:
        """Parse HTTP request from packet data"""
        try:
            # Look for HTTP methods
            if not (data.startswith(b'GET') or data.startswith(b'POST') or 
                    data.startswith(b'PUT') or data.startswith(b'DELETE') or
                    data.startswith(b'PATCH') or data.startswith(b'HEAD') or
                    data.startswith(b'OPTIONS')):
                # Log why it failed
                if len(data) > 0:
                    first_bytes = data[:20].decode('utf-8', errors='replace')
                    print(f"  🔍 Not an HTTP request (first bytes: {repr(first_bytes)})", file=sys.stderr, flush=True)
                return None
            
            # Note: This check is redundant since _process_tcp_data already checks completeness
            # But we keep it as a safety check
            is_complete, _ = self._is_complete_http_message(data)
            if not is_complete:
                print(f"  ⚠️  Incomplete HTTP message passed to parser (this shouldn't happen)", file=sys.stderr, flush=True)
                return None
            
            print(f"  ✓ HTTP request detected, parsing...", file=sys.stderr, flush=True)
            
            # Parse HTTP request
            lines = data.split(b'\r\n')
            if not lines:
                return None
            
            # Split headers and body (HTTP uses \r\n\r\n separator)
            if b'\r\n\r\n' not in data:
                print(f"  ⚠️  ERROR: No \\r\\n\\r\\n separator found in data (length: {len(data)})", file=sys.stderr, flush=True)
                return None
            
            # Split headers and body at \r\n\r\n
            split_result = data.split(b'\r\n\r\n', 1)
            if len(split_result) < 2:
                print(f"  ❌ ERROR: No \\r\\n\\r\\n separator found in data (length: {len(data)})", file=sys.stderr, flush=True)
                return None
            
            header_data = split_result[0]
            all_body_data = split_result[1]  # Everything after \r\n\r\n
            header_length = len(header_data) + 4  # +4 for \r\n\r\n
            
            print(f"  📐 Header length: {header_length} bytes, Body data available: {len(all_body_data)} bytes", file=sys.stderr, flush=True)
            
            # Parse request line and headers from header_data
            header_lines = header_data.split(b'\r\n')
            if not header_lines:
                return None
            
            request_line = header_lines[0].decode('utf-8', errors='ignore')
            parts = request_line.split()
            if len(parts) < 2:
                return None
            
            method = parts[0]
            path = parts[1]
            version = parts[2] if len(parts) > 2 else 'HTTP/1.1'
            
            # Parse headers
            headers = {}
            content_length = None
            for line in header_lines[1:]:
                if not line:
                    break
                if b':' in line:
                    key, value = line.split(b':', 1)
                    key_str = key.decode('utf-8', errors='ignore').strip()
                    key_lower = key_str.lower()
                    value_str = value.decode('utf-8', errors='ignore').strip()
                    headers[key_str] = value_str
                    
                    # Extract Content-Length while parsing headers
                    if key_lower == 'content-length':
                        try:
                            content_length = int(value_str)
                            print(f"  📏 Content-Length header: {content_length} bytes", file=sys.stderr, flush=True)
                        except ValueError as e:
                            print(f"  ⚠️  WARNING: Could not parse Content-Length '{value_str}': {e}", file=sys.stderr, flush=True)
            
            # Extract request body (respect Content-Length if present)
            request_body = ""
            if content_length is not None:
                # CRITICAL: Take exactly Content-Length bytes from the start of body data
                # This ensures we don't include any trailing data from subsequent requests
                if len(all_body_data) < content_length:
                    print(f"  ❌ CRITICAL: Body data ({len(all_body_data)} bytes) < Content-Length ({content_length} bytes)!", file=sys.stderr, flush=True)
                    print(f"  ❌ Total data: {len(data)} bytes, Expected total: {header_length + content_length} bytes", file=sys.stderr, flush=True)
                    return None
                
                # Extract exactly Content-Length bytes - no more, no less
                body_data = all_body_data[:content_length]
                print(f"  ✅ Extracted exactly {len(body_data)} bytes of body (Content-Length: {content_length})", file=sys.stderr, flush=True)
            else:
                # No Content-Length - use all body data (may be empty or chunked)
                body_data = all_body_data
                print(f"  📦 Extracted {len(body_data)} bytes of body (no Content-Length header)", file=sys.stderr, flush=True)
            
            # Decode body data to string
            if body_data:
                try:
                    request_body = body_data.decode('utf-8', errors='replace')
                    if content_length is not None and len(body_data) != content_length:
                        # UTF-8 decoding might change byte count if there are multi-byte chars, but bytes should match
                        actual_bytes = len(body_data)
                        print(f"  ✓ Request body decoded: {repr(request_body[:200])}... (string length: {len(request_body)}, bytes: {actual_bytes})", file=sys.stderr, flush=True)
                    else:
                        print(f"  ✓ Request body decoded: {repr(request_body[:200])}... (length: {len(request_body)})", file=sys.stderr, flush=True)
                except Exception as e:
                    try:
                        request_body = body_data.decode('latin-1', errors='replace')
                        print(f"  ✓ Request body decoded (latin-1): {repr(request_body[:200])}... (length: {len(request_body)})", file=sys.stderr, flush=True)
                    except Exception as e2:
                        request_body = body_data.hex()  # Fallback to hex for binary data
                        print(f"  ⚠️  Request body converted to hex (binary data?): {str(e)}, {str(e2)}", file=sys.stderr, flush=True)
            else:
                request_body = ""
                print(f"  📭 No body data (expected for {method} requests without body)", file=sys.stderr, flush=True)
            
            host = headers.get('Host', dst_ip)
            
            # Log Host header for debugging
            if host != dst_ip:
                print(f"📋 Host header: '{host}' (dst_ip={dst_ip})", file=sys.stderr, flush=True)
            else:
                print(f"⚠️  No Host header found, using dst_ip: {dst_ip}", file=sys.stderr, flush=True)
            
            if ':' in str(dst_port) and dst_port != 80 and dst_port != 443:
                host = f"{host}:{dst_port}"
            
            # Extract service name from host
            service_name = self._extract_service_name(host, dst_ip)
            
            endpoint_data = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "node": self.node_name,
                "service": service_name,
                "method": method,
                "endpoint": path,
                "full_url": f"http://{host}{path}",
                "host": host,
                "protocol": "HTTP",
                "source_ip": src_ip,
                "source_port": src_port,
                "destination_ip": dst_ip,
                "destination_port": dst_port,
                "request_headers": headers,
                "request_body": request_body,
                "version": version
            }
            
            return endpoint_data
        except Exception as e:
            # Silently fail - not all packets are HTTP
            return None
    
    def _parse_http_response(self, data: bytes, src_ip: str, dst_ip: str, 
                            src_port: int, dst_port: int, connection_key: str) -> Optional[Dict]:
        """Parse HTTP response from packet data"""
        try:
            if not data.startswith(b'HTTP/'):
                if len(data) > 0:
                    first_bytes = data[:20].decode('utf-8', errors='replace')
                    print(f"  🔍 Not an HTTP response (first bytes: {repr(first_bytes)})", file=sys.stderr, flush=True)
                return None
            
            # Check if we have a complete HTTP message before parsing
            is_complete, expected_length = self._is_complete_http_message(data)
            if not is_complete:
                if expected_length:
                    print(f"  ⏳ Incomplete HTTP response, waiting for more data (current={len(data)}, need={expected_length})", file=sys.stderr, flush=True)
                else:
                    print(f"  ⏳ Incomplete HTTP response (no \\r\\n\\r\\n found)", file=sys.stderr, flush=True)
                return None
            
            print(f"  ✓ HTTP response detected, parsing...", file=sys.stderr, flush=True)
            
            # Split headers and body (HTTP uses \r\n\r\n separator)
            if b'\r\n\r\n' in data:
                header_data, body_data = data.split(b'\r\n\r\n', 1)
            else:
                header_data = data
                body_data = b''
            
            # Parse status line and headers from header_data
            header_lines = header_data.split(b'\r\n')
            if not header_lines:
                return None
            
            status_line = header_lines[0].decode('utf-8', errors='ignore')
            parts = status_line.split(maxsplit=2)
            if len(parts) < 2:
                return None
            
            version = parts[0]
            status_code = int(parts[1])
            status_text = parts[2] if len(parts) > 2 else ''
            
            # Parse headers
            headers = {}
            for line in header_lines[1:]:
                if not line:
                    break
                if b':' in line:
                    key, value = line.split(b':', 1)
                    headers[key.decode('utf-8', errors='ignore').strip()] = \
                        value.decode('utf-8', errors='ignore').strip()
            
            # Extract response body (respect Content-Length if present)
            response_body = ""
            content_length = None
            for line in header_lines[1:]:
                if b':' in line:
                    key, value = line.split(b':', 1)
                    key_lower = key.decode('utf-8', errors='ignore').strip().lower()
                    if key_lower == 'content-length':
                        try:
                            content_length = int(value.decode('utf-8', errors='ignore').strip())
                            break
                        except ValueError:
                            pass
            
            if body_data:
                # Only take up to Content-Length bytes if specified
                if content_length is not None:
                    if len(body_data) < content_length:
                        # This shouldn't happen if _is_complete_http_message worked correctly
                        print(f"  ⚠️  WARNING: Response body data ({len(body_data)} bytes) is less than Content-Length ({content_length} bytes)", file=sys.stderr, flush=True)
                    body_data = body_data[:content_length]
                try:
                    response_body = body_data.decode('utf-8', errors='replace')
                except:
                    try:
                        response_body = body_data.decode('latin-1', errors='replace')
                    except:
                        response_body = body_data.hex()  # Fallback to hex for binary data
            
            # Try to match with request if available
            request_info = self.http_connections.get(connection_key, {})
            
            # Extract service name from host (use stored host from request, or extract from IP)
            host = request_info.get("host", dst_ip)
            service_name = request_info.get("service", self._extract_service_name(host, dst_ip))
            
            endpoint_data = {
                "id": str(uuid.uuid4()),
                "type": "response",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "node": self.node_name,
                "service": service_name,
                "method": request_info.get("method", "UNKNOWN"),
                "endpoint": request_info.get("endpoint", "/"),
                "full_url": f"http://{host}{request_info.get('endpoint', '/')}",
                "host": host,
                "protocol": "HTTP",
                "status_code": status_code,
                "status_text": status_text,
                "source_ip": src_ip,
                "source_port": src_port,
                "destination_ip": dst_ip,
                "destination_port": dst_port,
                "response_headers": headers,
                "response_body": response_body,
                "version": version
            }
            
            return endpoint_data
        except Exception as e:
            # Log parsing errors for debugging
            print(f"  ❌ Error parsing HTTP response: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            return None
    
    def _process_tcp_data(self, src_ip: str, src_port: int, dst_ip: str, dst_port: int, data: bytes):
        """Process TCP payload data for HTTP parsing"""
        connection_key = f"{src_ip}:{src_port}-{dst_ip}:{dst_port}"
        reverse_key = f"{dst_ip}:{dst_port}-{src_ip}:{src_port}"
        
        # Accumulate data in TCP stream for reassembly
        # Determine which direction this packet belongs to
        if connection_key in self.tcp_streams:
            stream_key = connection_key
            prev_len = len(self.tcp_streams[stream_key])
            self.tcp_streams[stream_key].extend(data)
            new_len = len(self.tcp_streams[stream_key])
            print(f"📥 Packet received: +{len(data)} bytes (stream now: {new_len} bytes, was {prev_len})", file=sys.stderr, flush=True)
        elif reverse_key in self.tcp_streams:
            stream_key = reverse_key
            prev_len = len(self.tcp_streams[stream_key])
            self.tcp_streams[stream_key].extend(data)
            new_len = len(self.tcp_streams[stream_key])
            print(f"📥 Packet received (reverse): +{len(data)} bytes (stream now: {new_len} bytes, was {prev_len})", file=sys.stderr, flush=True)
        else:
            # New stream, create buffer
            stream_key = connection_key
            self.tcp_streams[stream_key] = bytearray(data)
            print(f"📥 New stream: +{len(data)} bytes (stream now: {len(self.tcp_streams[stream_key])} bytes)", file=sys.stderr, flush=True)
        
        # Update last packet time for this stream
        self.stream_last_packet_time[stream_key] = time.time()
        
        # Get accumulated data
        complete_data = bytes(self.tcp_streams[stream_key])
        
        # CRITICAL: Check if we have complete headers first (must have \r\n\r\n)
        if b'\r\n\r\n' not in complete_data:
            print(f"⏳ Waiting for complete headers (no \\r\\n\\r\\n found yet, have {len(complete_data)} bytes)", file=sys.stderr, flush=True)
            return
        
        # Check if we have a complete HTTP message before parsing
        is_complete, expected_length = self._is_complete_http_message(complete_data)
        
        # Now check if message is complete
        if not is_complete:
            # Incomplete message, wait for more data
            if expected_length:
                print(f"⏳ Incomplete HTTP message, waiting for more data (current={len(complete_data)}, need={expected_length}, missing={expected_length - len(complete_data)} bytes)", file=sys.stderr, flush=True)
                # Show what we have so far
                if b'\r\n\r\n' in complete_data:
                    header_part, body_part = complete_data.split(b'\r\n\r\n', 1)
                    print(f"  📋 Headers: {len(header_part)} bytes, Body so far: {len(body_part)} bytes", file=sys.stderr, flush=True)
            else:
                print(f"⏳ Incomplete HTTP message, waiting for more data (current length={len(complete_data)}, no Content-Length header yet)", file=sys.stderr, flush=True)
            return
        
        # Log message details for debugging
        if len(complete_data) > 0:
            preview = complete_data[:200].decode('utf-8', errors='replace')
            print(f"📄 Attempting to parse message (length={len(complete_data)}): {repr(preview[:100])}...", file=sys.stderr, flush=True)
            
            # Check Content-Length in headers if present
            if b'\r\n\r\n' in complete_data:
                header_part = complete_data.split(b'\r\n\r\n')[0]
                body_part = complete_data.split(b'\r\n\r\n', 1)[1] if len(complete_data.split(b'\r\n\r\n')) > 1 else b''
                header_length = len(header_part) + 4
                header_lines = header_part.split(b'\r\n')
                for line in header_lines[1:]:
                    if not line:  # Empty line
                        break
                    if b'Content-Length:' in line or b'content-length:' in line:
                        cl_val = line.split(b':', 1)[1].strip().decode('utf-8', errors='ignore')
                        try:
                            cl_int = int(cl_val)
                            expected_total = header_length + cl_int
                            print(f"  📏 Content-Length header: {cl_val} bytes", file=sys.stderr, flush=True)
                            print(f"  📏 Header: {header_length} bytes, Body available: {len(body_part)} bytes, Expected total: {expected_total} bytes", file=sys.stderr, flush=True)
                            if len(complete_data) < expected_total:
                                print(f"  ⚠️  WARNING: Message incomplete! Have {len(complete_data)} bytes, need {expected_total} ({expected_total - len(complete_data)} missing)", file=sys.stderr, flush=True)
                        except ValueError:
                            print(f"  📏 Content-Length header: {cl_val} (invalid)", file=sys.stderr, flush=True)
                        break
        
        # Try parsing as HTTP request first
        endpoint = self._parse_http_request(complete_data, src_ip, dst_ip, src_port, dst_port)
        if endpoint:
            method = endpoint.get('method', 'UNKNOWN')
            endpoint_path = endpoint.get('endpoint', '/')
            request_body = endpoint.get('request_body', '')
            
            # CRITICAL: Double-check body length matches Content-Length for POST/PUT/PATCH
            if method in ['POST', 'PUT', 'PATCH']:
                content_length_header = None
                if b'\r\n\r\n' in complete_data:
                    header_part = complete_data.split(b'\r\n\r\n')[0]
                    header_lines = header_part.split(b'\r\n')
                    for line in header_lines[1:]:
                        if not line:
                            break
                        if b'Content-Length:' in line or b'content-length:' in line:
                            try:
                                content_length_header = int(line.split(b':', 1)[1].strip().decode('utf-8', errors='ignore'))
                                break
                            except (ValueError, IndexError):
                                pass
                
                if content_length_header is not None and len(request_body) < content_length_header:
                    print(f"  ❌ VALIDATION FAILED: Request body length ({len(request_body)}) < Content-Length ({content_length_header})", file=sys.stderr, flush=True)
                    print(f"  ❌ Discarding endpoint - will wait for more packets", file=sys.stderr, flush=True)
                    # Don't clear stream - wait for more packets
                    return
            
            print(f"✅ Successfully parsed HTTP REQUEST: {method} {endpoint_path} (service={endpoint.get('service')})", file=sys.stderr, flush=True)
            if request_body:
                print(f"  📦 Captured request body: {repr(request_body[:150])} (length: {len(request_body)})", file=sys.stderr, flush=True)
            else:
                print(f"  📭 No request body (expected for {method} requests)", file=sys.stderr, flush=True)
            self.http_connections[connection_key] = {
                "method": endpoint["method"],
                "endpoint": endpoint["endpoint"],
                "host": endpoint["host"],
                "service": endpoint.get("service", "unknown")
            }
            self.output_queue.put(endpoint)
            # Clear the stream after successful parse
            if connection_key in self.tcp_streams:
                del self.tcp_streams[connection_key]
            if connection_key in self.stream_last_packet_time:
                del self.stream_last_packet_time[connection_key]
            if reverse_key in self.tcp_streams:
                del self.tcp_streams[reverse_key]
            if reverse_key in self.stream_last_packet_time:
                del self.stream_last_packet_time[reverse_key]
            return
        
        # Try parsing as HTTP response
        endpoint = self._parse_http_response(complete_data, src_ip, dst_ip, src_port, dst_port, reverse_key)
        if endpoint:
            print(f"✅ Successfully parsed HTTP RESPONSE: {endpoint.get('method')} {endpoint.get('endpoint')} (status={endpoint.get('status_code')}, service={endpoint.get('service')})", file=sys.stderr, flush=True)
            self.output_queue.put(endpoint)
            # Clear the stream after successful parse
            if connection_key in self.tcp_streams:
                del self.tcp_streams[connection_key]
            if connection_key in self.stream_last_packet_time:
                del self.stream_last_packet_time[connection_key]
            if reverse_key in self.tcp_streams:
                del self.tcp_streams[reverse_key]
            if reverse_key in self.stream_last_packet_time:
                del self.stream_last_packet_time[reverse_key]
            return
    
    def _process_packet_scapy(self, packet):
        """Process packet using scapy"""
        try:
            if not packet.haslayer(IP):
                return
            
            ip_layer = packet[IP]
            src_ip = ip_layer.src
            dst_ip = ip_layer.dst
            
            if packet.haslayer(TCP):
                tcp_layer = packet[TCP]
                src_port = tcp_layer.sport
                dst_port = tcp_layer.dport
                seq = tcp_layer.seq
                
                # Check for HTTP traffic (ports 80, 8080, 8000, etc.)
                http_ports = [80, 443, 8080, 8000, 3000, 5000, 8443, 9000]
                is_http_port = dst_port in http_ports or src_port in http_ports
                
                # Check if this is internal Kubernetes traffic (pod IPs)
                is_pod_traffic = (src_ip.startswith('10.244.') or dst_ip.startswith('10.244.') or 
                                 src_ip.startswith('10.96.') or dst_ip.startswith('10.96.'))
                
                # Debug: Log HTTP port traffic with more detail (especially internal IPs)
                if is_http_port:
                    has_raw = packet.haslayer(Raw)
                    raw_len = len(packet[Raw].load) if has_raw else 0
                    # Log pod traffic (10.244.x.x pod IPs or 10.96.x.x service IPs) very prominently
                    if is_pod_traffic:
                        # For packets with raw data, show a preview of the HTTP request/response
                        preview = ""
                        if has_raw and raw_len > 0:
                            try:
                                raw_data = packet[Raw].load
                                if len(raw_data) > 0:
                                    # Check if it looks like HTTP
                                    if raw_data.startswith(b'GET') or raw_data.startswith(b'POST') or raw_data.startswith(b'PUT') or raw_data.startswith(b'DELETE') or raw_data.startswith(b'HTTP/'):
                                        # Extract first line (request line or status line)
                                        first_line_end = raw_data.find(b'\r\n')
                                        if first_line_end > 0:
                                            preview = f" [{raw_data[:first_line_end].decode('utf-8', errors='replace')[:60]}]"
                            except:
                                pass
                        print(f"*** POD TRAFFIC ***: {src_ip}:{src_port} -> {dst_ip}:{dst_port} (has_raw={has_raw}, raw_len={raw_len}){preview}", file=sys.stderr, flush=True)
                
                if is_http_port:
                    # Always track HTTP port connections for reassembly
                    connection_key = f"{src_ip}:{src_port}-{dst_ip}:{dst_port}"
                    reverse_key = f"{dst_ip}:{dst_port}-{src_ip}:{src_port}"
                    
                    if packet.haslayer(Raw):
                        data = packet[Raw].load
                        if len(data) > 0:
                            # Process TCP data (accumulates and parses when complete)
                            self._process_tcp_data(src_ip, src_port, dst_ip, dst_port, data)
                    else:
                        # TCP packet without Raw layer - might be ACK, or payload is 0 bytes
                        # Still try to track connection for reassembly (some packets might have empty payloads)
                        # Don't do anything here - just log that we saw the packet
                        pass
                                
        except Exception as e:
            # Log errors but continue - not all packets are parseable
            print(f"Error processing packet: {e}", file=sys.stderr, flush=True)
            import traceback
            traceback.print_exc(file=sys.stderr)
            pass
    
    def _capture_raw_socket(self):
        """Fallback packet capture using raw sockets"""
        try:
            # Create raw socket
            s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
            
            print("Starting raw socket capture (requires root privileges)...", file=sys.stderr)
            
            while self.running:
                try:
                    packet, addr = s.recvfrom(65565)
                    
                    # Parse IP header (first 20 bytes)
                    ip_header = struct.unpack('!BBHHHBBH4s4s', packet[:20])
                    src_ip = socket.inet_ntoa(ip_header[8])
                    dst_ip = socket.inet_ntoa(ip_header[9])
                    protocol = ip_header[6]
                    
                    if protocol == 6:  # TCP
                        # Parse TCP header (starts at byte 20)
                        if len(packet) > 40:
                            tcp_header = struct.unpack('!HHLLBBHHH', packet[20:40])
                            src_port = tcp_header[0]
                            dst_port = tcp_header[1]
                            
                            # Extract payload
                            data_offset = (tcp_header[4] >> 4) * 4
                            if len(packet) > 20 + data_offset:
                                data = packet[20 + data_offset:]
                                
                                # Check for HTTP
                                if dst_port in [80, 8080, 8000, 3000, 5000] or src_port in [80, 8080, 8000, 3000, 5000]:
                                    # Process TCP data (accumulates and parses when complete)
                                    self._process_tcp_data(src_ip, src_port, dst_ip, dst_port, data)
                except socket.error:
                    continue
                except Exception as e:
                    print(f"Error processing packet: {e}", file=sys.stderr)
                    continue
        except PermissionError:
            print("ERROR: Raw socket capture requires root privileges", file=sys.stderr)
            print("Please run with CAP_NET_RAW capability or as root", file=sys.stderr)
            sys.exit(1)
    
    def start(self):
        """Start traffic monitoring"""
        print(f"Starting traffic monitor on node: {self.node_name}", file=sys.stderr, flush=True)
        print(f"Output file: {self.output_file}", file=sys.stderr, flush=True)
        print(f"SCAPY_AVAILABLE: {SCAPY_AVAILABLE}", file=sys.stderr, flush=True)
        
        # Initialize output file
        try:
            with open(self.output_file, 'w') as f:
                f.write('')  # Clear/initialize file
            print(f"Initialized output file: {self.output_file}", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"Warning: Could not initialize output file: {e}", file=sys.stderr, flush=True)
        
        if SCAPY_AVAILABLE:
            print("Using scapy for packet capture", file=sys.stderr, flush=True)
            try:
                # Get interface list first
                print("Getting interface list...", file=sys.stderr, flush=True)
                interfaces = get_if_list()
                print(f"Available interfaces: {interfaces}", file=sys.stderr, flush=True)
                
                # Filter for HTTP traffic on common ports (exclude 443 to reduce HTTPS noise)
                filter_str = "tcp and (port 80 or port 8080 or port 8000 or port 3000 or port 5000 or port 8443 or port 9000)"
                print(f"Using filter: {filter_str}", file=sys.stderr, flush=True)
                
                # Collect interfaces to capture on
                capture_interfaces = []
                for iface in interfaces:
                    if iface == 'lo':
                        continue  # Skip loopback
                    # Capture on veth interfaces (pod traffic), eth0 (host), and bridge interfaces
                    # veth* interfaces are critical for pod-to-pod traffic
                    if (iface.startswith('veth') or iface == 'eth0' or 
                        iface.startswith('docker') or iface.startswith('br') or
                        iface.startswith('cni') or iface.startswith('flannel')):
                        capture_interfaces.append(iface)
                
                # If no specific interfaces found, capture on all except loopback
                if not capture_interfaces:
                    capture_interfaces = [iface for iface in interfaces if iface != 'lo']
                
                print(f"Found {len(capture_interfaces)} candidate interfaces: {capture_interfaces}", file=sys.stderr, flush=True)
                
                # Try capturing on all veth interfaces using threads (more reliable than 'any' in K8s)
                # Using threads on multiple interfaces ensures we catch pod-to-pod traffic
                if len(capture_interfaces) > 0:
                    print(f"Starting capture on {len(capture_interfaces)} interfaces using threads", file=sys.stderr, flush=True)
                    def capture_interface(iface):
                        try:
                            print(f"Starting capture on interface: {iface}", file=sys.stderr, flush=True)
                            sniff(iface=iface, prn=self._process_packet_scapy, store=False, 
                                  stop_filter=lambda x: not self.running, filter=filter_str)
                        except Exception as e:
                            print(f"Error capturing on {iface}: {e}", file=sys.stderr, flush=True)
                            import traceback
                            traceback.print_exc(file=sys.stderr)
                    
                    threads = []
                    for iface in capture_interfaces:
                        t = threading.Thread(target=capture_interface, args=(iface,), daemon=True)
                        t.start()
                        threads.append(t)
                        time.sleep(0.5)  # Small delay between thread starts
                    
                    print("All capture threads started, monitoring traffic...", file=sys.stderr, flush=True)
                    
                    # Keep main thread alive
                    while self.running:
                        time.sleep(1)
                    return
                
                # Fallback to 'any' interface if no specific interfaces found
                print("No specific interfaces found, trying 'any' interface...", file=sys.stderr, flush=True)
                try:
                    sniff(iface=None, prn=self._process_packet_scapy, store=False, 
                          stop_filter=lambda x: not self.running, filter=filter_str)
                    return
                except Exception as e:
                    print(f"WARNING: Failed to capture on 'any' interface: {e}", file=sys.stderr, flush=True)
                    print("Falling back to per-interface capture...", file=sys.stderr, flush=True)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    
                    # Fallback to per-interface if 'any' fails
                    if len(capture_interfaces) > 0:
                        def capture_interface(iface):
                            try:
                                print(f"Starting capture on interface: {iface}", file=sys.stderr, flush=True)
                                sniff(iface=iface, prn=self._process_packet_scapy, store=False, 
                                      stop_filter=lambda x: not self.running, filter=filter_str)
                            except Exception as e:
                                print(f"Error capturing on {iface}: {e}", file=sys.stderr, flush=True)
                                import traceback
                                traceback.print_exc(file=sys.stderr)
                        
                        if len(capture_interfaces) == 1:
                            # Single interface - no threading needed
                            print(f"Capturing on single interface: {capture_interfaces[0]}", file=sys.stderr, flush=True)
                            sniff(iface=capture_interfaces[0], prn=self._process_packet_scapy, store=False, 
                                  stop_filter=lambda x: not self.running, filter=filter_str)
                        else:
                            # Multiple interfaces - use threading
                            print(f"Starting capture on {len(capture_interfaces)} interfaces using threads", file=sys.stderr, flush=True)
                            threads = []
                            for iface in capture_interfaces:
                                t = threading.Thread(target=capture_interface, args=(iface,), daemon=True)
                                t.start()
                                threads.append(t)
                                time.sleep(0.5)  # Small delay between thread starts
                            
                            print("All capture threads started, monitoring traffic...", file=sys.stderr, flush=True)
                            
                            # Keep main thread alive
                            while self.running:
                                time.sleep(1)
                    return
            except Exception as e:
                print(f"ERROR with scapy capture: {e}", file=sys.stderr, flush=True)
                import traceback
                traceback.print_exc(file=sys.stderr)
                print("Falling back to raw socket capture", file=sys.stderr, flush=True)
                self._capture_raw_socket()
        else:
            print("Using raw socket capture (scapy not available)", file=sys.stderr, flush=True)
            self._capture_raw_socket()
    
    def stop(self):
        """Stop traffic monitoring"""
        self.running = False

def main():
    # Get node name from environment or hostname
    node_name = os.environ.get('NODE_NAME') or os.environ.get('HOSTNAME', 'unknown-node')
    output_file = os.environ.get('OUTPUT_FILE', '/tmp/endpoints.json')
    
    monitor = TrafficMonitor(output_file=output_file, node_name=node_name)
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        print("\nShutting down...", file=sys.stderr)
        monitor.stop()
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
