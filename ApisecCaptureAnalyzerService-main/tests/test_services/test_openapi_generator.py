"""Tests for OpenAPI generator"""

import pytest
from app.services.feature_extractor import get_feature_extractor
from app.services.clustering_service import get_clustering_service
from app.services.microservice_identifier import get_microservice_identifier
from app.services.openapi_generator import OpenAPIGenerator


class TestOpenAPIGenerator:
    """Tests for OpenAPI specification generation"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.generator = OpenAPIGenerator()
        self.extractor = get_feature_extractor()
        self.clustering = get_clustering_service()
        self.identifier = get_microservice_identifier()
    
    def test_generate_spec_structure(self, sample_captures):
        """Test that generated spec has correct OpenAPI structure"""
        # Extract features and cluster
        features = self.extractor.extract_features_batch(sample_captures)
        clusters = self.clustering.cluster_features(features)
        microservices = self.identifier.identify_microservices(clusters)
        
        # Generate spec for first microservice
        spec = self.generator.generate_spec(microservices[0], clusters[0])
        
        # Verify OpenAPI structure
        assert spec["openapi"] == "3.0.0"
        assert "info" in spec
        assert "servers" in spec
        assert "paths" in spec
        assert "components" in spec
    
    def test_generate_spec_info_section(self, sample_captures):
        """Test info section generation"""
        features = self.extractor.extract_features_batch(sample_captures)
        clusters = self.clustering.cluster_features(features)
        microservices = self.identifier.identify_microservices(clusters)
        
        spec = self.generator.generate_spec(microservices[0], clusters[0])
        
        info = spec["info"]
        assert "title" in info
        assert "version" in info
        assert "description" in info
        assert info["x-microservice-id"] == microservices[0].microservice_id
    
    def test_generate_paths(self, sample_captures):
        """Test paths generation"""
        features = self.extractor.extract_features_batch(sample_captures)
        clusters = self.clustering.cluster_features(features)
        microservices = self.identifier.identify_microservices(clusters)
        
        spec = self.generator.generate_spec(microservices[0], clusters[0])
        
        assert len(spec["paths"]) > 0
        
        # Check that paths contain operations
        for path, methods in spec["paths"].items():
            assert len(methods) > 0
            for method, operation in methods.items():
                assert "summary" in operation
                assert "responses" in operation
    
    def test_extract_parameters(self):
        """Test parameter extraction from paths"""
        path = "/v1/users/{id}/orders/{order_id}"
        params = self.generator._extract_parameters(path)
        
        assert len(params) == 2
        param_names = [p["name"] for p in params]
        assert "id" in param_names
        assert "order_id" in param_names
        
        # All should be path parameters
        for param in params:
            assert param["in"] == "path"
            assert param["required"] is True
    
    def test_generate_operation_id(self):
        """Test operation ID generation"""
        op_id = self.generator._generate_operation_id("GET", "/api/v1/users/{id}")
        
        assert "get" in op_id.lower()
        assert "users" in op_id.lower()
    
    def test_generate_security_schemes_bearer(self):
        """Test security schemes generation for Bearer auth"""
        from app.models.analysis_result import IdentifiedMicroservice, MicroserviceSignature
        
        microservice = IdentifiedMicroservice(
            microservice_id="test-id",
            identified_name="test-service",
            confidence_score=0.9,
            base_url="https://api.example.com",
            signature=MicroserviceSignature(auth_pattern="Bearer:header"),
            endpoints=[]
        )
        
        schemes = self.generator._generate_security_schemes(microservice, [])
        
        assert "bearerAuth" in schemes
        assert schemes["bearerAuth"]["type"] == "http"
        assert schemes["bearerAuth"]["scheme"] == "bearer"

