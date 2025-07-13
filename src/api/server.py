"""
FastAPI server for Sources Sought AI system.
Provides REST API endpoints for web application and external integrations.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from ..core.config import config
from ..utils.logger import get_logger
from ..utils.search import search_engine
from ..utils.task_tracker import task_tracker, create_task, get_task_status
from ..agents.opportunity_finder import OpportunityFinderAgent
from ..agents.analyzer import AnalyzerAgent
from ..agents.response_generator import ResponseGeneratorAgent
from ..agents.relationship_manager import RelationshipManagerAgent
from ..agents.email_manager import EmailManagerAgent
from ..agents.human_loop import HumanInTheLoopAgent
from ..utils.csv_processor import process_sam_csv

# Initialize FastAPI app
app = FastAPI(
    title="Sources Sought AI API",
    description="REST API for the Sources Sought AI automation system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://sources-sought-ai.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security
security = HTTPBearer()
logger = get_logger("api_server")

# Initialize agents
agents = {
    "opportunity_finder": OpportunityFinderAgent(),
    "analyzer": AnalyzerAgent(),
    "response_generator": ResponseGeneratorAgent(),
    "relationship_manager": RelationshipManagerAgent(),
    "email_manager": EmailManagerAgent(),
    "human_loop": HumanInTheLoopAgent()
}


# Pydantic models
class OpportunitySearch(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None
    limit: int = Field(default=10, ge=1, le=100)


class ContactSearch(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None
    limit: int = Field(default=10, ge=1, le=100)


class ResponseGenerationRequest(BaseModel):
    opportunity_id: str
    template_type: str = "professional_services"
    custom_sections: Optional[Dict[str, str]] = None


class AnalysisRequest(BaseModel):
    opportunity_id: str
    company_profile: Optional[Dict[str, Any]] = None


class EmailRequest(BaseModel):
    to_email: str
    template_type: str
    template_data: Dict[str, Any]
    opportunity_id: Optional[str] = None


# Authentication dependency
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validate JWT token and return user info"""
    try:
        import jwt
        from jwt.exceptions import InvalidTokenError
        
        token = credentials.credentials
        
        # Get JWT secret from config
        jwt_secret = config.security.jwt_secret or "your-jwt-secret-key"
        jwt_algorithm = config.security.jwt_algorithm or "HS256"
        
        # Decode and validate token
        payload = jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
        
        user_id = payload.get("sub")
        email = payload.get("email") 
        name = payload.get("name")
        
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user ID")
        
        # Verify user is authorized (check against allowed domains if configured)
        if config.security.allowed_email_domains:
            email_domain = email.split("@")[1] if email and "@" in email else ""
            allowed_domains = config.security.allowed_email_domains.split(",")
            
            if email_domain not in allowed_domains:
                raise HTTPException(status_code=403, detail="Unauthorized email domain")
        
        return {
            "user_id": user_id,
            "email": email,
            "name": name,
            "authenticated_at": datetime.utcnow().isoformat()
        }
        
    except InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for load balancers"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


# Search endpoints
@app.post("/api/search/opportunities")
async def search_opportunities(
    request: OpportunitySearch,
    user: dict = Depends(get_current_user)
):
    """Search for Sources Sought opportunities"""
    try:
        results = await search_engine.search_opportunities(
            query=request.query,
            filters=request.filters,
            top_k=request.limit
        )
        
        return {
            "results": results,
            "total": len(results),
            "query": request.query
        }
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search/contacts")
async def search_contacts(
    request: ContactSearch,
    user: dict = Depends(get_current_user)
):
    """Search for government contacts"""
    try:
        results = await search_engine.search_contacts(
            query=request.query,
            filters=request.filters,
            top_k=request.limit
        )
        
        return {
            "results": results,
            "total": len(results),
            "query": request.query
        }
    except Exception as e:
        logger.error(f"Contact search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/search/all")
