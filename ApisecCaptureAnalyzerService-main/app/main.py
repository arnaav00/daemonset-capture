"""FastAPI application entry point"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .api.v1.endpoints import sessions

# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="""
    API Security Capture Analyzer Service
    
    This service analyzes batched API request-response data from browser plugins
    to identify and group endpoints by microservice.
    
    ## Workflow
    
    1. **Start a session** - POST /api/v1/sessions/start
    2. **Add captures** - POST /api/v1/sessions/{session_id}/captures (can be called multiple times)
    3. **Analyze** - POST /api/v1/sessions/{session_id}/analyze
    
    ## Features
    
    - Multi-signal clustering using header signatures, URL patterns, auth patterns, and more
    - Automatic URL parameterization
    - Microservice identification and naming
    - OpenAPI specification generation
    """,
    debug=settings.debug
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify allowed origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(sessions.router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "status": "operational",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": settings.api_title
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )

