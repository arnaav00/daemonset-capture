"""Main analysis engine that orchestrates the entire analysis pipeline"""

from typing import List, Dict, Any
from datetime import datetime
from ..models.capture import Capture
from ..models.analysis_result import AnalysisResult, IdentifiedMicroservice
from ..services.feature_extractor import get_feature_extractor
from ..services.clustering_service import get_clustering_service
from ..services.bbm_clustering_service import get_bbm_clustering_service
from ..services.microservice_identifier import get_microservice_identifier
from ..services.openapi_generator import get_openapi_generator
from ..services.openapi_generator_enhanced import get_enhanced_openapi_generator
from ..storage.permanent_storage import get_permanent_storage
from ..core.config import settings


class AnalysisEngine:
    """
    Main analysis engine that coordinates the entire pipeline:
    1. Feature extraction
    2. Clustering (BBM or Simple algorithm)
    3. Microservice identification
    4. OpenAPI spec generation
    5. Storage
    """
    
    def __init__(self):
        self.feature_extractor = get_feature_extractor()
        
        # Select clustering algorithm based on configuration
        if settings.clustering_algorithm == "bbm":
            self.clustering_service = get_bbm_clustering_service()
        else:
            self.clustering_service = get_clustering_service()
        
        self.identifier = get_microservice_identifier()
        
        # Use enhanced OpenAPI generator with comprehensive schema inference
        self.openapi_generator = get_enhanced_openapi_generator()
        
        self.storage = get_permanent_storage()
        
        # In-memory cache for OpenAPI specs (for onboarding)
        # Structure: {session_id: {microservice_id: {"spec": {...}, "name": "..."}}}
        self._openapi_cache: Dict[str, Dict[str, Dict[str, Any]]] = {}
    
    def analyze(self, session_id: str, captures: List[Capture]) -> AnalysisResult:
        """
        Run complete analysis on a set of captures.
        
        Args:
            session_id: Session identifier
            captures: List of captures to analyze
        
        Returns:
            Complete analysis result
        """
        if not captures:
            return AnalysisResult(
                session_id=session_id,
                analysis_timestamp=datetime.utcnow(),
                total_captures_analyzed=0,
                microservices_identified=0,
                microservices=[],
                raw_data_url=None
            )
        
        # Step 1: Extract features from all captures
        features = self.feature_extractor.extract_features_batch(captures)
        
        # Step 2: Cluster features into microservice groups
        clusters = self.clustering_service.cluster_features(features)
        
        # Step 3: Identify microservices from clusters
        microservices = self.identifier.identify_microservices(clusters)
        
        # Initialize cache for this session
        if session_id not in self._openapi_cache:
            self._openapi_cache[session_id] = {}
        
        # Step 4: Generate comprehensive OpenAPI specs and store
        for i, microservice in enumerate(microservices):
            # Get captures for this cluster
            cluster_capture_indices = clusters[i].feature_indices
            cluster_captures = [captures[idx] for idx in cluster_capture_indices if idx < len(captures)]
            
            # Generate comprehensive OpenAPI spec with schema inference
            openapi_spec = self.openapi_generator.generate_spec(
                microservice,
                clusters[i],
                cluster_captures  # Pass original captures for comprehensive analysis
            )
            
            # Cache the OpenAPI spec and microservice name for onboarding
            self._openapi_cache[session_id][microservice.microservice_id] = {
                "spec": openapi_spec,
                "name": microservice.identified_name
            }
            
            # Save OpenAPI spec to storage (S3 placeholder - production ready)
            spec_url = self.storage.save_openapi_spec(
                session_id,
                microservice.microservice_id,
                openapi_spec
            )
            # Note: openapi_spec_url removed from model, stored only internally
        
        # Step 5: Save raw session data
        raw_data_url = self.storage.save_raw_session(
            session_id,
            {
                "session_id": session_id,
                "total_captures": len(captures),
                "captures": [
                    {
                        "url": c.url,
                        "method": c.method,
                        "status": c.response.status,
                        "timestamp": c.timestamp.isoformat() if c.timestamp else None
                    }
                    for c in captures
                ]
            }
        )
        
        # Step 6: Create and save analysis result
        result = AnalysisResult(
            session_id=session_id,
            analysis_timestamp=datetime.utcnow(),
            total_captures_analyzed=len(captures),
            microservices_identified=len(microservices),
            microservices=microservices,
            raw_data_url=raw_data_url
        )
        
        # Save analysis result
        self.storage.save_analysis_result(
            session_id,
            result.model_dump()
        )
        
        return result
    
    def get_openapi_spec(self, session_id: str, microservice_id: str) -> Dict[str, Any]:
        """
        Retrieve the OpenAPI specification for a specific microservice.
        
        Args:
            session_id: Session identifier
            microservice_id: Microservice identifier
            
        Returns:
            Complete OpenAPI 3.0 specification
            
        Raises:
            KeyError: If session or microservice not found
        """
        if session_id not in self._openapi_cache:
            raise KeyError(f"Session '{session_id}' not found or not analyzed")
        
        if microservice_id not in self._openapi_cache[session_id]:
            raise KeyError(
                f"Microservice '{microservice_id}' not found in session '{session_id}'"
            )
        
        return self._openapi_cache[session_id][microservice_id]["spec"]
    
    def get_microservice_name(self, session_id: str, microservice_id: str) -> str:
        """
        Retrieve the name of a specific microservice.
        
        Args:
            session_id: Session identifier
            microservice_id: Microservice identifier
            
        Returns:
            Microservice name
            
        Raises:
            KeyError: If session or microservice not found
        """
        if session_id not in self._openapi_cache:
            raise KeyError(f"Session '{session_id}' not found or not analyzed")
        
        if microservice_id not in self._openapi_cache[session_id]:
            raise KeyError(
                f"Microservice '{microservice_id}' not found in session '{session_id}'"
            )
        
        return self._openapi_cache[session_id][microservice_id]["name"]


# Singleton instance
_analysis_engine = AnalysisEngine()


def get_analysis_engine() -> AnalysisEngine:
    """Get the analysis engine instance"""
    return _analysis_engine

