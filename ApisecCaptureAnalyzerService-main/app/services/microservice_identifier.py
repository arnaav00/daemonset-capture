"""Microservice identification and naming service"""

import uuid
from typing import List, Dict, Set, Tuple
from collections import Counter, defaultdict
from ..services.clustering_service import ClusterResult
from ..services.feature_extractor import FeatureVector
from ..models.analysis_result import IdentifiedMicroservice, EndpointInfo, MicroserviceSignature


class MicroserviceIdentifier:
    """
    Service to identify and name microservices from clusters.
    """
    
    def identify_microservices(
        self, 
        clusters: List[ClusterResult]
    ) -> List[IdentifiedMicroservice]:
        """
        Identify microservices from cluster results.
        
        Args:
            clusters: List of cluster results
        
        Returns:
            List of identified microservices
        """
        print(f"[MicroserviceIdentifier] Identifying microservices from {len(clusters)} clusters")
        microservices = []
        
        for i, cluster in enumerate(clusters, 1):
            if not cluster.features:
                continue
            
            print(f"[MicroserviceIdentifier] Cluster {i}: {len(cluster.features)} features")
            
            # Generate unique ID
            microservice_id = f"ms-{uuid.uuid4()}"
            
            # Identify name
            identified_name = self._generate_service_name(cluster.features)
            
            # Calculate confidence
            confidence_score = self._calculate_confidence(cluster.features)
            
            # Extract base URL
            base_url = self._extract_base_url(cluster.features)
            
            # Create signature
            signature = self._create_signature(cluster.features)
            
            # Group endpoints
            endpoints = self._group_endpoints(cluster.features)
            
            microservice = IdentifiedMicroservice(
                microservice_id=microservice_id,
                identified_name=identified_name,
                confidence_score=confidence_score,
                base_url=base_url,
                signature=signature,
                endpoints=endpoints,
                openapi_spec_url=None  # Will be set by storage service
            )
            
            print(f"[MicroserviceIdentifier] → {identified_name}: {base_url} ({len(endpoints)} endpoints)")
            
            microservices.append(microservice)
        
        print(f"[MicroserviceIdentifier] Total microservices identified: {len(microservices)}")
        
        return microservices
    
    def _generate_service_name(self, features: List[FeatureVector]) -> str:
        """
        Generate a descriptive name for the microservice.
        
        Args:
            features: Features in the cluster
        
        Returns:
            Service name
        """
        # Strategy 1: Look for explicit service indicators in headers
        service_names = []
        for feature in features:
            indicators = feature["header_signature"].get("service_indicators", {})
            for key, value in indicators.items():
                if value:
                    service_names.append(value.lower().replace(' ', '-'))
        
        if service_names:
            # Use most common service name
            return Counter(service_names).most_common(1)[0][0]
        
        # Strategy 2: Extract from URL patterns - look for common path prefix
        parameterized_paths = [f["url_features"].get("parameterized_path", "") for f in features]
        
        # Find common prefix across ALL endpoints
        if parameterized_paths:
            all_segments = [p.strip('/').split('/') for p in parameterized_paths if p and p != '/']
            
            if all_segments:
                # Find common prefix shared by all endpoints
                common_prefix = []
                for i in range(min(len(segs) for segs in all_segments)):
                    segment_set = set(segs[i] for segs in all_segments)
                    # If all endpoints share this segment (and it's not a parameter)
                    if len(segment_set) == 1:
                        segment = segment_set.pop()
                        if not segment.startswith('{') and segment not in ['api', 'v1', 'v2', 'v3']:
                            common_prefix.append(segment)
                        else:
                            break
                    else:
                        break
                
                # Use the common prefix if found
                if common_prefix:
                    return f"{common_prefix[0]}-service"
                
                # If no common prefix, but paths are structured, extract first meaningful segment
                # from the most common pattern
                first_segments = [segs[0] for segs in all_segments if segs and not segs[0].startswith('{')]
                if first_segments:
                    # Check if there's a dominant pattern (>50% of endpoints)
                    segment_counts = Counter(first_segments)
                    most_common_segment, count = segment_counts.most_common(1)[0]
                    if count > len(first_segments) * 0.5 and most_common_segment not in ['api', 'v1', 'v2', 'v3']:
                        return f"{most_common_segment}-service"
        
        # Strategy 3: Use domain-based naming
        domains = [f["url_features"].get("domain", "") for f in features]
        if domains and domains[0]:
            domain_parts = domains[0].split('.')
            if len(domain_parts) >= 2:
                # Try subdomain first
                subdomain = domain_parts[0]
                if subdomain not in ['www', 'api']:
                    return f"{subdomain}-service"
                
                # Use primary domain name (e.g., "apisec" from "apisec.ai")
                primary_domain = domain_parts[-2] if len(domain_parts) >= 2 else domain_parts[0]
                if primary_domain:
                    return f"{primary_domain}-service"
        
        # Fallback: Generic name
        return "unknown-service"
    
    def _calculate_confidence(self, features: List[FeatureVector]) -> float:
        """
        Calculate confidence score for the microservice identification.
        
        Args:
            features: Features in the cluster
        
        Returns:
            Confidence score between 0 and 1
        """
        if not features:
            return 0.0
        
        # Factors that increase confidence:
        # 1. Consistent header signatures
        header_fingerprints = [
            f["header_signature"].get("header_fingerprint", "")
            for f in features
        ]
        header_consistency = len(set(header_fingerprints)) / len(features) if features else 0
        header_score = 1.0 - header_consistency  # Lower variety = higher confidence
        
        # 2. Explicit service indicators
        has_service_indicators = any(
            f["header_signature"].get("service_indicators")
            for f in features
        )
        indicator_score = 1.0 if has_service_indicators else 0.5
        
        # 3. Consistent auth patterns
        auth_patterns = [f["auth_signature"].get("auth_pattern", "") for f in features]
        auth_consistency = len(set(auth_patterns)) / len(features) if features else 0
        auth_score = 1.0 - auth_consistency
        
        # 4. Cluster size (larger clusters = more confidence)
        size_score = min(len(features) / 10.0, 1.0)  # Cap at 10 endpoints
        
        # 5. Base URL consistency
        base_urls = [f["url_features"].get("base_url", "") for f in features]
        url_consistency = len(set(base_urls)) / len(features) if features else 0
        url_score = 1.0 - url_consistency
        
        # Weighted combination
        confidence = (
            header_score * 0.30 +
            indicator_score * 0.25 +
            auth_score * 0.20 +
            size_score * 0.15 +
            url_score * 0.10
        )
        
        return round(confidence, 2)
    
    def _extract_base_url(self, features: List[FeatureVector]) -> str:
        """
        Extract the most common base URL (scheme + domain only, no path).
        
        The base URL should be the common root across all endpoints,
        not include any path segments that are specific to individual endpoints.
        """
        if not features:
            return "unknown"
        
        # Get most common base URL (scheme + domain)
        base_urls = [f["url_features"].get("base_url", "") for f in features]
        most_common_base = Counter(base_urls).most_common(1)[0][0]
        
        # Check if there's a truly common path prefix across ALL endpoints
        # (not just the most common individual first segment)
        parameterized_paths = [f["url_features"].get("parameterized_path", "") for f in features]
        
        # Find common prefix across all paths
        if parameterized_paths:
            # Split into segments
            all_segments = [p.strip('/').split('/') for p in parameterized_paths if p and p != '/']
            
            if all_segments:
                # Find common prefix
                common_prefix = []
                for i in range(min(len(segs) for segs in all_segments)):
                    segment_set = set(segs[i] for segs in all_segments)
                    # If all endpoints share this segment (and it's not a parameter)
                    if len(segment_set) == 1:
                        segment = list(segment_set)[0]
                        if not segment.startswith('{'):
                            common_prefix.append(segment)
                        else:
                            break
                    else:
                        break
                
                # Filter out generic prefixes but keep meaningful segments
                meaningful_prefix = [s for s in common_prefix if s not in ['api', 'v1', 'v2', 'v3', 'v4']]
                
                # Add prefix if it exists and is meaningful
                if meaningful_prefix:
                    # Include version prefix if it exists for context
                    version_prefix = [s for s in common_prefix if s in ['v1', 'v2', 'v3', 'v4']]
                    if version_prefix:
                        final_prefix = version_prefix + meaningful_prefix
                    else:
                        final_prefix = meaningful_prefix
                    return f"{most_common_base}/{'/'.join(final_prefix)}"
        
        # No common prefix, return just scheme + domain
        return most_common_base
    
    def _create_signature(self, features: List[FeatureVector]) -> MicroserviceSignature:
        """Create a signature for the microservice"""
        if not features:
            return MicroserviceSignature()
        
        # Most common values
        servers = [f["header_signature"].get("server", "") for f in features if f["header_signature"].get("server")]
        powered_by = [f["header_signature"].get("x_powered_by", "") for f in features if f["header_signature"].get("x_powered_by")]
        auth_patterns = [f["auth_signature"].get("auth_pattern", "") for f in features if f["auth_signature"].get("auth_pattern")]
        
        # Common headers
        all_custom_headers = set()
        for f in features:
            custom = f["header_signature"].get("custom_headers", [])
            all_custom_headers.update(custom)
        
        # Most common response schema
        schema_hashes = [
            f["response_signature"].get("schema_hash")
            for f in features
            if f["response_signature"].get("schema_hash")
        ]
        primary_schema_hash = Counter(schema_hashes).most_common(1)[0][0] if schema_hashes else None
        
        # Error format
        error_formats = [
            f["error_signature"].get("error_format")
            for f in features
            if f["error_signature"].get("error_format")
        ]
        common_error_format = Counter(error_formats).most_common(1)[0][0] if error_formats else None
        
        return MicroserviceSignature(
            primary_response_schema={"hash": primary_schema_hash} if primary_schema_hash else None,
            common_headers={h: "present" for h in list(all_custom_headers)[:10]},  # Top 10
            auth_pattern=Counter(auth_patterns).most_common(1)[0][0] if auth_patterns else None,
            server_signature=f"{Counter(servers).most_common(1)[0][0]}/{Counter(powered_by).most_common(1)[0][0]}" if servers and powered_by else None,
            error_format={"type": common_error_format} if common_error_format else None
        )
    
    def _group_endpoints(self, features: List[FeatureVector]) -> List[EndpointInfo]:
        """
        Group features into endpoint patterns.
        
        Args:
            features: Features to group
        
        Returns:
            List of endpoint information
        """
        # Debug: Show raw URLs before parameterization
        raw_urls = [(f.get("method", "GET"), f["url_features"].get("path", "unknown")) 
                   for f in features]
        unique_raw = set(raw_urls)
        print(f"[MicroserviceIdentifier] Raw endpoints before parameterization: {len(unique_raw)}")
        
        # Group by parameterized path
        endpoint_groups: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: {"methods": set(), "count": 0})
        
        for feature in features:
            path = feature["url_features"].get("parameterized_path", "/")
            method = feature.get("method", "GET")
            
            endpoint_groups[path]["methods"].add(method)
            endpoint_groups[path]["count"] += 1
        
        print(f"[MicroserviceIdentifier] Endpoints after parameterization: {len(endpoint_groups)}")
        
        # Create endpoint info objects
        endpoints = []
        for path, data in endpoint_groups.items():
            endpoint = EndpointInfo(
                path=path,
                methods=sorted(list(data["methods"])),
                sample_count=data["count"]
            )
            endpoints.append(endpoint)
        
        # Sort by sample count (most common first)
        endpoints.sort(key=lambda e: e.sample_count, reverse=True)
        
        # Debug: Show final endpoints
        for ep in endpoints[:10]:  # Show first 10
            methods_str = ','.join(ep.methods)
            print(f"[MicroserviceIdentifier]   • {methods_str:6} {ep.path} (n={ep.sample_count})")
        if len(endpoints) > 10:
            print(f"[MicroserviceIdentifier]   ... and {len(endpoints) - 10} more")
        
        return endpoints


# Singleton instance
_microservice_identifier = MicroserviceIdentifier()


def get_microservice_identifier() -> MicroserviceIdentifier:
    """Get the microservice identifier instance"""
    return _microservice_identifier

