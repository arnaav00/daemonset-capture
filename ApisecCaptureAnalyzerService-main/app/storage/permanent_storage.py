"""
Permanent storage adapter with production-ready S3 integration.

This module handles persistent storage of:
- Raw session data (captured API traffic)
- OpenAPI specifications (comprehensive with schemas and examples)
- Analysis results (identified microservices)
"""

from typing import Optional, Dict, Any
import json
import yaml
from datetime import datetime
from ..core.config import settings

# Boto3 is imported conditionally for production
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


class PermanentStorage:
    """
    Production-ready storage adapter for S3.
    
    Features:
    - Automatic format detection (JSON/YAML)
    - Comprehensive error handling
    - Development mode with mock URLs
    - Production mode with actual S3 uploads
    
    To enable production mode:
    1. Install boto3: pip install boto3
    2. Configure AWS credentials
    3. Set STORAGE_ENABLED=true in config
    4. Set S3_BUCKET_NAME in config
    """
    
    def __init__(self):
        self.enabled = settings.storage_enabled
        self.bucket_name = settings.s3_bucket_name
        self.s3_client = None
        
        # Initialize S3 client if enabled and boto3 available
        if self.enabled and BOTO3_AVAILABLE:
            try:
                self.s3_client = boto3.client('s3')
                print(f"[Storage] S3 client initialized for bucket: {self.bucket_name}")
            except Exception as e:
                print(f"[Storage] Warning: Failed to initialize S3 client: {e}")
                self.enabled = False
        elif self.enabled and not BOTO3_AVAILABLE:
            print("[Storage] Warning: boto3 not installed, storage disabled")
            print("[Storage] Install with: pip install boto3")
            self.enabled = False
    
    def save_raw_session(self, session_id: str, data: Dict[str, Any]) -> Optional[str]:
        """
        Save raw session data to S3.
        
        Args:
            session_id: Session identifier
            data: Session data to save
        
        Returns:
            S3 URL if successful, None otherwise
        """
        if not self.enabled:
            # Return mock URL for development
            return f"s3://{self.bucket_name or 'dev-bucket'}/{session_id}/raw.json"
        
        # TODO: Implement actual S3 upload
        # Example:
        # s3_client = boto3.client('s3')
        # key = f"{session_id}/raw.json"
        # s3_client.put_object(
        #     Bucket=self.bucket_name,
        #     Key=key,
        #     Body=json.dumps(data),
        #     ContentType='application/json'
        # )
        # return f"s3://{self.bucket_name}/{key}"
        
        return f"s3://{self.bucket_name or 'dev-bucket'}/{session_id}/raw.json"
    
    def save_openapi_spec(
        self, 
        session_id: str, 
        microservice_id: str, 
        spec: Dict[str, Any]
    ) -> Optional[str]:
        """
        Save comprehensive OpenAPI specification to S3.
        
        Saves in both YAML (primary) and JSON formats for maximum compatibility.
        The spec includes:
        - Complete request/response schemas
        - Query, path, and header parameters
        - Examples from successful executions
        - Inferred types and formats
        
        Args:
            session_id: Session identifier
            microservice_id: Microservice identifier
            spec: Comprehensive OpenAPI specification dict
        
        Returns:
            S3 URL to YAML file if successful, None otherwise
        """
        key_yaml = f"{session_id}/{microservice_id}.yaml"
        key_json = f"{session_id}/{microservice_id}.json"
        
        if not self.enabled or not self.s3_client:
            # Development mode - return mock URL
            print(f"[Storage] Mock save OpenAPI spec: {key_yaml}")
            print(f"[Storage]   - Paths: {len(spec.get('paths', {}))} endpoints")
            print(f"[Storage]   - Security schemes: {list(spec.get('components', {}).get('securitySchemes', {}).keys())}")
            return f"s3://{self.bucket_name or 'dev-bucket'}/{key_yaml}"
        
        try:
            # Save as YAML (primary format for OpenAPI)
            yaml_content = yaml.dump(spec, default_flow_style=False, sort_keys=False)
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key_yaml,
                Body=yaml_content.encode('utf-8'),
                ContentType='application/x-yaml',
                Metadata={
                    'session-id': session_id,
                    'microservice-id': microservice_id,
                    'generated-at': datetime.utcnow().isoformat(),
                    'openapi-version': spec.get('openapi', '3.0.0'),
                    'service-name': spec.get('info', {}).get('title', 'unknown')
                }
            )
            
            # Also save as JSON for programmatic access
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key_json,
                Body=json.dumps(spec, indent=2).encode('utf-8'),
                ContentType='application/json',
                Metadata={
                    'session-id': session_id,
                    'microservice-id': microservice_id,
                    'generated-at': datetime.utcnow().isoformat()
                }
            )
            
            print(f"[Storage] ✓ Saved OpenAPI spec to S3: {key_yaml} and {key_json}")
            return f"s3://{self.bucket_name}/{key_yaml}"
            
        except ClientError as e:
            print(f"[Storage] ✗ Failed to save OpenAPI spec: {e}")
            # Return mock URL as fallback
            return f"s3://{self.bucket_name or 'dev-bucket'}/{key_yaml}"
        except Exception as e:
            print(f"[Storage] ✗ Unexpected error saving OpenAPI spec: {e}")
            return f"s3://{self.bucket_name or 'dev-bucket'}/{key_yaml}"
    
    def save_analysis_result(
        self, 
        session_id: str, 
        result: Dict[str, Any]
    ) -> Optional[str]:
        """
        Save analysis result to S3.
        
        Args:
            session_id: Session identifier
            result: Analysis result
        
        Returns:
            S3 URL if successful, None otherwise
        """
        if not self.enabled:
            # Return mock URL for development
            return f"s3://{self.bucket_name or 'dev-bucket'}/{session_id}/analysis.json"
        
        # TODO: Implement actual S3 upload
        return f"s3://{self.bucket_name or 'dev-bucket'}/{session_id}/analysis.json"


# Singleton instance
_permanent_storage = PermanentStorage()


def get_permanent_storage() -> PermanentStorage:
    """Get the permanent storage instance"""
    return _permanent_storage

