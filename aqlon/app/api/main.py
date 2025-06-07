"""
FastAPI app for AQLON agent control
"""
from fastapi import FastAPI, BackgroundTasks, HTTPException, status, Body, APIRouter, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
import uuid
from datetime import datetime
import os
from pathlib import Path

from app.state import AgentState
from app.graph import compiled_graph
from app.logger import logger
from app.memory import memory
from app.memory_export import export_memory_snapshot, save_memory_snapshot_to_file
from app.api.endpoints.agent import router as agent_router, configure as configure_agent

# Create FastAPI app
app = FastAPI(
    title="AQLON Agent API",
    description="API for controlling the AQLON agent and monitoring its state",
    version="1.0.0"
)

# Create v1 API router
v1_router = APIRouter(prefix="/api/v1")

# Dictionary to store active agent sessions
active_sessions = {}

# Get the templates directory path
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
STATIC_DIR = TEMPLATES_DIR / "static"
SCREENSHOTS_DIR = Path(os.environ.get("AQLON_SCREENSHOTS_DIR", "./screenshots"))
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

class SessionRequest(BaseModel):
    """Request model for starting a new agent session"""
    goal: Optional[str] = None
    initial_context: Optional[str] = None
    max_iterations: Optional[int] = 5
    monitor_index: Optional[int] = 0

class SessionResponse(BaseModel):
    """Response model for an agent session"""
    session_id: str
    status: str
    goal: Optional[str] = None
    created_at: str
    iterations_completed: int = 0
    iterations_max: int
    current_state: Optional[Dict[str, Any]] = None
    
class AgentStatusResponse(BaseModel):
    """Response model for agent status"""
    active: bool
    session_id: Optional[str] = None
    status: str
    goal: Optional[str] = None
    iterations_completed: int = 0
    iterations_max: int = 0
    last_action: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

# Keep the async function the same
async def run_agent_loop(session_id: str, goal: str, max_iterations: int, initial_context: str = None, monitor_index: int = 0):
    """
    Run the agent loop in the background
    """
    try:
        # Initialize agent state
        state = AgentState()
        state.goal = goal
        state.internal_loop_counter = 0
        state.max_iterations = max_iterations
        state.user_context = initial_context
        state.monitor_index = monitor_index
        state.session_id = uuid.UUID(session_id)
        
        logger.info(f"Starting agent loop for session {session_id}")
        
        # Run the agent loop
        result = compiled_graph.invoke(state)
        
        # Update session
        active_sessions[session_id]["status"] = "completed"
        active_sessions[session_id]["iterations_completed"] = result.internal_loop_counter
        active_sessions[session_id]["current_state"] = result.dict()
        active_sessions[session_id]["completed_at"] = datetime.now().isoformat()
        
        logger.info(f"Agent loop completed for session {session_id}")
    except Exception as e:
        # Update session on error
        active_sessions[session_id]["status"] = "error"
        active_sessions[session_id]["error"] = str(e)
        logger.error(f"Agent loop error for session {session_id}: {e}")

# Add routes to the v1 router
@v1_router.post("/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session_v1(
    background_tasks: BackgroundTasks,
    request: SessionRequest = Body(...)
):
    """
    Start a new agent session
    """
    # Validate goal
    if not request.goal:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Goal is required"
        )
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    # Store session
    active_sessions[session_id] = {
        "session_id": session_id,
        "status": "running",
        "goal": request.goal,
        "created_at": datetime.now().isoformat(),
        "iterations_completed": 0,
        "iterations_max": request.max_iterations,
        "current_state": None
    }
    
    # Start agent loop in background
    background_tasks.add_task(
        run_agent_loop,
        session_id,
        request.goal,
        request.max_iterations,
        request.initial_context,
        request.monitor_index
    )
    
    logger.info(f"Created new agent session: {session_id}")
    
    # Return response
    return SessionResponse(**active_sessions[session_id])

@v1_router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session_v1(session_id: str):
    """
    Get the status of an agent session
    """
    if session_id not in active_sessions:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found"
        )
    
    return SessionResponse(**active_sessions[session_id])

@v1_router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions_v1():
    """
    List all agent sessions
    """
    return [SessionResponse(**session) for session in active_sessions.values()]

