"""
Enhanced OpenAPI specification generator with comprehensive schema inference
"""

from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
from urllib.parse import urlparse, parse_qs
import json

from ..models.analysis_result import IdentifiedMicroservice, EndpointInfo
from ..models.capture import Capture
from ..services.feature_extractor import FeatureVector
from ..services.clustering_service import ClusterResult
from ..services.schema_inference import get_schema_inferrer


class EnhancedOpenAPIGenerator:
    """
    Generates comprehensive OpenAPI 3.0 specifications with:
    - Query parameters from actual URLs
    - Header parameters from actual requests
    - Request/response body schemas inferred from data
    - Examples from successful executions
    - Complete type information
    """
    
    def __init__(self):
        self.schema_inferrer = get_schema_inferrer()
    
    def generate_spec(
        self,
        microservice: IdentifiedMicroservice,
        cluster: ClusterResult,
        original_captures: List[Capture]
    ) -> Dict[str, Any]:
        """
        Generate comprehensive OpenAPI specification.
        
        Args:
            microservice: Identified microservice
            cluster: Cluster with features
            original_captures: Original capture objects with full data
        
        Returns:
            Complete OpenAPI 3.0 specification
        """
        # Map features to captures
        feature_capture_map = self._map_features_to_captures(cluster.features, original_captures)
        
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": microservice.identified_name,
                "version": "1.0.0",
                "description": f"Auto-generated API specification for {microservice.identified_name}",
                "x-confidence": microservice.confidence_score,
                "x-microservice-id": microservice.microservice_id,
                "x-analysis-metadata": {
                    "total_samples": len(original_captures),
                    "endpoints_identified": len(microservice.endpoints),
                    "generated_from": "API Security Capture Analyzer"
                }
            },
            "servers": [
                {
                    "url": microservice.base_url,
                    "description": "Identified base URL from captured traffic"
                }
            ],
            "paths": {},
            "components": {
                "securitySchemes": self._generate_security_schemes(microservice, original_captures),
                "schemas": {},
                "parameters": {}
            }
        }
        
        # Generate comprehensive paths
        spec["paths"] = self._generate_comprehensive_paths(
            microservice.endpoints,
            cluster.features,
            feature_capture_map
        )
        
        # Add security if applicable
        if microservice.signature.auth_pattern:
            spec["security"] = self._generate_security_requirements(microservice.signature.auth_pattern)
        
        return spec
    
    def _map_features_to_captures(
        self,
        features: List[FeatureVector],
        captures: List[Capture]
    ) -> Dict[int, Capture]:
        """
        Map feature indices to original capture objects.
        
        This assumes features are in same order as captures they were extracted from.
        """
        mapping = {}
        for i, capture in enumerate(captures):
            if i < len(features):
                mapping[i] = capture
        return mapping
    
    def _generate_comprehensive_paths(
        self,
        endpoints: List[EndpointInfo],
        features: List[FeatureVector],
        feature_capture_map: Dict[int, Capture]
    ) -> Dict[str, Any]:
        """Generate comprehensive paths with all parameters and schemas"""
        paths = {}
        
        # Group features by endpoint
        endpoint_features: Dict[str, List[tuple]] = {}
        for i, feature in enumerate(features):
            path = feature["url_features"].get("parameterized_path", "/")
            if path not in endpoint_features:
                endpoint_features[path] = []
            
            # Store (feature, capture) tuple
            capture = feature_capture_map.get(i)
            if capture:
                endpoint_features[path].append((feature, capture))
        
        for endpoint in endpoints:
            path = endpoint.path
            path_item = {}
            
            # Get features and captures for this endpoint
            feature_capture_pairs = endpoint_features.get(path, [])
            
            for method in endpoint.methods:
                # Filter by method
                method_pairs = [
                    (f, c) for f, c in feature_capture_pairs
                    if f.get("method") == method
                ]
                
                if not method_pairs:
                    continue
                
                operation = self._generate_comprehensive_operation(
                    method,
                    path,
                    method_pairs
                )
                path_item[method.lower()] = operation
            
            paths[path] = path_item
        
        return paths
    
    def _generate_comprehensive_operation(
        self,
        method: str,
        path: str,
        feature_capture_pairs: List[tuple]
    ) -> Dict[str, Any]:
        """Generate comprehensive operation with all parameters and examples"""
        
        features = [f for f, _ in feature_capture_pairs]
        captures = [c for _, c in feature_capture_pairs]
        
        # Separate successful vs error responses
        successful_captures = [c for c in captures if 200 <= c.response.status < 300]
        error_captures = [c for c in captures if c.response.status >= 400]
        
        operation = {
            "summary": f"{method} {path}",
            "description": f"Auto-generated from {len(captures)} captured request(s)",
            "operationId": self._generate_operation_id(method, path),
            "parameters": [],
            "responses": {},
            "x-samples": len(captures)
        }
        
        # Extract all parameter types
        # 1. Path parameters
        path_params = self._extract_path_parameters(path, captures)
        operation["parameters"].extend(path_params)
        
        # 2. Query parameters
        query_params = self._extract_query_parameters(captures)
        operation["parameters"].extend(query_params)
        
        # 3. Header parameters
        header_params = self._extract_header_parameters(captures)
        operation["parameters"].extend(header_params)
        
        # 4. Request body (for POST, PUT, PATCH)
        if method in ["POST", "PUT", "PATCH"]:
            request_body = self._generate_comprehensive_request_body(captures, successful_captures)
            if request_body:
                operation["requestBody"] = request_body
        
        # 5. Responses with comprehensive schemas and examples
        operation["responses"] = self._generate_comprehensive_responses(
            captures,
            successful_captures,
            error_captures
        )
        
        # Add tags
        path_parts = [p for p in path.split('/') if p and not p.startswith('{')]
        if path_parts:
            operation["tags"] = [path_parts[0]]
        
        return operation
    
    def _extract_path_parameters(
        self,
        path: str,
        captures: List[Capture]
    ) -> List[Dict[str, Any]]:
        """Extract path parameters with inferred types and examples"""
        import re
        
        parameters = []
        param_pattern = re.compile(r'\{([^}]+)\}')
        matches = param_pattern.findall(path)
        
        for param_name in matches:
            # Collect actual values from captures
            param_values = self._extract_path_param_values(param_name, path, captures)
            
            # Infer type
            param_type = self._infer_parameter_type(param_values)
            
            # Detect format
            param_format = None
            if param_values and param_type == "string":
                param_format = self.schema_inferrer._detect_string_format(param_values[0])
            
            param = {
                "name": param_name,
                "in": "path",
                "required": True,
                "schema": {
                    "type": param_type
                },
                "description": f"Path parameter (inferred from {len(param_values)} sample(s))"
            }
            
            if param_format:
                param["schema"]["format"] = param_format
            
            # Add example from actual data
            if param_values:
                param["example"] = param_values[0]
            
            parameters.append(param)
        
        return parameters
    
    def _extract_path_param_values(
        self,
        param_name: str,
        parameterized_path: str,
        captures: List[Capture]
    ) -> List[Any]:
        """Extract actual values for a path parameter from captures"""
        import re
        
        # Convert {param} to regex capture group
        pattern = parameterized_path
        for match in re.finditer(r'\{([^}]+)\}', pattern):
            pattern = pattern.replace(match.group(0), r'([^/]+)')
        
        pattern = '^' + pattern + '$'
        
        values = []
        for capture in captures:
            # Extract path from URL
            url_path = urlparse(capture.url).path
            
            match = re.match(pattern, url_path)
            if match:
                # Find the index of this parameter
                param_matches = list(re.finditer(r'\{([^}]+)\}', parameterized_path))
                param_index = -1
                for i, m in enumerate(param_matches):
                    if m.group(1) == param_name:
                        param_index = i
                        break
                
                if param_index >= 0 and param_index < len(match.groups()):
                    values.append(match.group(param_index + 1))
        
        return values
    
    def _extract_query_parameters(
        self,
        captures: List[Capture]
    ) -> List[Dict[str, Any]]:
        """Extract query parameters from actual URLs"""
        # Collect all query parameters across all captures
        query_params_data = defaultdict(list)
        
        for capture in captures:
            parsed = urlparse(capture.url)
            if parsed.query:
                params = parse_qs(parsed.query)
                for key, values in params.items():
                    query_params_data[key].extend(values)
        
        parameters = []
        for param_name, values in query_params_data.items():
            # Infer type
            param_type = self._infer_parameter_type(values)
            
            # Count occurrences to determine if required
            occurrence_count = sum(1 for c in captures if param_name in parse_qs(urlparse(c.url).query))
            is_required = occurrence_count / len(captures) > 0.8
            
            param = {
                "name": param_name,
                "in": "query",
                "required": is_required,
                "schema": {
                    "type": param_type
                },
                "description": f"Query parameter (found in {occurrence_count}/{len(captures)} request(s))"
            }
            
            # Add example
            if values:
                param["example"] = values[0]
            
            parameters.append(param)
        
        return parameters
    
    def _extract_header_parameters(
        self,
        captures: List[Capture]
    ) -> List[Dict[str, Any]]:
        """Extract common header parameters"""
        # Collect custom/auth headers (exclude standard HTTP headers)
        standard_headers = {
            'accept', 'accept-encoding', 'accept-language', 'cache-control',
            'connection', 'content-length', 'content-type', 'cookie', 'host',
            'user-agent', 'referer', 'origin'
        }
        
        header_data = defaultdict(lambda: {'values': [], 'count': 0})
        
        for capture in captures:
            for header_name, header_value in capture.request.headers.items():
                header_lower = header_name.lower()
                
                # Skip standard headers
                if header_lower in standard_headers:
                    continue
                
                # Include custom headers and auth headers
                if header_lower.startswith('x-') or 'auth' in header_lower or 'api' in header_lower:
                    header_data[header_name]['values'].append(header_value)
                    header_data[header_name]['count'] += 1
        
        parameters = []
        for header_name, data in header_data.items():
            occurrence_count = data['count']
            is_required = occurrence_count / len(captures) > 0.8
            
            param = {
                "name": header_name,
                "in": "header",
                "required": is_required,
                "schema": {
                    "type": "string"
                },
                "description": f"Header parameter (found in {occurrence_count}/{len(captures)} request(s))"
            }
            
            # Add example (mask sensitive values)
            if data['values']:
                example_value = data['values'][0]
                # Mask tokens/keys for security
                if any(word in header_name.lower() for word in ['auth', 'token', 'key', 'secret']):
                    if len(example_value) > 10:
                        example_value = example_value[:10] + "..."
                param["example"] = example_value
            
            parameters.append(param)
        
        return parameters
    
    def _generate_comprehensive_request_body(
        self,
        all_captures: List[Capture],
        successful_captures: List[Capture]
    ) -> Optional[Dict[str, Any]]:
        """Generate request body schema with examples from successful requests"""
        # Collect request bodies
        bodies = []
        for capture in all_captures:
            if capture.request.body is not None:
                bodies.append(capture.request.body)
        
        if not bodies:
            return None
        
        # Infer schema from all bodies
        schema = self.schema_inferrer.infer_schema(bodies)
        
        # Select best example from successful requests
        successful_bodies = [
            c.request.body for c in successful_captures
            if c.request.body is not None
        ]
        
        example = self.schema_inferrer.select_best_example(
            successful_bodies if successful_bodies else bodies
        )
        
        request_body = {
            "description": "Request body schema inferred from captured data",
            "required": True,
            "content": {
                "application/json": {
                    "schema": schema
                }
            }
        }
        
        if example is not None:
            request_body["content"]["application/json"]["example"] = example
        
        return request_body
    
    def _generate_comprehensive_responses(
        self,
        all_captures: List[Capture],
        successful_captures: List[Capture],
        error_captures: List[Capture]
    ) -> Dict[str, Any]:
        """Generate comprehensive response schemas with examples"""
        responses = {}
        
        # Group captures by status code
        captures_by_status = defaultdict(list)
        for capture in all_captures:
            captures_by_status[capture.response.status].append(capture)
        
        for status_code, captures in captures_by_status.items():
            # Collect response bodies
            bodies = [c.response.body for c in captures if c.response.body is not None]
            
            description = self._get_status_description(status_code)
            
            response = {
                "description": f"{description} (observed {len(captures)} time(s))"
            }
            
            # Generate schema if we have bodies
            if bodies:
                schema = self.schema_inferrer.infer_schema(bodies)
                
                # Select best example
                example = self.schema_inferrer.select_best_example(bodies)
                
                response["content"] = {
                    "application/json": {
                        "schema": schema
                    }
                }
                
                if example is not None:
                    response["content"]["application/json"]["example"] = example
            
            responses[str(status_code)] = response
        
        # Ensure at least a 200 response exists
        if "200" not in responses and not any(200 <= int(code) < 300 for code in responses.keys()):
            responses["200"] = {
                "description": "Successful response"
            }
        
        return responses
    
    def _infer_parameter_type(self, values: List[Any]) -> str:
        """Infer parameter type from actual values"""
        if not values:
            return "string"
        
        # Try to parse as different types
        all_integers = True
        all_numbers = True
        all_booleans = True
        
        for value in values:
            if isinstance(value, str):
                # Try integer
                try:
                    int(value)
                except ValueError:
                    all_integers = False
                
                # Try number
                try:
                    float(value)
                except ValueError:
                    all_numbers = False
                
                # Try boolean
                if value.lower() not in ('true', 'false', '0', '1'):
                    all_booleans = False
            elif isinstance(value, (int, float)):
                all_integers = isinstance(value, int) and all_integers
                all_numbers = all_numbers
                all_booleans = False
            else:
                all_integers = False
                all_numbers = False
                all_booleans = False
        
        if all_integers:
            return "integer"
        if all_numbers:
            return "number"
        if all_booleans:
            return "boolean"
        
        return "string"
    
    def _generate_operation_id(self, method: str, path: str) -> str:
        """Generate operation ID"""
        parts = [p for p in path.split('/') if p and p not in ['api', 'v1', 'v2', 'v3']]
        
        if not parts:
            return method.lower()
        
        operation_name = method.lower()
        for part in parts:
            if part.startswith('{'):
                param_name = part.strip('{}')
                operation_name += 'By' + param_name.title().replace('_', '')
            else:
                operation_name += part.title().replace('_', '').replace('-', '')
        
        return operation_name
    
    def _generate_security_schemes(
        self,
        microservice: IdentifiedMicroservice,
        captures: List[Capture]
    ) -> Dict[str, Any]:
        """Generate security schemes from actual auth patterns"""
        schemes = {}
        
        auth_pattern = microservice.signature.auth_pattern
        
        if not auth_pattern:
            return schemes
        
        # Check actual authorization headers
        auth_headers = set()
        for capture in captures:
            for header_name in capture.request.headers.keys():
                if 'auth' in header_name.lower():
                    auth_headers.add(header_name)
        
        if "Bearer" in auth_pattern or any('bearer' in h.lower() for h in auth_headers):
            schemes["bearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": "Bearer token authentication (detected from captured traffic)"
            }
        
        if "Basic" in auth_pattern:
            schemes["basicAuth"] = {
                "type": "http",
                "scheme": "basic",
                "description": "Basic authentication (detected from captured traffic)"
            }
        
        if "Cookie" in auth_pattern:
            schemes["cookieAuth"] = {
                "type": "apiKey",
                "in": "cookie",
                "name": "session",
                "description": "Cookie-based authentication (detected from captured traffic)"
            }
        
        # Check for API key headers
        api_key_headers = [h for h in auth_headers if 'key' in h.lower() or 'api' in h.lower()]
        if api_key_headers:
            schemes["apiKeyAuth"] = {
                "type": "apiKey",
                "in": "header",
                "name": api_key_headers[0],
                "description": f"API key authentication via {api_key_headers[0]} header"
            }
        
        return schemes
    
    def _generate_security_requirements(self, auth_pattern: str) -> List[Dict[str, List]]:
        """Generate security requirements"""
        requirements = []
        
        if "Bearer" in auth_pattern:
            requirements.append({"bearerAuth": []})
        if "Basic" in auth_pattern:
            requirements.append({"basicAuth": []})
        if "Cookie" in auth_pattern:
            requirements.append({"cookieAuth": []})
        
        return requirements
    
    def _get_status_description(self, status_code: int) -> str:
        """Get description for status code"""
        descriptions = {
            200: "OK",
            201: "Created",
            202: "Accepted",
            204: "No Content",
            400: "Bad Request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not Found",
            422: "Unprocessable Entity",
            429: "Too Many Requests",
            500: "Internal Server Error",
            502: "Bad Gateway",
            503: "Service Unavailable"
        }
        return descriptions.get(status_code, f"HTTP {status_code}")


# Singleton instance
_enhanced_openapi_generator = EnhancedOpenAPIGenerator()


def get_enhanced_openapi_generator() -> EnhancedOpenAPIGenerator:
    """Get enhanced OpenAPI generator instance"""
    return _enhanced_openapi_generator

