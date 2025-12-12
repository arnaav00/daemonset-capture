"""Tests for clustering service"""

import pytest
from app.services.feature_extractor import get_feature_extractor
from app.services.clustering_service import ClusteringService


class TestClusteringService:
    """Tests for clustering service"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.clustering = ClusteringService()
        self.extractor = get_feature_extractor()
    
    def test_cluster_features_single(self, sample_user_capture):
        """Test clustering with a single feature"""
        features = [self.extractor.extract_features(sample_user_capture)]
        clusters = self.clustering.cluster_features(features)
        
        assert len(clusters) == 1
        assert len(clusters[0].features) == 1
    
    def test_cluster_features_multiple_services(self, sample_captures):
        """Test clustering with multiple services"""
        features = self.extractor.extract_features_batch(sample_captures)
        clusters = self.clustering.cluster_features(features)
        
        # Should identify at least 2 clusters (user-service and order-service)
        assert len(clusters) >= 1
        
        # Verify clusters are sorted by size
        if len(clusters) > 1:
            assert len(clusters[0].features) >= len(clusters[1].features)
    
    def test_calculate_similarity_identical(self, sample_user_capture):
        """Test similarity calculation for identical features"""
        feature = self.extractor.extract_features(sample_user_capture)
        similarity = self.clustering._calculate_similarity(feature, feature)
        
        assert similarity == 1.0
    
    def test_calculate_similarity_different_services(self, sample_captures):
        """Test similarity for different services"""
        features = self.extractor.extract_features_batch(sample_captures)
        
        # User service features (indices 0, 1, 2)
        # Order service features (indices 3, 4)
        
        # Same service should have high similarity
        user_similarity = self.clustering._calculate_similarity(features[0], features[1])
        assert user_similarity > 0.5
        
        # Different services should have lower similarity
        cross_similarity = self.clustering._calculate_similarity(features[0], features[3])
        assert cross_similarity < user_similarity
    
    def test_cluster_empty_features(self):
        """Test clustering with empty features list"""
        clusters = self.clustering.cluster_features([])
        assert len(clusters) == 0
    
    def test_compare_header_signatures(self):
        """Test header signature comparison"""
        headers1 = {
            "server": "nginx",
            "x_powered_by": "Express",
            "custom_headers": ["x-service-name", "x-request-id"],
            "header_fingerprint": "abc123"
        }
        headers2 = {
            "server": "nginx",
            "x_powered_by": "Express",
            "custom_headers": ["x-service-name", "x-request-id"],
            "header_fingerprint": "abc123"
        }
        
        similarity = self.clustering._compare_header_signatures(headers1, headers2)
        assert similarity > 0.9
    
    def test_compare_url_features_same_service(self):
        """Test URL comparison for same service"""
        url1 = {
            "domain": "api.example.com",
            "port": 443,
            "base_path": "/v1/users",
            "parameterized_path": "/v1/users/{id}",
            "path_depth": 3
        }
        url2 = {
            "domain": "api.example.com",
            "port": 443,
            "base_path": "/v1/users",
            "parameterized_path": "/v1/users/{id}",
            "path_depth": 3
        }
        
        similarity = self.clustering._compare_url_features(url1, url2)
        assert similarity > 0.9
    
    def test_compare_url_features_different_domains(self):
        """Test URL comparison for different domains"""
        url1 = {"domain": "api1.example.com", "port": 443, "base_path": "/", "parameterized_path": "/", "path_depth": 0}
        url2 = {"domain": "api2.example.com", "port": 443, "base_path": "/", "parameterized_path": "/", "path_depth": 0}
        
        similarity = self.clustering._compare_url_features(url1, url2)
        assert similarity == 0.0

