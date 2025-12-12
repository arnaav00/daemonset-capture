"""Tests for similarity utilities"""

import pytest
from app.utils.similarity import (
    jaccard_similarity,
    cosine_similarity,
    string_similarity,
    dict_similarity,
    path_similarity
)


class TestJaccardSimilarity:
    """Tests for Jaccard similarity"""
    
    def test_identical_sets(self):
        """Test similarity of identical sets"""
        set1 = {1, 2, 3}
        set2 = {1, 2, 3}
        assert jaccard_similarity(set1, set2) == 1.0
    
    def test_disjoint_sets(self):
        """Test similarity of disjoint sets"""
        set1 = {1, 2, 3}
        set2 = {4, 5, 6}
        assert jaccard_similarity(set1, set2) == 0.0
    
    def test_partial_overlap(self):
        """Test similarity of partially overlapping sets"""
        set1 = {1, 2, 3}
        set2 = {2, 3, 4}
        # Intersection: {2, 3} = 2 elements
        # Union: {1, 2, 3, 4} = 4 elements
        # Similarity: 2/4 = 0.5
        assert jaccard_similarity(set1, set2) == 0.5
    
    def test_empty_sets(self):
        """Test similarity of empty sets"""
        set1 = set()
        set2 = set()
        assert jaccard_similarity(set1, set2) == 1.0


class TestCosineSimilarity:
    """Tests for cosine similarity"""
    
    def test_identical_vectors(self):
        """Test similarity of identical vectors"""
        vec1 = {"a": 1.0, "b": 2.0, "c": 3.0}
        vec2 = {"a": 1.0, "b": 2.0, "c": 3.0}
        similarity = cosine_similarity(vec1, vec2)
        assert abs(similarity - 1.0) < 0.001
    
    def test_orthogonal_vectors(self):
        """Test similarity of orthogonal vectors"""
        vec1 = {"a": 1.0, "b": 0.0}
        vec2 = {"a": 0.0, "b": 1.0}
        assert cosine_similarity(vec1, vec2) == 0.0
    
    def test_empty_vectors(self):
        """Test similarity of empty vectors"""
        vec1 = {}
        vec2 = {}
        assert cosine_similarity(vec1, vec2) == 0.0


class TestStringSimilarity:
    """Tests for string similarity"""
    
    def test_identical_strings(self):
        """Test similarity of identical strings"""
        assert string_similarity("hello", "hello") == 1.0
    
    def test_completely_different(self):
        """Test similarity of completely different strings"""
        # No common characters
        similarity = string_similarity("abc", "xyz")
        assert similarity == 0.0
    
    def test_case_insensitive(self):
        """Test that comparison is case-insensitive"""
        similarity = string_similarity("Hello", "hello")
        assert similarity == 1.0
    
    def test_partial_match(self):
        """Test partial string match"""
        similarity = string_similarity("hello", "help")
        assert 0.0 < similarity < 1.0


class TestDictSimilarity:
    """Tests for dictionary similarity"""
    
    def test_identical_dicts(self):
        """Test similarity of identical dictionaries"""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"a": 1, "b": 2}
        assert dict_similarity(dict1, dict2) == 1.0
    
    def test_different_dicts(self):
        """Test similarity of different dictionaries"""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"c": 3, "d": 4}
        similarity = dict_similarity(dict1, dict2)
        assert similarity < 1.0
    
    def test_partial_overlap(self):
        """Test similarity with partial key overlap"""
        dict1 = {"a": 1, "b": 2}
        dict2 = {"a": 1, "c": 3}
        similarity = dict_similarity(dict1, dict2)
        assert 0.0 < similarity < 1.0


class TestPathSimilarity:
    """Tests for path similarity"""
    
    def test_identical_paths(self):
        """Test similarity of identical paths"""
        path1 = "/api/v1/users/123"
        path2 = "/api/v1/users/123"
        assert path_similarity(path1, path2) == 1.0
    
    def test_parameterized_paths(self):
        """Test similarity of paths with different IDs"""
        path1 = "/api/v1/users/123"
        path2 = "/api/v1/users/456"
        similarity = path_similarity(path1, path2)
        # Should have high similarity since structure is same
        assert similarity > 0.7
    
    def test_different_resources(self):
        """Test similarity of paths to different resources"""
        path1 = "/api/v1/users/123"
        path2 = "/api/v1/orders/456"
        similarity = path_similarity(path1, path2)
        # Should have lower similarity
        assert similarity < 0.8
    
    def test_different_lengths(self):
        """Test similarity of paths with different lengths"""
        path1 = "/api/v1/users"
        path2 = "/api/v1/users/123/orders"
        similarity = path_similarity(path1, path2)
        assert 0.0 < similarity < 1.0
    
    def test_empty_paths(self):
        """Test similarity of root paths"""
        path1 = "/"
        path2 = "/"
        # Both empty, should return something reasonable
        similarity = path_similarity(path1, path2)
        assert similarity >= 0.0

