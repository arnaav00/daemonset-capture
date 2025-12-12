"""Session management endpoints"""

from fastapi import APIRouter, HTTPException, status, Query
from ....models.session import StartSessionRequest, StartSessionResponse, AddCapturesResponse
from ....models.capture import CapturesBatchRequest
from ....models.analysis_result import AnalysisResult
from ....models.onboard import OnboardRequest, OnboardResponse, OnboardType
from ....services.session_manager import get_session_manager
from ....services.analysis_engine import get_analysis_engine
from ....services.onboarding_service import get_onboarding_service

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/start", response_model=StartSessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(request: StartSessionRequest) -> StartSessionResponse:
    """
    Start a new capture session.
    
    Creates a new session that will collect API captures for analysis.
    The session expires after 2 hours if not completed.
    
    **Request Body:**
    - `domain` (optional): The domain being analyzed
    - `metadata` (optional): Additional metadata about the session
    
    **Returns:**
    - `session_id`: Unique identifier for the session
    - `created_at`: Timestamp when session was created
    - `expires_at`: Timestamp when session will expire
    - `status`: Current session status
    """
    session_manager = get_session_manager()
    return session_manager.start_session(request)


@router.post(
    "/{session_id}/captures",
    response_model=AddCapturesResponse,
    status_code=status.HTTP_200_OK
)
async def add_captures(
    session_id: str,
    request: CapturesBatchRequest
) -> AddCapturesResponse:
    """
    Add a batch of captures to an existing session.
    
    Can be called multiple times during a session to incrementally
    add captures. Maximum 50 captures per batch.
    
    **Path Parameters:**
    - `session_id`: The session identifier from start_session
    
    **Request Body:**
    - `captures`: Array of capture objects (max 50)
    
    **Returns:**
    - `session_id`: The session identifier
    - `captures_added`: Number of captures added in this batch
    - `total_captures_in_session`: Total captures accumulated so far
    - `status`: Current session status
    
    **Errors:**
    - 404: Session not found
    - 400: Session expired, completed, or batch size exceeded
    """
    session_manager = get_session_manager()
    return session_manager.add_captures(session_id, request.captures)


@router.post(
    "/{session_id}/analyze",
    response_model=AnalysisResult,
    status_code=status.HTTP_200_OK
)
async def analyze_session(session_id: str) -> AnalysisResult:
    """
    Trigger analysis on a session and return results.
    
    Performs the complete analysis pipeline:
    1. Extracts features from all captures
    2. Clusters captures into microservice groups
    3. Identifies and names microservices
    4. Generates OpenAPI specifications
    5. Stores results
    
    **Path Parameters:**
    - `session_id`: The session identifier from start_session
    
    **Returns:**
    - Complete analysis result with identified microservices
    - Each microservice includes:
      - `microservice_id`: Unique identifier
      - `identified_name`: Generated name for the service
      - `confidence_score`: Confidence in the identification (0-1)
      - `endpoints`: List of identified endpoints with methods
      - `openapi_spec_url`: URL to the generated OpenAPI spec
    
    **Errors:**
    - 404: Session not found
    - 400: Session expired or has no captures
    """
    session_manager = get_session_manager()
    analysis_engine = get_analysis_engine()
    
    # Mark session as analyzing
    session_manager.mark_session_analyzing(session_id)
    
    try:
        # Get session data
        session = session_manager.get_session(session_id)
        
        if not session.captures:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Session has no captures to analyze"
            )
        
        # Run analysis
        result = analysis_engine.analyze(session_id, session.captures)
        
        # Mark session as completed
        session_manager.mark_session_completed(session_id)
        
        return result
    
    except Exception as e:
        # If analysis fails, revert to active status
        # (In production, might want more sophisticated error handling)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )


@router.post(
    "/{session_id}/onboard/{microservice_id}",
    response_model=OnboardResponse,
    status_code=status.HTTP_200_OK
)
async def onboard_microservice(
    session_id: str,
    microservice_id: str,
    request: OnboardRequest,
    onboard_type: OnboardType = Query(..., alias="type", description="Type of onboarding: 'new' or 'update'")
) -> OnboardResponse:
    """
    Onboard a microservice to an external API.
    
    Sends the OpenAPI specification for a specific microservice to an external API
    for further processing (e.g., security scanning, documentation, etc.).
    
    **Path Parameters:**
    - `session_id`: The session identifier from the analysis
    - `microservice_id`: The microservice identifier from analysis results
    
    **Query Parameters:**
    - `type`: Type of onboarding - either "new" (first time) or "update" (re-onboard)
    
    **Request Body:**
    - `api_key`: API key for authenticating with the external API
    
    **Returns:**
    - Success status
    - Microservice details
    - Response from external API
    
    **Errors:**
    - 404: Session or microservice not found
    - 400: External API URL not configured
    - 500: External API call failed
    
    **Example:**
    ```
    POST /api/v1/sessions/{session_id}/onboard/{microservice_id}?type=new
    Body: {"api_key": "your-api-key"}
    ```
    """
    analysis_engine = get_analysis_engine()
    onboarding_service = get_onboarding_service()
    
    # Get the OpenAPI spec for this microservice
    try:
        openapi_spec = analysis_engine.get_openapi_spec(session_id, microservice_id)
        microservice_name = analysis_engine.get_microservice_name(session_id, microservice_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Microservice '{microservice_id}' not found in session '{session_id}'"
        )
    
    # Send to external API
    try:
        external_response = await onboarding_service.onboard_microservice(
            microservice_id=microservice_id,
            microservice_name=microservice_name,
            openapi_spec=openapi_spec,
            onboard_type=onboard_type,
            api_key=request.api_key
        )
        
        return OnboardResponse(
            success=True,
            microservice_id=microservice_id,
            microservice_name=microservice_name,
            onboard_type=onboard_type.value,
            application_id=external_response.get("applicationId"),
            host_urls=external_response.get("hostUrls"),
            application_url=external_response.get("applicationUrl"),
            instances_created=external_response.get("instancesCreated"),
            message=external_response.get("message", "Successfully onboarded microservice to external API")
        )
        
    except ValueError as e:
        error_msg = str(e)
        # Check if it's an authentication error (401)
        if "Authentication failed" in error_msg or "valid Bearer token" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=error_msg
            )
        # Other ValueError exceptions (e.g., missing config)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to onboard microservice: {str(e)}"
        )

