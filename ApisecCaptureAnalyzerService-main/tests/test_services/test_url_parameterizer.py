"""Tests for URL parameterization service"""

import pytest
from app.services.url_parameterizer import URLParameterizer


class TestURLParameterizer:
    """Tests for URL parameterization"""
    
    def setup_method(self):
        """Setup test fixtures"""
        self.parameterizer = URLParameterizer()
    
    def test_parameterize_numeric_id(self):
        """Test parameterizing numeric IDs"""
        url = "https://api.example.com/v1/users/123"
        base_url, path = self.parameterizer.parameterize_url(url)
        
        assert base_url == "https://api.example.com"
        assert path == "/v1/users/{id}"
    
    def test_parameterize_uuid(self):
        """Test parameterizing UUIDs"""
        url = "https://api.example.com/v1/users/550e8400-e29b-41d4-a716-446655440000"
        base_url, path = self.parameterizer.parameterize_url(url)
        
        assert base_url == "https://api.example.com"
        assert path == "/v1/users/{uuid}"
    
    def test_parameterize_prefixed_id(self):
        """Test parameterizing prefixed IDs"""
        url = "https://api.example.com/v1/orders/ord_abc123"
        base_url, path = self.parameterizer.parameterize_url(url)
        
        assert base_url == "https://api.example.com"
        assert path == "/v1/orders/{ord_id}"
    
    def test_parameterize_static_path(self):
        """Test that static paths are not parameterized"""
        url = "https://api.example.com/v1/users"
        base_url, path = self.parameterizer.parameterize_url(url)
        
        assert base_url == "https://api.example.com"
        assert path == "/v1/users"
    
    def test_parameterize_batch(self):
        """Test batch parameterization"""
        urls = [
            "https://api.example.com/v1/users/123",
            "https://api.example.com/v1/users/456",
            "https://api.example.com/v1/users/789",
        ]
        
        result = self.parameterizer.parameterize_urls_batch(urls)
        
        assert len(result) == 3
        for url in urls:
            base_url, path = result[url]
            assert path == "/v1/users/{id}"
    
    def test_group_by_pattern(self):
        """Test grouping URLs by pattern"""
        urls = [
            "https://api.example.com/v1/users/123",
            "https://api.example.com/v1/users/456",
            "https://api.example.com/v1/orders/ord_abc",
            "https://api.example.com/v1/orders/ord_xyz",
        ]
        
        groups = self.parameterizer.group_by_pattern(urls)
        
        assert len(groups) == 2
        assert any("/users/{id}" in pattern for pattern in groups.keys())
        assert any("/orders/{ord_id}" in pattern for pattern in groups.keys())
    
    def test_parameterize_nested_paths(self):
        """Test parameterizing nested paths"""
        url = "https://api.example.com/v1/users/123/orders/456"
        base_url, path = self.parameterizer.parameterize_url(url)
        
        assert base_url == "https://api.example.com"
        assert "{id}" in path
    
    def test_parameterize_empty_path(self):
        """Test parameterizing root path"""
        url = "https://api.example.com/"
        base_url, path = self.parameterizer.parameterize_url(url)
        
        assert base_url == "https://api.example.com"
        assert path == "/"

