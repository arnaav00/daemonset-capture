"""Clustering service for grouping endpoints into microservices"""

from typing import List, Dict, Set, Any, Tuple
from collections import defaultdict
import numpy as np
from sklearn.cluster import DBSCAN
from ..services.feature_extractor import FeatureVector
from ..utils.similarity import jaccard_similarity, dict_similarity, path_similarity
from ..core.config import settings


class ClusterResult:
    """Result of clustering analysis"""
    
    def __init__(self, cluster_id: int, feature_indices: List[int]):
        self.cluster_id = cluster_id
        self.feature_indices = feature_indices
        self.features: List[FeatureVector] = []
    
    def add_feature(self, feature: FeatureVector):
        self.features.append(feature)


class ClusteringService:
    """
    Service to cluster API captures into microservices based on multi-signal similarity.
    """
    
    def __init__(self):
        self.similarity_threshold = settings.similarity_threshold
        self.weights = {
            "header_signature": settings.weight_header_signature,
            "url_base_path": settings.weight_url_base_path,
            "auth_signature": settings.weight_auth_signature,
            "error_signature": settings.weight_error_signature,
            "response_schema": settings.weight_response_schema
        }
    
    def cluster_features(self, features: List[FeatureVector]) -> List[ClusterResult]:
        """
        Cluster feature vectors into microservice groups.
        
        Args:
            features: List of extracted features
        
        Returns:
            List of cluster results
        """
        if not features:
            return []
        
        if len(features) == 1:
            # Single feature, single cluster
            result = ClusterResult(cluster_id=0, feature_indices=[0])
            result.add_feature(features[0])
            return [result]
        
        # Calculate pairwise similarity matrix
        n = len(features)
        similarity_matrix = np.zeros((n, n))
        
        for i in range(n):
            for j in range(i, n):
                if i == j:
                    similarity_matrix[i][j] = 1.0
                else:
                    sim = self._calculate_similarity(features[i], features[j])
                    similarity_matrix[i][j] = sim
                    similarity_matrix[j][i] = sim
        
        # Convert similarity to distance for DBSCAN
        distance_matrix = 1.0 - similarity_matrix
        
        # Apply DBSCAN clustering
        # eps is the maximum distance between samples to be considered in the same neighborhood
        eps = 1.0 - self.similarity_threshold
        min_samples = max(1, settings.min_cluster_size)
        
        clustering = DBSCAN(
            eps=eps,
            min_samples=min_samples,
            metric='precomputed'
        ).fit(distance_matrix)
        
        # Group by cluster labels
        clusters_dict: Dict[int, List[int]] = defaultdict(list)
        for idx, label in enumerate(clustering.labels_):
            clusters_dict[label].append(idx)
        
        # Create cluster results
        results = []
        for cluster_id, indices in clusters_dict.items():
            result = ClusterResult(cluster_id=cluster_id, feature_indices=indices)
            for idx in indices:
                result.add_feature(features[idx])
            results.append(result)
        
        # Sort by cluster size (largest first)
        results.sort(key=lambda x: len(x.features), reverse=True)
        
        return results
    
    def _calculate_similarity(self, feature1: FeatureVector, feature2: FeatureVector) -> float:
        """
        Calculate weighted similarity between two feature vectors.
        
        Args:
            feature1: First feature vector
            feature2: Second feature vector
        
        Returns:
            Similarity score between 0 and 1
        """
        # 1. Header signature similarity (35%)
        header_sim = self._compare_header_signatures(
            feature1["header_signature"],
            feature2["header_signature"]
        )
        
        # 2. URL base path similarity (25%)
        url_sim = self._compare_url_features(
            feature1["url_features"],
            feature2["url_features"]
        )
        
        # 3. Auth signature similarity (20%)
        auth_sim = self._compare_auth_signatures(
            feature1["auth_signature"],
            feature2["auth_signature"]
        )
        
        # 4. Error signature similarity (12%)
        error_sim = self._compare_error_signatures(
            feature1["error_signature"],
            feature2["error_signature"]
        )
        
        # 5. Response schema similarity (8%)
        response_sim = self._compare_response_signatures(
            feature1["response_signature"],
            feature2["response_signature"]
        )
        
        # Weighted sum
        total_similarity = (
            header_sim * self.weights["header_signature"] +
            url_sim * self.weights["url_base_path"] +
            auth_sim * self.weights["auth_signature"] +
            error_sim * self.weights["error_signature"] +
            response_sim * self.weights["response_schema"]
        )
        
        return total_similarity
    
    def _compare_header_signatures(self, headers1: Dict, headers2: Dict) -> float:
        """Compare header signatures"""
        # Service indicators (X-Service-Name) are the STRONGEST signal
        # If explicitly different, these are definitely different services
        indicators1 = headers1.get("service_indicators", {})
        indicators2 = headers2.get("service_indicators", {})
        
        # Check for explicit X-Service-Name mismatch
        if indicators1 and indicators2:
            # Both have service indicators - compare them
            service_name_1 = indicators1.get("x-service-name", "").lower()
            service_name_2 = indicators2.get("x-service-name", "").lower()
            
            if service_name_1 and service_name_2 and service_name_1 != service_name_2:
                # Explicit different service names - very strong signal of different services
                return 0.0
        
        # Server and powered-by should match
        server_match = 1.0 if headers1.get("server") == headers2.get("server") else 0.0
        powered_by_match = 1.0 if headers1.get("x_powered_by") == headers2.get("x_powered_by") else 0.0
        
        # Custom headers similarity
        custom1 = set(headers1.get("custom_headers", []))
        custom2 = set(headers2.get("custom_headers", []))
        custom_sim = jaccard_similarity(custom1, custom2)
        
        # Header fingerprint match
        fingerprint_match = 1.0 if headers1.get("header_fingerprint") == headers2.get("header_fingerprint") else 0.0
        
        # Service indicators similarity (if not already handled above)
        indicators_sim = dict_similarity(indicators1, indicators2) if indicators1 or indicators2 else 0.5
        
        # Weighted combination
        similarity = (
            server_match * 0.25 +
            powered_by_match * 0.20 +
            custom_sim * 0.25 +
            fingerprint_match * 0.20 +
            indicators_sim * 0.10
        )
        
        return similarity
    
    def _compare_url_features(self, url1: Dict, url2: Dict) -> float:
        """Compare URL features"""
        # Domain must match
        if url1.get("domain") != url2.get("domain"):
            return 0.0
        
        # Port should match
        port_match = 1.0 if url1.get("port") == url2.get("port") else 0.5
        
        # Base path similarity (e.g., /api/v1/users vs /api/v1/orders)
        base_path1 = url1.get("base_path", "/")
        base_path2 = url2.get("base_path", "/")
        base_path_sim = 1.0 if base_path1 == base_path2 else 0.0
        
        # Full pattern similarity (with parameterization)
        pattern1 = url1.get("parameterized_path", "")
        pattern2 = url2.get("parameterized_path", "")
        pattern_sim = path_similarity(pattern1, pattern2)
        
        # Path depth similarity
        depth1 = url1.get("path_depth", 0)
        depth2 = url2.get("path_depth", 0)
        depth_sim = 1.0 - (abs(depth1 - depth2) / max(depth1, depth2, 1))
        
        similarity = (
            port_match * 0.10 +
            base_path_sim * 0.40 +
            pattern_sim * 0.40 +
            depth_sim * 0.10
        )
        
        return similarity
    
    def _compare_auth_signatures(self, auth1: Dict, auth2: Dict) -> float:
        """Compare authentication signatures"""
        # Auth type should match
        type_match = 1.0 if auth1.get("auth_type") == auth2.get("auth_type") else 0.0
        
        # Auth location should match
        location_match = 1.0 if auth1.get("auth_location") == auth2.get("auth_location") else 0.0
        
        # Pattern should match
        pattern_match = 1.0 if auth1.get("auth_pattern") == auth2.get("auth_pattern") else 0.0
        
        # API key presence
        api_key_match = 1.0 if auth1.get("has_api_key") == auth2.get("has_api_key") else 0.5
        
        similarity = (
            type_match * 0.35 +
            location_match * 0.25 +
            pattern_match * 0.30 +
            api_key_match * 0.10
        )
        
        return similarity
    
    def _compare_error_signatures(self, error1: Dict, error2: Dict) -> float:
        """Compare error response signatures"""
        # Error format should be similar
        format_match = 1.0 if error1.get("error_format") == error2.get("error_format") else 0.0
        
        # Error fields similarity
        fields1 = error1.get("error_fields", set())
        fields2 = error2.get("error_fields", set())
        fields_sim = jaccard_similarity(fields1, fields2) if fields1 or fields2 else 0.5
        
        # Status category similarity
        category_match = 1.0 if error1.get("status_category") == error2.get("status_category") else 0.5
        
        similarity = (
            format_match * 0.50 +
            fields_sim * 0.30 +
            category_match * 0.20
        )
        
        return similarity
    
    def _compare_response_signatures(self, response1: Dict, response2: Dict) -> float:
        """Compare response signatures"""
        # Schema hash match (exact structure)
        schema_match = 1.0 if (
            response1.get("schema_hash") == response2.get("schema_hash") and
            response1.get("schema_hash") is not None
        ) else 0.0
        
        # Field names similarity
        fields1 = response1.get("field_names", set())
        fields2 = response2.get("field_names", set())
        fields_sim = jaccard_similarity(fields1, fields2) if fields1 or fields2 else 0.0
        
        # Schema depth similarity
        depth1 = response1.get("schema_depth", 0)
        depth2 = response2.get("schema_depth", 0)
        depth_sim = 1.0 - (abs(depth1 - depth2) / max(depth1, depth2, 1)) if depth1 or depth2 else 0.0
        
        # Common field patterns
        has_id_match = 1.0 if response1.get("has_id_field") == response2.get("has_id_field") else 0.5
        has_ts_match = 1.0 if response1.get("has_timestamps") == response2.get("has_timestamps") else 0.5
        
        similarity = (
            schema_match * 0.30 +
            fields_sim * 0.40 +
            depth_sim * 0.15 +
            has_id_match * 0.075 +
            has_ts_match * 0.075
        )
        
        return similarity


# Singleton instance
_clustering_service = ClusteringService()


def get_clustering_service() -> ClusteringService:
    """Get the clustering service instance"""
    return _clustering_service

