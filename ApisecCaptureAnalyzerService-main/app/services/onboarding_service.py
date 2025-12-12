"""Onboarding service for external API integration"""

import httpx
import logging
import yaml
from io import BytesIO
from typing import Optional, Dict, Any, List
from app.core.config import settings
from app.models.onboard import OnboardType

logger = logging.getLogger(__name__)


class OnboardingService:
    """Service to handle onboarding microservices to external API"""
    
    def __init__(self):
        self.external_api_url = settings.external_api_url
        self.timeout = settings.external_api_timeout
    
    async def onboard_microservice(
        self,
        microservice_id: str,
        microservice_name: str,
        openapi_spec: Dict[str, Any],
        onboard_type: OnboardType,
        api_key: str
    ) -> Dict[str, Any]:
        """
        Send OpenAPI specification to external API through two-step process.
        
        Step 1: Upload OpenAPI spec to /v1/applications/oas
        Step 2: Create application instances using returned applicationId and hostUrls
        
        Args:
            microservice_id: Unique identifier for the microservice
            microservice_name: Generated name for the microservice
            openapi_spec: Complete OpenAPI 3.0 specification
            onboard_type: Type of onboarding (new or update)
            api_key: Bearer token for external API authentication
            
        Returns:
            Response containing applicationId, hostUrls, and application URL
            
        Raises:
            ValueError: If external API URL is not configured
            httpx.HTTPError: If external API call fails
        """
        # External API URL now defaults to https://api.dev.apisecapps.com
        # but can be overridden with EXTERNAL_API_URL environment variable
        if not self.external_api_url:
            raise ValueError(
                "External API URL not configured."
            )
        
        logger.info(
            f"Onboarding microservice '{microservice_name}' ({microservice_id}) "
            f"to external API - type: {onboard_type.value}"
        )
        logger.info(f"Using external API: {self.external_api_url}")
        
        # Step 1: Upload OpenAPI specification
        upload_result = await self._upload_openapi_spec(
            microservice_name,
            openapi_spec,
            api_key
        )
        
        if not upload_result:
            raise Exception("Failed to upload OpenAPI specification")
        
        application_id = upload_result.get("applicationId")
        host_urls = upload_result.get("hostUrls", [])
        
        logger.info(
            f"OpenAPI spec uploaded successfully - "
            f"Application ID: {application_id}, Host URLs: {host_urls}"
        )
        
        # Step 2: Create application instances (only for 'new' onboarding)
        if onboard_type == OnboardType.NEW and application_id and host_urls:
            instances_result = await self._create_application_instances(
                application_id,
                host_urls,
                api_key
            )
            
            # Construct application URL
            base_domain = self.external_api_url.replace("api.dev.apisecapps.com", "cst.dev.apisecapps.com")
            base_domain = base_domain.split("/v1")[0]  # Remove /v1 suffix if present
            application_url = f"{base_domain}/application/{application_id}"
            
            return {
                "applicationId": application_id,
                "hostUrls": host_urls,
                "instancesCreated": instances_result.get("success", False),
                "applicationUrl": application_url,
                "message": f"Application created successfully: {application_url}"
            }
        else:
            return {
                "applicationId": application_id,
                "hostUrls": host_urls,
                "message": "OpenAPI specification uploaded successfully"
            }
    
    async def _upload_openapi_spec(
        self,
        application_name: str,
        openapi_spec: Dict[str, Any],
        api_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Upload OpenAPI specification to /v1/applications/oas endpoint.
        
        Args:
            application_name: Name of the application (microservice name)
            openapi_spec: OpenAPI 3.0 specification dictionary
            api_key: Bearer token for authentication
            
        Returns:
            Response containing applicationId and hostUrls
            
        Raises:
            httpx.HTTPError: If upload fails
        """
        try:
            # Serialize OpenAPI spec to YAML
            spec_yaml = yaml.dump(openapi_spec, default_flow_style=False, sort_keys=False)
            spec_bytes = spec_yaml.encode('utf-8')
            
            # Prepare multipart form data
            files = {
                'fileUpload': ('openapi-spec.yaml', BytesIO(spec_bytes), 'application/x-yaml')
            }
            
            data = {
                'applicationName': application_name,
                'origin': 'BROWSER_CAPTURE'
            }
            
            # Prepare headers (no Content-Type for multipart/form-data)
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            
            # Construct upload URL
            upload_url = f"{self.external_api_url.rstrip('/')}/v1/applications/oas"
            
            logger.info(f"Uploading OpenAPI spec to {upload_url}")
            logger.info(f"  Application: {application_name}")
            
            # Send request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    upload_url,
                    files=files,
                    data=data,
                    headers=headers
                )
                response.raise_for_status()
                
                logger.info(f"✓ Successfully uploaded OpenAPI specification")
                logger.info(f"  Response status: {response.status_code}")
                
                # Parse response
                result = response.json()
                
                application_id = result.get('applicationId')
                host_urls = result.get('hostUrls', [])
                
                logger.info(f"  Application ID: {application_id}")
                logger.info(f"  Host URLs: {host_urls}")
                
                return result
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Authentication failed - Invalid API key")
                raise ValueError(
                    "Authentication failed. Please provide a valid Bearer token (API key)."
                )
            logger.error(
                f"HTTP Error uploading OpenAPI spec: {e.response.status_code} - {e.response.text}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error uploading OpenAPI spec: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error uploading OpenAPI spec: {str(e)}")
            raise
    
    async def _create_application_instances(
        self,
        application_id: str,
        host_urls: List[str],
        api_key: str
    ) -> Dict[str, Any]:
        """
        Create application instances using applicationId and hostUrls.
        
        Args:
            application_id: Application ID from upload response
            host_urls: List of host URLs from upload response
            api_key: Bearer token for authentication
            
        Returns:
            Response from instances creation
            
        Raises:
            httpx.HTTPError: If instance creation fails
        """
        try:
            # Prepare payload
            payload = {
                "instanceRequestItems": [
                    {"hostUrl": host_url} for host_url in host_urls
                ]
            }
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            # Construct instances URL
            instances_url = f"{self.external_api_url.rstrip('/')}/v1/applications/{application_id}/instances/batch"
            
            logger.info(f"Creating application instances...")
            logger.info(f"  Instances URL: {instances_url}")
            logger.info(f"  Host URLs: {host_urls}")
            
            # Send request
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    instances_url,
                    json=payload,
                    headers=headers
                )
                response.raise_for_status()
                
                logger.info(f"✓ Successfully created application instances")
                logger.info(f"  Response status: {response.status_code}")
                
                # Parse response
                result = response.json() if response.text else {}
                logger.info(f"  Instance creation response: {result}")
                
                return {
                    "success": True,
                    "response": result
                }
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("Authentication failed during instance creation - Invalid API key")
                raise ValueError(
                    "Authentication failed. Please provide a valid Bearer token (API key)."
                )
            logger.error(
                f"HTTP Error creating instances: {e.response.status_code} - {e.response.text}"
            )
            # Don't raise for other errors - instances creation is not critical, just log the error
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text}"
            }
        except httpx.RequestError as e:
            logger.error(f"Request error creating instances: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Unexpected error creating instances: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


# Singleton instance
_onboarding_service: Optional[OnboardingService] = None


def get_onboarding_service() -> OnboardingService:
    """Get or create the onboarding service singleton"""
    global _onboarding_service
    if _onboarding_service is None:
        _onboarding_service = OnboardingService()
    return _onboarding_service


