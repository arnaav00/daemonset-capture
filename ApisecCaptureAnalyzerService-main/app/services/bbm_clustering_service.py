"""
Black-Box Microservice Boundary Discovery Algorithm (BBM-BDA)
Enhanced clustering service for better microservice detection
"""

import hashlib
import re
import json
import numpy as np
import pandas as pd
from typing import List, Dict, Set, Tuple, Any
from collections import Counter, defaultdict
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.neighbors import NearestNeighbors

from ..services.feature_extractor import FeatureVector
from ..services.clustering_service import ClusterResult
from ..core.config import settings


class BBMClusteringService:
    """
    Black-Box Microservice Boundary Discovery Algorithm (BBM-BDA)
    
    Uses sophisticated feature engineering and DBSCAN clustering to identify
    microservices that share the same domain.
    """
    
    def __init__(self, 
                 max_header_values: int = 10,
                 max_error_signatures: int = 20,
                 min_volume_ratio: float = 0.001):
        """
        Initialize BBM Clustering Service.
        
        Args:
            max_header_values: Maximum unique header values for OHE (N in paper)
            max_error_signatures: Maximum unique error signatures for OHE (K in paper)
            min_volume_ratio: Minimum cluster size ratio for validation
        """
        self.max_header_values = max_header_values
        self.max_error_signatures = max_error_signatures
        self.min_volume_ratio = min_volume_ratio
    
    def cluster_features(self, features: List[FeatureVector]) -> List[ClusterResult]:
        """
        Cluster features using BBM-BDA algorithm.
        
        Args:
            features: List of extracted features
        
        Returns:
            List of validated clusters
        """
        if not features or len(features) < 2:
            # Fallback for small datasets
            if features:
                result = ClusterResult(cluster_id=0, feature_indices=[0])
                result.add_feature(features[0])
                return [result]
            return []
        
        # Phase 1: Feature Extraction (already done by FeatureExtractor)
        # Phase 2: Feature Engineering and Encoding
        feature_matrix, feature_names = self._build_feature_matrix(features)
        
        if feature_matrix.shape[0] < 2:
            result = ClusterResult(cluster_id=0, feature_indices=list(range(len(features))))
            for f in features:
                result.add_feature(f)
            return [result]
        
        # Phase 3: DBSCAN Clustering
        cluster_labels = self._perform_dbscan_clustering(feature_matrix)
        
        # Log noise points (cluster label -1)
        noise_count = sum(1 for label in cluster_labels if label == -1)
        if noise_count > 0:
            print(f"[BBM] ⚠️  {noise_count} captures marked as NOISE by DBSCAN")
            noise_indices = [i for i, label in enumerate(cluster_labels) if label == -1]
            print(f"[BBM] Noise samples:")
            for idx in noise_indices[:10]:  # Show first 10
                url = features[idx]['url_features'].get('path', 'unknown')
                method = features[idx].get('method', 'GET')
                print(f"[BBM]   • {method} {url}")
            if len(noise_indices) > 10:
                print(f"[BBM]   ... and {len(noise_indices) - 10} more")
            
            # Smart noise handling: Group noise by path prefix
            print(f"[BBM] Recovering noise points by grouping similar ones...")
            cluster_labels = self._recover_noise_points(cluster_labels, features)
        
        # Phase 4: Cluster Validation
        clusters = self._build_and_validate_clusters(cluster_labels, features, feature_matrix)
        
        return clusters
    
    def _recover_noise_points(
        self, 
        cluster_labels: np.ndarray, 
        features: List[FeatureVector]
    ) -> np.ndarray:
        """
        Intelligently recover noise points by grouping similar ones.
        
        Strategy:
        1. Group noise points by domain + path prefix
        2. If a group has ≥2 points, create a new cluster
        3. Single outliers get their own cluster (better than losing them)
        
        Args:
            cluster_labels: Original cluster labels (with -1 for noise)
            features: Feature vectors
            
        Returns:
            Updated cluster labels with noise points reassigned
        """
        from collections import defaultdict
        
        # Find noise indices
        noise_indices = [i for i, label in enumerate(cluster_labels) if label == -1]
        
        if not noise_indices:
            return cluster_labels
        
        # Group noise by domain + path prefix
        noise_groups = defaultdict(list)
        for idx in noise_indices:
            domain = features[idx]['url_features'].get('domain', 'unknown')
            path_prefix = self._extract_path_prefix(features[idx]['url_features'])
            key = f"{domain}/{path_prefix}"
            noise_groups[key].append(idx)
        
        # Get the max cluster ID to start assigning new ones
        max_cluster_id = cluster_labels.max() if cluster_labels.max() >= 0 else -1
        next_cluster_id = max_cluster_id + 1
        
        # Create new clusters for noise groups
        new_labels = cluster_labels.copy()
        
        for group_key, indices in noise_groups.items():
            if len(indices) >= 1:  # Include even single points
                # Assign new cluster ID
                for idx in indices:
                    new_labels[idx] = next_cluster_id
                
                print(f"[BBM] ✓ Recovered {len(indices)} noise point(s) as cluster {next_cluster_id} ({group_key})")
                next_cluster_id += 1
        
        recovered_count = sum(1 for label in new_labels if label != -1) - sum(1 for label in cluster_labels if label != -1)
        print(f"[BBM] ✓ Total recovered: {recovered_count} endpoints from noise")
        
        return new_labels
    
    def _extract_path_prefix(self, url_features: Dict) -> str:
        """
        Extract primary path segment following /v1/.
        
        Per BBM-BDA: If URL is /v1/serviceA/resource, extract serviceA.
        """
        path = url_features.get("parameterized_path", "")
        segments = [s for s in path.strip('/').split('/') if s and not s.startswith('{')]
        
        # Skip version segments (v1, v2, etc.)
        filtered = [s for s in segments if s not in ['api', 'v1', 'v2', 'v3', 'v4']]
        
        # Return first meaningful segment
        return filtered[0] if filtered else "root"
    
    def _hash_error_body(self, error_body: Any) -> str:
        """
        Create deterministic signature for error bodies.
        
        Per BBM-BDA: Remove timestamps, UUIDs, stack traces,
        then return SHA-256 hash of normalized structure.
        """
        if not error_body:
            return "no_error"
        
        # Convert to string representation
        if isinstance(error_body, dict):
            body_str = json.dumps(error_body, sort_keys=True)
        else:
            body_str = str(error_body)
        
        # Remove timestamps (ISO 8601, unix timestamps, etc.)
        body_str = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?', 'TIMESTAMP', body_str)
        body_str = re.sub(r'\d{10,13}', 'TIMESTAMP', body_str)
        
        # Remove UUIDs
        body_str = re.sub(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            'UUID',
            body_str,
            flags=re.IGNORECASE
        )
        
        # Remove request IDs and trace IDs
        body_str = re.sub(r'(request_id|trace_id|correlation_id)["\']?\s*[:=]\s*["\']?[a-zA-Z0-9-]+', 'ID', body_str)
        
        # Remove stack traces
        body_str = re.sub(r'at\s+[\w.$<>]+\([^)]+\)', '', body_str)
        body_str = re.sub(r'File\s+"[^"]+",\s+line\s+\d+', '', body_str)
        
        # Create hash
        return hashlib.sha256(body_str.encode()).hexdigest()[:16]
    
    def _build_feature_matrix(self, features: List[FeatureVector]) -> Tuple[np.ndarray, List[str]]:
        """
        Build feature matrix M with OHE encoding and normalization.
        
        Per BBM-BDA (Enhanced): 
        M = [F_domain, F_path, F_server, F_x_powered, F_custom_headers, 
             F_error, F_latency, F_status]
        
        F_domain is the strongest differentiator - different domains almost always
        indicate different microservices.
        """
        n_samples = len(features)
        feature_dict = {
            'domain': [],  # CRITICAL: Domain is strongest differentiator
            'path_prefix': [],
            'server': [],
            'x_powered_by': [],
            'custom_headers': [],
            'error_signature': [],
            'latency_ms': [],
            'status_category': []
        }
        
        # Extract features
        for feature in features:
            # Domain (strongest signal for different microservices)
            domain = feature['url_features'].get('domain', 'unknown')
            feature_dict['domain'].append(domain)
            
            # Path prefix
            path_prefix = self._extract_path_prefix(feature['url_features'])
            feature_dict['path_prefix'].append(path_prefix)
            
            # Server header
            server = feature['header_signature'].get('server', 'unknown')
            feature_dict['server'].append(server)
            
            # X-Powered-By header
            x_powered = feature['header_signature'].get('x_powered_by', 'unknown')
            feature_dict['x_powered_by'].append(x_powered)
            
            # Custom headers fingerprint
            custom_fp = feature['header_signature'].get('header_fingerprint', 'none')
            feature_dict['custom_headers'].append(custom_fp)
            
            # Error signature (only for errors)
            status = feature.get('status_code', 200)
            if status >= 400:
                # Get error body from original capture if available
                error_body = feature.get('response_signature', {}).get('is_json')
                error_sig = self._hash_error_body(error_body)
            else:
                error_sig = 'no_error'
            feature_dict['error_signature'].append(error_sig)
            
            # Latency (will be log-transformed)
            latency = feature.get('duration_ms', 0)
            feature_dict['latency_ms'].append(max(latency, 1))  # Avoid log(0)
            
            # Status category
            if status < 300:
                status_cat = '2xx'
            elif status < 400:
                status_cat = '3xx'
            elif status < 500:
                status_cat = '4xx'
            else:
                status_cat = '5xx'
            feature_dict['status_category'].append(status_cat)
        
        # Create DataFrame for easier manipulation
        df = pd.DataFrame(feature_dict)
        
        # One-Hot Encode categorical features
        categorical_features = []
        feature_names = []
        
        # Domain OHE (MOST IMPORTANT - different domains = different services)
        domain_ohe = self._one_hot_encode_top_n(df['domain'], self.max_header_values)
        categorical_features.append(domain_ohe)
        feature_names.extend([f'domain_{i}' for i in range(domain_ohe.shape[1])])
        
        # Path prefix OHE
        path_ohe = self._one_hot_encode_top_n(df['path_prefix'], self.max_header_values)
        categorical_features.append(path_ohe)
        feature_names.extend([f'path_{i}' for i in range(path_ohe.shape[1])])
        
        # Server OHE
        server_ohe = self._one_hot_encode_top_n(df['server'], self.max_header_values)
        categorical_features.append(server_ohe)
        feature_names.extend([f'server_{i}' for i in range(server_ohe.shape[1])])
        
        # X-Powered-By OHE
        xpowered_ohe = self._one_hot_encode_top_n(df['x_powered_by'], self.max_header_values)
        categorical_features.append(xpowered_ohe)
        feature_names.extend([f'xpowered_{i}' for i in range(xpowered_ohe.shape[1])])
        
        # Custom headers OHE
        custom_ohe = self._one_hot_encode_top_n(df['custom_headers'], self.max_header_values)
        categorical_features.append(custom_ohe)
        feature_names.extend([f'custom_{i}' for i in range(custom_ohe.shape[1])])
        
        # Error signature OHE
        error_ohe = self._one_hot_encode_top_n(df['error_signature'], self.max_error_signatures)
        categorical_features.append(error_ohe)
        feature_names.extend([f'error_{i}' for i in range(error_ohe.shape[1])])
        
        # Status category OHE
        status_ohe = self._one_hot_encode_top_n(df['status_category'], 5)
        categorical_features.append(status_ohe)
        feature_names.extend([f'status_{i}' for i in range(status_ohe.shape[1])])
        
        # Log-transform and normalize latency
        latency_log = np.log1p(df['latency_ms'].values).reshape(-1, 1)
        scaler = StandardScaler()
        latency_normalized = scaler.fit_transform(latency_log)
        feature_names.append('latency_normalized')
        
        # Concatenate all features
        feature_matrix = np.hstack(categorical_features + [latency_normalized])
        
        return feature_matrix, feature_names
    
    def _one_hot_encode_top_n(self, series: pd.Series, top_n: int) -> np.ndarray:
        """
        One-hot encode categorical feature, keeping only top N values.
        Low-frequency values are grouped into 'Other'.
        """
        # Get top N most frequent values
        value_counts = series.value_counts()
        top_values = set(value_counts.head(top_n).index)
        
        # Replace low-frequency values with 'Other'
        series_cleaned = series.apply(lambda x: x if x in top_values else 'Other')
        
        # One-hot encode
        encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        encoded = encoder.fit_transform(series_cleaned.values.reshape(-1, 1))
        
        return encoded
    
    def _perform_dbscan_clustering(self, feature_matrix: np.ndarray) -> np.ndarray:
        """
        Perform DBSCAN clustering with automatic parameter estimation.
        
        Per BBM-BDA:
        - minPts = 2 × dimension of M
        - eps determined via K-NN distance elbow method
        """
        n_samples, n_features = feature_matrix.shape
        
        # Calculate minPts
        min_pts_calculated = 2 * n_features
        min_pts = min(min_pts_calculated, n_samples - 1)
        min_pts = max(min_pts, 2)  # At least 2
        
        # For small datasets, adjust minPts to be more lenient
        if n_samples < 100:
            min_pts = max(2, n_samples // 15)  # More lenient for small datasets
        
        # Estimate eps using K-NN distance plot
        eps = self._estimate_eps(feature_matrix, k=min_pts)
        
        # Perform DBSCAN
        dbscan = DBSCAN(eps=eps, min_samples=min_pts, metric='euclidean')
        cluster_labels = dbscan.fit_predict(feature_matrix)
        
        return cluster_labels
    
    def _estimate_eps(self, feature_matrix: np.ndarray, k: int) -> float:
        """
        Estimate eps parameter using K-NN distance elbow method.
        
        Per BBM-BDA: Find the "elbow" in the sorted k-nearest neighbor distances.
        """
        # Calculate k-nearest neighbor distances
        nbrs = NearestNeighbors(n_neighbors=min(k, feature_matrix.shape[0]-1), metric='euclidean')
        nbrs.fit(feature_matrix)
        distances, _ = nbrs.kneighbors(feature_matrix)
        
        # Get distance to k-th nearest neighbor for each point
        kth_distances = distances[:, -1]
        
        # Sort distances
        sorted_distances = np.sort(kth_distances)
        
        # Handle edge case: all distances are zero (highly sparse features)
        if sorted_distances.max() == 0:
            return 1.0  # Default eps for sparse data
        
        # Find elbow using simple heuristic:
        # Look for point where rate of change increases significantly
        if len(sorted_distances) < 10:
            eps = np.percentile(sorted_distances, 90)
            return max(eps, 0.1)  # Ensure non-zero
        
        # For OHE features, distances tend to be small
        # Use a more aggressive percentile for better clustering
        eps = np.percentile(sorted_distances, 70)
        
        # Ensure eps is not too small or too large
        if eps <= 0:
            eps = 0.5  # Default if percentile returns 0
        eps = max(eps, 0.5)  # Minimum threshold
        eps = min(eps, sorted_distances.max() * 0.7)
        
        return float(eps)
    
    def _build_and_validate_clusters(
        self, 
        cluster_labels: np.ndarray, 
        features: List[FeatureVector],
        feature_matrix: np.ndarray
    ) -> List[ClusterResult]:
        """
        Build clusters and validate them using BBM-BDA heuristics.
        
        Per BBM-BDA validation criteria:
        1. High Volume: Volume > 0.001 × |M|
        2. Header Uniqueness: Unique (Server, X-Powered-By) pairs = 1
        3. Error Uniqueness: Unique error signatures for 5xx = 1
        """
        n_total = len(features)
        min_volume = max(int(n_total * self.min_volume_ratio), 2)
        
        # Group by cluster
        cluster_dict = defaultdict(list)
        for idx, label in enumerate(cluster_labels):
            if label != -1:  # Ignore noise
                cluster_dict[label].append(idx)
        
        # Build and validate clusters
        validated_clusters = []
        
        # Determine max "natural" cluster ID (from DBSCAN)
        # Noise-recovered clusters have IDs > this threshold
        natural_cluster_ids = [label for label in cluster_labels if label >= 0]
        max_natural_id = max(natural_cluster_ids) if natural_cluster_ids else -1
        
        # Calculate the number of clusters that existed before noise recovery
        unique_natural = len(set(label for label in cluster_labels if 0 <= label <= max_natural_id))
        
        for cluster_id, indices in cluster_dict.items():
            # Check if this is a noise-recovered cluster
            is_noise_recovered = cluster_id > max_natural_id
            
            # Criterion 1: High Volume
            # Relax for noise-recovered clusters (accept size 1)
            if not is_noise_recovered and len(indices) < min_volume:
                print(f"[BBM] Cluster {cluster_id} filtered: too small ({len(indices)} < {min_volume})")
                continue
            elif is_noise_recovered and len(indices) < 1:
                # This shouldn't happen, but just in case
                continue
            
            # Extract cluster features
            cluster_features = [features[i] for i in indices]
            
            # Criterion 2: Header Uniqueness
            header_pairs = set()
            for feat in cluster_features:
                server = feat['header_signature'].get('server', 'unknown')
                x_powered = feat['header_signature'].get('x_powered_by', 'unknown')
                header_pairs.add((server, x_powered))
            
            if len(header_pairs) > 1:
                # Multiple different server signatures - likely different services
                # Split this cluster by header signature
                sub_clusters = self._split_cluster_by_headers(cluster_id, indices, cluster_features)
                validated_clusters.extend(sub_clusters)
                continue
            
            # Criterion 3: Error Uniqueness (for clusters with 5xx errors)
            error_sigs_5xx = set()
            has_5xx = False
            for feat in cluster_features:
                status = feat.get('status_code', 200)
                if status >= 500:
                    has_5xx = True
                    error_body = feat.get('response_signature', {}).get('is_json')
                    error_sig = self._hash_error_body(error_body)
                    error_sigs_5xx.add(error_sig)
            
            # If has 5xx errors and multiple error signatures, might be different services
            if has_5xx and len(error_sigs_5xx) > 2:
                # Too diverse in error handling - split or mark with lower confidence
                pass
            
            # Create validated cluster
            result = ClusterResult(cluster_id=cluster_id, feature_indices=indices)
            for feat in cluster_features:
                result.add_feature(feat)
            
            validated_clusters.append(result)
        
        # Sort by size (largest first)
        validated_clusters.sort(key=lambda x: len(x.features), reverse=True)
        
        return validated_clusters
    
    def _split_cluster_by_headers(
        self,
        base_cluster_id: int,
        indices: List[int],
        features: List[FeatureVector]
    ) -> List[ClusterResult]:
        """
        Split a cluster into sub-clusters based on header signatures.
        
        This handles cases where DBSCAN grouped similar but distinct services.
        """
        # Group by header signature
        header_groups = defaultdict(list)
        
        for idx, feat in zip(indices, features):
            server = feat['header_signature'].get('server', 'unknown')
            x_powered = feat['header_signature'].get('x_powered_by', 'unknown')
            key = (server, x_powered)
            header_groups[key].append((idx, feat))
        
        # Create sub-clusters
        sub_clusters = []
        for sub_id, (header_key, items) in enumerate(header_groups.items()):
            if len(items) < 2:
                continue
            
            cluster_id = f"{base_cluster_id}_{sub_id}"
            result = ClusterResult(cluster_id=cluster_id, feature_indices=[i[0] for i in items])
            for _, feat in items:
                result.add_feature(feat)
            
            sub_clusters.append(result)
        
        return sub_clusters


# Singleton instance
_bbm_clustering_service = BBMClusteringService()


def get_bbm_clustering_service() -> BBMClusteringService:
    """Get the BBM clustering service instance"""
    return _bbm_clustering_service

