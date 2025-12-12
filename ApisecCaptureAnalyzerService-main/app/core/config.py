"""Configuration management"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings"""
    
    # API Settings
    api_title: str = "API Security Capture Analyzer Service"
    api_version: str = "1.0.0"
    api_prefix: str = "/v1/bolt"
    
    # Session Settings
    session_ttl_seconds: int = 7200  # 2 hours
    max_captures_per_batch: int = 50
    max_captures_per_session: int = 1000
    
    # Clustering Settings
    clustering_algorithm: str = "bbm"  # "bbm" (recommended) or "simple"
    similarity_threshold: float = 0.70
    min_cluster_size: int = 2
    
    # BBM Algorithm Settings
    bbm_max_header_values: int = 10
    bbm_max_error_signatures: int = 20
    bbm_min_volume_ratio: float = 0.001
    
    # Similarity Weights
    weight_header_signature: float = 0.35
    weight_url_base_path: float = 0.25
    weight_auth_signature: float = 0.20
    weight_error_signature: float = 0.12
    weight_response_schema: float = 0.08
    
    # Storage Settings (placeholders)
    s3_bucket_name: Optional[str] = None
    s3_region: Optional[str] = "us-east-1"
    storage_enabled: bool = False
    
    # External API Integration (for onboarding)
    external_api_url: str = "https://api.dev.apisecapps.com"
    external_api_timeout: int = 30  # seconds
    
    # Development
    debug: bool = False
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