async def search_all(
    request: OpportunitySearch,
    user: dict = Depends(get_current_user)
):
    """Search across all content types"""
    try:
        results = await search_engine.search_all(
            query=request.query,
            filters=request.filters,
            top_k=request.limit
        )
        
        return results
    except Exception as e:
        logger.error(f"Global search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Agent endpoints
@app.post("/api/analyze/opportunity")
async def analyze_opportunity(
    request: AnalysisRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """Analyze a Sources Sought opportunity"""
    try:
        analyzer = agents["analyzer"]
        
        task_data = {
            "opportunity_id": request.opportunity_id,
            "company_profile": request.company_profile or {},
            "user_id": user["user_id"]
        }
        
        # Create tracked task
        task_id = await create_task(
            task_type="opportunity_analysis",
            task_data=task_data,
            user_id=user["user_id"]
        )
        
        # Define tracked task execution
        async def tracked_analysis():
            try:
                await task_tracker.start_task(task_id)
                await task_tracker.update_progress(task_id, 10, "Starting opportunity analysis...")
                
                result = await analyzer.execute(task_data)
                
                await task_tracker.complete_task(task_id, result)
            except Exception as e:
                await task_tracker.fail_task(task_id, str(e))
                raise
        
        # Run tracked analysis in background
        background_tasks.add_task(tracked_analysis)
        
        return {
            "status": "analysis_started",
            "task_id": task_id,
            "opportunity_id": request.opportunity_id,
            "message": "Analysis started in background. Check status for updates."
        }
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate/response")
async def generate_response(
    request: ResponseGenerationRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """Generate a Sources Sought response"""
    try:
        generator = agents["response_generator"]
        
        task_data = {
            "opportunity_id": request.opportunity_id,
            "template_type": request.template_type,
            "custom_sections": request.custom_sections or {},
            "user_id": user["user_id"]
        }
        
        # Create tracked task
        task_id = await create_task(
            task_type="response_generation",
            task_data=task_data,
            user_id=user["user_id"]
        )
        
        # Define tracked task execution
        async def tracked_generation():
            try:
                await task_tracker.start_task(task_id)
                await task_tracker.update_progress(task_id, 10, "Starting response generation...")
                
                result = await generator.execute(task_data)
                
                await task_tracker.complete_task(task_id, result)
            except Exception as e:
                await task_tracker.fail_task(task_id, str(e))
                raise
        
        # Run tracked generation in background
        background_tasks.add_task(tracked_generation)
        
        return {
            "status": "generation_started",
            "task_id": task_id,
            "opportunity_id": request.opportunity_id,
            "template_type": request.template_type,
            "message": "Response generation started. Check status for updates."
        }
    except Exception as e:
        logger.error(f"Response generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email/send")
async def send_email(
    request: EmailRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """Send an email using templates"""
    try:
        email_manager = agents["email_manager"]
        
        task_data = {
            "action": "send_email",
            "to_email": request.to_email,
            "template_type": request.template_type,
            "template_data": request.template_data,
            "opportunity_id": request.opportunity_id,
            "user_id": user["user_id"]
        }
        
        # Create tracked task
        task_id = await create_task(
            task_type="email_sending",
            task_data=task_data,
            user_id=user["user_id"]
        )
        
        # Define tracked task execution
        async def tracked_email_send():
            try:
                await task_tracker.start_task(task_id)
                await task_tracker.update_progress(task_id, 20, "Preparing email...")
                
                result = await email_manager.execute(task_data)
                
                await task_tracker.complete_task(task_id, result)
            except Exception as e:
                await task_tracker.fail_task(task_id, str(e))
                raise
        
        # Send email in background
        background_tasks.add_task(tracked_email_send)
        
        return {
            "status": "email_queued",
            "task_id": task_id,
            "to_email": request.to_email,
            "template_type": request.template_type,
            "message": "Email queued for sending"
        }
    except Exception as e:
        logger.error(f"Email sending error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/opportunities/discover")
async def discover_opportunities(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """Trigger opportunity discovery"""
    try:
        finder = agents["opportunity_finder"]
        
        task_data = {
            "action": "discover_opportunities",
            "user_id": user["user_id"]
        }
        
        # Create tracked task
        task_id = await create_task(
            task_type="opportunity_discovery",
            task_data=task_data,
            user_id=user["user_id"]
        )
        
        # Define tracked task execution
        async def tracked_discovery():
            try:
                await task_tracker.start_task(task_id)
                await task_tracker.update_progress(task_id, 10, "Starting opportunity discovery...")
                
                result = await finder.execute(task_data)
                
                await task_tracker.complete_task(task_id, result)
            except Exception as e:
                await task_tracker.fail_task(task_id, str(e))
                raise
        
        # Run discovery in background
        background_tasks.add_task(tracked_discovery)
        
        return {
            "status": "discovery_started",
            "task_id": task_id,
            "message": "Opportunity discovery started in background"
        }
    except Exception as e:
        logger.error(f"Discovery error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/opportunities/process-csv")
async def process_sam_csv_endpoint(
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user)
):
    """Process SAM.gov CSV file directly"""
    try:
        task_data = {
            "action": "process_sam_csv",
            "user_id": user["user_id"]
        }
        
        # Create tracked task
        task_id = await create_task(
            task_type="csv_processing",
            task_data=task_data,
            user_id=user["user_id"]
        )
        
        # Define tracked task execution
        async def tracked_csv_processing():
            try:
                await task_tracker.start_task(task_id)
                await task_tracker.update_progress(task_id, 10, "Starting CSV download...")
                
                result = await process_sam_csv()
                
                await task_tracker.complete_task(task_id, result)
            except Exception as e:
                await task_tracker.fail_task(task_id, str(e))
                raise
        
        # Run CSV processing in background
        background_tasks.add_task(tracked_csv_processing)
        
        return {
            "status": "csv_processing_started",
            "task_id": task_id,
            "message": "SAM.gov CSV processing started in background"
        }
    except Exception as e:
        logger.error(f"CSV processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/stats")
async def get_dashboard_stats(user: dict = Depends(get_current_user)):
    """Get dashboard statistics"""
    try:
        # Mock stats - in production, query from database
        stats = {
            "active_opportunities": 42,
            "pending_responses": 8,
            "submitted_responses": 156,
            "government_contacts": 89,
            "this_month": {
                "new_opportunities": 12,
                "responses_submitted": 7,
                "meetings_scheduled": 3
            },
            "win_rate": 23.5,
            "avg_response_time": "2.3 days"
        }
        
        return stats
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/status/{task_id}")
async def get_task_status_endpoint(task_id: str, user: dict = Depends(get_current_user)):
    """Get status of a background task"""
    try:
        task_status = await get_task_status(task_id)
        
        if not task_status:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Verify user has access to this task
        if task_status["user_id"] != user["user_id"]:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return task_status
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Task status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tasks")
async def get_user_tasks(
    status: Optional[str] = None, 
    limit: int = 50,
    user: dict = Depends(get_current_user)
):
    """Get tasks for the current user"""
    try:
        tasks = await task_tracker.get_user_tasks(
            user_id=user["user_id"],
            status_filter=status,
            limit=limit
        )
        
        return {
            "tasks": tasks,
            "total": len(tasks),
            "user_id": user["user_id"]
        }
    except Exception as e:
        logger.error(f"Get user tasks error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# System endpoints
@app.post("/api/system/initialize")
async def initialize_system(user: dict = Depends(get_current_user)):
    """Initialize the search engine and system components"""
    try:
        await search_engine.initialize()
        
        return {
            "status": "initialized",
            "message": "System initialized successfully"
        }
    except Exception as e:
        logger.error(f"System initialization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize system on startup"""
    logger.info("Starting Sources Sought AI API server...")
    try:
        await search_engine.initialize()
        logger.info("Search engine initialized")
    except Exception as e:
        logger.error(f"Startup error: {e}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down Sources Sought AI API server...")


if __name__ == "__main__":
    uvicorn.run(
        "src.api.server:app",
        host="0.0.0.0",
        port=8080,
        reload=True if config.environment == "development" else False,
        log_level="info"
    )