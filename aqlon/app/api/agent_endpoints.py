"""
Agent-related endpoints for the AQLON API
"""
from fastapi import APIRouter, Query, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

from app.logger import logger

# Define response models for the endpoints
class AgentStatusResponse(BaseModel):
    """Response model for agent status"""
    active: bool
    active_session_id: Optional[str] = None
    active_goal: Optional[str] = None
    iterations_completed: int = 0
    iterations_max: int = 0
    last_action: Optional[Dict[str, Any]] = None
    status: str = "idle"
    error: Optional[str] = None

class GoalResponse(BaseModel):
    """Response model for goals"""
    goal_id: str
    text: str
    status: str
    created_at: str
    completed_at: Optional[str] = None
    success_score: Optional[float] = None

def create_agent_router(active_sessions: Dict[str, Any], screenshots_dir: Path):
    """
    Create an APIRouter with agent-related endpoints
    
    Args:
        active_sessions: Dictionary containing active agent sessions
        screenshots_dir: Directory for screenshots
        
    Returns:
        APIRouter: Router with agent endpoints
    """
    router = APIRouter()
    
    @router.get("/agent/status", response_model=AgentStatusResponse)
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
    
    @router.get("/goals", response_model=List[GoalResponse])
    async def list_goals(
        status: Optional[str] = Query(None, description="Filter goals by status: 'in_progress', 'completed', or 'failed'"),
        limit: int = Query(10, description="Maximum number of goals to return")
    ):
        """
        List goals with optional filtering by status
        """
        try:
            # In a real implementation, this would query the database
            # For now, we'll extract goals from active sessions
            goals = []
            
            for session_id, session in active_sessions.items():
                goal_status = "in_progress"
                if session.get("status") == "completed":
                    goal_status = "completed"
                elif session.get("status") == "error":
                    goal_status = "failed"
                
                goal_data = {
                    "goal_id": session_id,
                    "text": session.get("goal", ""),
                    "status": goal_status,
                    "created_at": session.get("created_at", ""),
                    "completed_at": session.get("completed_at"),
                    "success_score": 1.0 if goal_status == "completed" else None
                }
                
                # Apply status filter if provided
                if status and goal_status.upper() != status.upper():
                    continue
                
                goals.append(GoalResponse(**goal_data))
            
            # Sort by created_at (newest first) and apply limit
            goals = sorted(goals, key=lambda g: g.created_at, reverse=True)[:limit]
            
            return goals
        except Exception as e:
            logger.error(f"Error listing goals: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error listing goals: {str(e)}"
            )
    
    @router.get("/agent/latest-screenshot", response_class=FileResponse)
    async def get_latest_screenshot():
        """
        Get the latest screenshot taken by the agent
        """
        try:
            # Find the most recent screenshot in the screenshots directory
            screenshots = list(screenshots_dir.glob("*.png"))
            
            if not screenshots:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No screenshots available"
                )
            
            # Sort by creation time, newest first
            latest_screenshot = max(screenshots, key=lambda p: p.stat().st_mtime)
            
            return FileResponse(
                path=latest_screenshot,
                media_type="image/png",
                filename=latest_screenshot.name
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving latest screenshot: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving screenshot: {str(e)}"
            )
    
    @router.get("/agent/screenshot")
    async def get_screenshot_by_timestamp(t: str = Query(..., description="Timestamp of the screenshot")):
        """
        Get a specific screenshot by timestamp
        """
        try:
            # Look for screenshot with matching timestamp in filename
            screenshot_path = screenshots_dir / f"screenshot_{t}.png"
            
            if not screenshot_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Screenshot with timestamp {t} not found"
                )
            
            return FileResponse(
                path=screenshot_path,
                media_type="image/png",
                filename=screenshot_path.name
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving screenshot: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving screenshot: {str(e)}"
            )
    
    return router