# Keep existing endpoints for backward compatibility
@app.post("/api/session", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def start_session(
    background_tasks: BackgroundTasks,
    request: SessionRequest = Body(...)
):
    """
    Start a new agent session (legacy endpoint)
    """
    return await start_session_v1(background_tasks, request)

@app.get("/api/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """
    Get the status of an agent session (legacy endpoint)
    """
    return await get_session_v1(session_id)

@app.get("/api/sessions", response_model=List[SessionResponse])
async def list_sessions():
    """
    List all agent sessions (legacy endpoint)
    """
    return await list_sessions_v1()

# Get the templates directory path
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
STATIC_DIR = TEMPLATES_DIR / "static"
SCREENSHOTS_DIR = Path(os.environ.get("AQLON_SCREENSHOTS_DIR", "./screenshots"))
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# Mount static files directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Add route for serving the dashboard
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """
    Render the AQLON dashboard
    """
    try:
        dashboard_path = TEMPLATES_DIR / "dashboard.html"
        
        if dashboard_path.exists():
            with open(dashboard_path, "r") as f:
                return f.read()
        else:
            return """
            <html>
                <head>
                    <title>AQLON Dashboard</title>
                </head>
                <body>
                    <h1>Dashboard template not found</h1>
                    <p>Please ensure the dashboard.html file is in the templates directory.</p>
                </body>
            </html>
            """
    except Exception as e:
        logger.error(f"Error serving dashboard: {e}")
        return f"""
        <html>
            <head>
                <title>AQLON Dashboard Error</title>
            </head>
            <body>
                <h1>Error serving dashboard</h1>
                <p>{str(e)}</p>
            </body>
        </html>
        """

# Add a simple redirect from root to dashboard
@app.get("/", response_class=HTMLResponse)
async def root():
    """
    Root endpoint - redirect to dashboard
    """
    return """
    <html>
        <head>
            <meta http-equiv="refresh" content="0;url=/dashboard" />
            <title>AQLON Agent API</title>
        </head>
        <body>
            <p>Redirecting to <a href="/dashboard">dashboard</a>...</p>
        </body>
    </html>
    """

# Additional models for memory export/import
class MemoryExportRequest(BaseModel):
    """Request model for exporting memory snapshot"""
    include_events: bool = True
    include_goals: bool = True
    compress: bool = True
    
class MemoryExportResponse(BaseModel):
    """Response model for memory export"""
    success: bool
    file_path: Optional[str] = None
    timestamp: str
    error: Optional[str] = None
    
class MemoryImportRequest(BaseModel):
    """Request model for importing memory snapshot"""
    file_path: str
    import_events: bool = True
    import_goals: bool = True
    
class MemoryImportResponse(BaseModel):
    """Response model for memory import"""
    success: bool
    timestamp: str
    error: Optional[str] = None

class SessionLogExportRequest(BaseModel):
    """Request model for exporting session logs"""
    session_id: str
    format: str = "markdown"  # markdown or html
    include_screenshots: bool = False
    
class SessionLogExportResponse(BaseModel):
    """Response model for session log export"""
    success: bool
    file_path: Optional[str] = None
    timestamp: str
    error: Optional[str] = None

# Add memory management endpoints to v1 router
@v1_router.post("/memory/export", response_model=MemoryExportResponse)
async def export_memory(request: MemoryExportRequest = Body(...)):
    """
    Export a memory snapshot to a file
    """
    try:
        # Create snapshots directory if it doesn't exist
        snapshots_dir = Path(os.environ.get("AQLON_SNAPSHOTS_DIR", "./snapshots"))
        snapshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_id = getattr(memory, "session_id", "unknown")
        filename = f"memory_snapshot_{session_id}_{timestamp}.json"
        file_path = snapshots_dir / filename
        
        # Generate snapshot
        snapshot = export_memory_snapshot(
            memory_instance=memory,
            include_events=request.include_events,
            include_goals=request.include_goals,
            compress=request.compress
        )
        
        # Save to file
        success = save_memory_snapshot_to_file(snapshot, str(file_path))
        
        if success:
            return MemoryExportResponse(
                success=True,
                file_path=str(file_path),
                timestamp=datetime.now().isoformat()
            )
        else:
            return MemoryExportResponse(
                success=False,
                timestamp=datetime.now().isoformat(),
                error="Failed to save memory snapshot to file"
            )
    except Exception as e:
        logger.error(f"Memory export error: {e}")
        return MemoryExportResponse(
            success=False,
            timestamp=datetime.now().isoformat(),
            error=str(e)
        )

@v1_router.post("/memory/import", response_model=MemoryImportResponse)
async def import_memory(request: MemoryImportRequest = Body(...)):
    """
    Import a memory snapshot from a file
    """
    try:
        from app.memory_export import load_memory_snapshot_from_file, import_memory_snapshot
        
        # Check if file exists
        if not Path(request.file_path).exists():
            return MemoryImportResponse(
                success=False,
                timestamp=datetime.now().isoformat(),
                error=f"File not found: {request.file_path}"
            )
        
        # Load snapshot from file
        snapshot = load_memory_snapshot_from_file(request.file_path)
        if not snapshot:
            return MemoryImportResponse(
                success=False,
                timestamp=datetime.now().isoformat(),
                error="Failed to load snapshot from file"
            )
        
        # Import snapshot to memory
        success = import_memory_snapshot(
            memory_instance=memory,
            snapshot=snapshot,
            import_events=request.import_events,
            import_goals=request.import_goals
        )
        
        if success:
            return MemoryImportResponse(
                success=True,
                timestamp=datetime.now().isoformat()
            )
        else:
            return MemoryImportResponse(
                success=False,
                timestamp=datetime.now().isoformat(),
                error="Failed to import memory snapshot"
            )
    except Exception as e:
        logger.error(f"Memory import error: {e}")
        return MemoryImportResponse(
            success=False,
            timestamp=datetime.now().isoformat(),
            error=str(e)
        )

@v1_router.post("/session/{session_id}/export-log", response_model=SessionLogExportResponse)
async def export_session_log(
    session_id: str,
    request: SessionLogExportRequest = Body(...)
):
    """
    Export session logs as HTML or Markdown
    """
    try:
        # Check if session exists
        if session_id not in active_sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        
        # Create logs directory if it doesn't exist
        logs_dir = Path(os.environ.get("AQLON_LOGS_DIR", "./logs"))
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate log filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = "md" if request.format.lower() == "markdown" else "html"
        filename = f"session_{session_id}_{timestamp}.{ext}"
        file_path = logs_dir / filename
        
        # Generate session log
        from app.export_logs import export_session_logs
        
        success = export_session_logs(
            session_id=session_id,
            output_file=str(file_path),
            format=request.format,
            include_screenshots=request.include_screenshots
        )
        
        if success:
            return SessionLogExportResponse(
                success=True,
                file_path=str(file_path),
                timestamp=datetime.now().isoformat()
            )
        else:
            return SessionLogExportResponse(
                success=False,
                timestamp=datetime.now().isoformat(),
                error="Failed to export session logs"
            )
    except Exception as e:
        logger.error(f"Session log export error: {e}")
        return SessionLogExportResponse(
            success=False,
            timestamp=datetime.now().isoformat(),
            error=str(e)
        )

@v1_router.get("/session/{session_id}/log", response_model=Any)
async def get_session_log(session_id: str, format: str = "json"):
    """
    Get session log in specified format (json, markdown, html)
    """
    try:
        # Check if session exists
        if session_id not in active_sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found"
            )
        
        # Get session log
        from app.export_logs import generate_session_log
        
        log_content = generate_session_log(
            session_id=session_id,
            format=format
        )
        
        if format.lower() == "json":
            return log_content
        elif format.lower() in ["markdown", "html"]:
            media_type = "text/markdown" if format.lower() == "markdown" else "text/html"
            return Response(content=log_content, media_type=media_type)
        else:
            return {"error": "Unsupported format. Use 'json', 'markdown', or 'html'"}
    except Exception as e:
        logger.error(f"Session log retrieval error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving session log: {str(e)}"
        )

# Add agent status and goal endpoints
@v1_router.get("/agent/status", response_model=AgentStatusResponse)
async def get_agent_status():
    """
    Get the current status of the agent
    """
    # Find the most recently active session
    active_session_id = None
    active_goal = None
    iterations_completed = 0
    iterations_max = 0
    last_action = None
    status = "idle"
    error = None
    
    # Get the most recent session based on created_at timestamp
    recent_sessions = sorted(
        [s for s in active_sessions.values()], 
        key=lambda s: s.get("created_at", ""), 
        reverse=True
    )
    
    if recent_sessions:
        latest_session = recent_sessions[0]
        active_session_id = latest_session.get("session_id")
        active_goal = latest_session.get("goal")
        iterations_completed = latest_session.get("iterations_completed", 0)
        iterations_max = latest_session.get("iterations_max", 0)
        status = latest_session.get("status", "idle")
        error = latest_session.get("error")
        
        # Get last action if available
        current_state = latest_session.get("current_state", {})
        if current_state:
            last_action = current_state.get("action", None)
    
    return AgentStatusResponse(
        active=status == "running",
        active_session_id=active_session_id,
        active_goal=active_goal,
        iterations_completed=iterations_completed,
        iterations_max=iterations_max,
        last_action=last_action,
        status=status,
        error=error
    )

@v1_router.get("/agent/goal", response_model=Dict[str, str])
async def get_agent_goal():
    """
    Get the current goal of the AQLON agent
    """
    try:
        # For now, just return a dummy goal
        return {
            "goal": "No goal set"
        }
    except Exception as e:
        logger.error(f"Error retrieving agent goal: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving agent goal: {str(e)}"
        )

# Configure agent endpoints
configure_agent(active_sessions, SCREENSHOTS_DIR)

# Include agent endpoints in v1 router
v1_router.include_router(agent_router)

# Include the v1 router in the app
app.include_router(v1_router)
