"""OpenAPI specification generator"""

from typing import Dict, Any, List, Set
from ..models.analysis_result import IdentifiedMicroservice, EndpointInfo
from ..services.feature_extractor import FeatureVector
from ..services.clustering_service import ClusterResult


class OpenAPIGenerator:
    """
    Generates OpenAPI 3.0 specifications for identified microservices.
    """
    
    def generate_spec(
        self,
        microservice: IdentifiedMicroservice,
        cluster: ClusterResult
    ) -> Dict[str, Any]:
        """
        Generate OpenAPI specification for a microservice.
        
        Args:
            microservice: Identified microservice
            cluster: Original cluster with features
        
        Returns:
            OpenAPI specification as dictionary
        """
        spec = {
            "openapi": "3.0.0",
            "info": {
                "title": microservice.identified_name,
                "version": "1.0.0",
                "description": f"Auto-generated API specification for {microservice.identified_name}",
                "x-confidence": microservice.confidence_score,
                "x-microservice-id": microservice.microservice_id
            },
            "servers": [
                {
                    "url": microservice.base_url,
                    "description": "Identified base URL"
                }
            ],
            "paths": {},
            "components": {
                "securitySchemes": self._generate_security_schemes(microservice, cluster.features),
                "schemas": {}
            }
        }
        
        # Add paths
        spec["paths"] = self._generate_paths(microservice.endpoints, cluster.features)
        
        # Add security if applicable
        if microservice.signature.auth_pattern:
            spec["security"] = self._generate_security_requirements(microservice.signature.auth_pattern)
        
        return spec
    
    def _generate_paths(
        self,
        endpoints: List[EndpointInfo],
        features: List[FeatureVector]
    ) -> Dict[str, Any]:
        """Generate paths section of OpenAPI spec"""
        paths = {}
        
        # Group features by endpoint
        endpoint_features: Dict[str, List[FeatureVector]] = {}
        for feature in features:
            path = feature["url_features"].get("parameterized_path", "/")
            if path not in endpoint_features:
                endpoint_features[path] = []
            endpoint_features[path].append(feature)
        
        for endpoint in endpoints:
            path = endpoint.path
            path_item = {}
            
            # Get features for this endpoint
            endpoint_feature_list = endpoint_features.get(path, [])
            
            for method in endpoint.methods:
                # Find features with this method
                method_features = [
                    f for f in endpoint_feature_list
                    if f.get("method") == method
                ]
                
                operation = self._generate_operation(method, path, method_features)
                path_item[method.lower()] = operation
            
            paths[path] = path_item
        
        return paths
    
    def _generate_operation(
        self,
        method: str,
        path: str,
        features: List[FeatureVector]
    ) -> Dict[str, Any]:
        """Generate operation object for a method"""
        operation = {
            "summary": f"{method} {path}",
            "operationId": self._generate_operation_id(method, path),
            "parameters": self._extract_parameters(path),
            "responses": self._generate_responses(features)
        }
        
        # Add request body for POST, PUT, PATCH
        if method in ["POST", "PUT", "PATCH"] and features:
            request_body = self._generate_request_body(features)
            if request_body:
                operation["requestBody"] = request_body
        
        # Add tags
        path_parts = [p for p in path.split('/') if p and not p.startswith('{')]
        if path_parts:
            operation["tags"] = [path_parts[0]]
        
        return operation
    
    def _generate_operation_id(self, method: str, path: str) -> str:
        """Generate operation ID"""
        # Convert /api/v1/users/{id} to getUsersById
        parts = [p for p in path.split('/') if p]
        
        # Remove common prefixes
        parts = [p for p in parts if p not in ['api', 'v1', 'v2', 'v3']]
        
        if not parts:
            return method.lower()
        
        # Build operation ID
        operation_name = method.lower()
        for part in parts:
            if part.startswith('{'):
                param_name = part.strip('{}')
                operation_name += 'By' + param_name.title().replace('_', '')
            else:
                operation_name += part.title().replace('_', '')
        
        return operation_name
    
    def _extract_parameters(self, path: str) -> List[Dict[str, Any]]:
        """Extract path parameters from parameterized path"""
        parameters = []
        
        # Find all {param} in path
        import re
        param_pattern = re.compile(r'\{([^}]+)\}')
        matches = param_pattern.findall(path)
        
        for param_name in matches:
            # Determine type based on name
            param_type = "string"
            if param_name in ["id", "user_id", "order_id"]:
                param_type = "integer"
            elif param_name == "uuid":
                param_type = "string"
            
            parameters.append({
                "name": param_name,
                "in": "path",
                "required": True,
                "schema": {
                    "type": param_type
                },
                "description": f"Path parameter: {param_name}"
            })
        
        return parameters
    
    def _generate_responses(self, features: List[FeatureVector]) -> Dict[str, Any]:
        """Generate responses section"""
        responses = {}
        
        # Collect status codes
        status_codes = set()
        for feature in features:
            status_codes.add(feature.get("status_code", 200))
        
        for status_code in sorted(status_codes):
            # Find features with this status
            status_features = [f for f in features if f.get("status_code") == status_code]
            
            description = self._get_status_description(status_code)
            
            response = {
                "description": description
            }
            
            # Add content if JSON response
            if status_features and status_features[0]["response_signature"].get("is_json"):
                response["content"] = {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "description": "Response schema (inferred)"
                        }
                    }
                }
            
            responses[str(status_code)] = response
        
        # Ensure at least a 200 response
        if "200" not in responses:
            responses["200"] = {
                "description": "Successful response"
            }
        
        return responses
    
    def _generate_request_body(self, features: List[FeatureVector]) -> Dict[str, Any]:
        """Generate request body schema"""
        # Check if any features have request bodies
        has_body = any(
            f.get("original_url") and "request" in str(f)
            for f in features
        )
        
        if not has_body:
            return {}
        
        return {
            "description": "Request body",
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "description": "Request schema (inferred)"
                    }
                }
            }
        }
    
    def _generate_security_schemes(
        self,
        microservice: IdentifiedMicroservice,
        features: List[FeatureVector]
    ) -> Dict[str, Any]:
        """Generate security schemes"""
        schemes = {}
        
        auth_pattern = microservice.signature.auth_pattern
        
        if not auth_pattern:
            return schemes
        
        if "Bearer" in auth_pattern:
            schemes["bearerAuth"] = {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT"
            }
        elif "Basic" in auth_pattern:
            schemes["basicAuth"] = {
                "type": "http",
                "scheme": "basic"
            }
        elif "Cookie" in auth_pattern:
            schemes["cookieAuth"] = {
                "type": "apiKey",
                "in": "cookie",
                "name": "session"
            }
        
        # Check for API key
        has_api_key = any(
            f["auth_signature"].get("has_api_key")
            for f in features
        )
        
        if has_api_key:
            schemes["apiKeyAuth"] = {
                "type": "apiKey",
                "in": "header",
                "name": "X-API-Key"
            }
        
        return schemes
    
    def _generate_security_requirements(self, auth_pattern: str) -> List[Dict[str, List]]:
        """Generate security requirements"""
        requirements = []
        
        if "Bearer" in auth_pattern:
            requirements.append({"bearerAuth": []})
        elif "Basic" in auth_pattern:
            requirements.append({"basicAuth": []})
        elif "Cookie" in auth_pattern:
            requirements.append({"cookieAuth": []})
        
        return requirements
    
    def _get_status_description(self, status_code: int) -> str:
        """Get description for status code"""
        descriptions = {
            200: "Successful response",
            201: "Created",
            204: "No content",
            400: "Bad request",
            401: "Unauthorized",
            403: "Forbidden",
            404: "Not found",
            500: "Internal server error"
        }
        return descriptions.get(status_code, f"Response with status {status_code}")


# Singleton instance
_openapi_generator = OpenAPIGenerator()


def get_openapi_generator() -> OpenAPIGenerator:
    """Get the OpenAPI generator instance"""
    return _openapi_generator

