"""Tests for feature extraction service"""

import pytest
from app.services.feature_extractor import FeatureExtractor


class TestFeatureExtractor:
    """Tests for feature extraction"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.extractor = FeatureExtractor()
    
    def test_extract_features_basic(self, sample_user_capture):
        """Test basic feature extraction"""
        features = self.extractor.extract_features(sample_user_capture)
        
        assert "url_features" in features
        assert "header_signature" in features
        assert "auth_signature" in features
        assert "response_signature" in features
        assert "error_signature" in features
    
    def test_extract_url_features(self, sample_user_capture):
        """Test URL feature extraction"""
        features = self.extractor.extract_features(sample_user_capture)
        url_features = features["url_features"]
        
        assert url_features["domain"] == "api.example.com"
        assert url_features["base_url"] == "https://api.example.com"
        assert "{id}" in url_features["parameterized_path"]
        assert url_features["path_depth"] == 3
    
    def test_extract_header_signature(self, sample_user_capture):
        """Test header signature extraction"""
        features = self.extractor.extract_features(sample_user_capture)
        header_sig = features["header_signature"]
        
        assert "custom_headers" in header_sig
        assert "service_indicators" in header_sig
        assert "header_fingerprint" in header_sig
    
    def test_extract_auth_signature_bearer(self, sample_user_capture):
        """Test auth signature extraction for Bearer tokens"""
        features = self.extractor.extract_features(sample_user_capture)
        auth_sig = features["auth_signature"]
        
        assert auth_sig["auth_type"] == "Bearer"
        assert auth_sig["auth_location"] == "header"
        assert "Bearer" in auth_sig["auth_pattern"]
    
    def test_extract_response_signature(self, sample_user_capture):
        """Test response signature extraction"""
        features = self.extractor.extract_features(sample_user_capture)
        response_sig = features["response_signature"]
        
        assert response_sig["is_json"] is True
        assert response_sig["schema_hash"] is not None
        assert response_sig["field_count"] > 0
        assert response_sig["has_id_field"] is True
    
    def test_extract_error_signature(self, sample_user_capture):
        """Test error signature extraction for success responses"""
        features = self.extractor.extract_features(sample_user_capture)
        error_sig = features["error_signature"]
        
        assert error_sig["is_error"] is False
        assert error_sig["status_code"] == 200
        assert error_sig["status_category"] == "2xx"
    
    def test_extract_features_batch(self, sample_captures):
        """Test batch feature extraction"""
        features_list = self.extractor.extract_features_batch(sample_captures)
        
        assert len(features_list) == len(sample_captures)
        for features in features_list:
            assert "url_features" in features
            assert "header_signature" in features

