from typing import Optional, Dict, Any, List
import uuid
from pydantic import BaseModel
from datetime import datetime

class AgentState(BaseModel):
    goal_id: Optional[uuid.UUID] = None
    step_id: Optional[uuid.UUID] = None
    agent_action: Optional[str] = None
    vision_state: Optional[str] = None
    terminal_output: Optional[str] = None
    notes: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None  # Use datetime for type safety
    action: Optional[Dict[str, Any]] = None
    vision_timestamp: Optional[datetime] = None
    vision_screenshot_path: Optional[str] = None
    vision_error: Optional[str] = None
    action_result: Optional[str] = None
    action_timestamp: Optional[datetime] = None
    terminal_command: Optional[str] = None
    terminal_error: Optional[str] = None
    terminal_exit_code: Optional[int] = None
    terminal_timestamp: Optional[datetime] = None
    
    # New fields used by the nodes but not previously defined
    goal: Optional[str] = ""
    goal_complete: Optional[bool] = False
    internal_loop_counter: Optional[int] = 0
    user_context: Optional[str] = None
    goal_generation_timestamp: Optional[str] = None
    goal_generation_error: Optional[str] = None
    vision_llm_summary: Optional[str] = None
    vision_llm_error: Optional[str] = None
    action_success: Optional[bool] = None
    
    # Vision node enhancements
    monitor_index: Optional[int] = 0
    capture_region: Optional[Dict[str, int]] = None
    detailed_ocr: Optional[bool] = False
    ocr_result: Optional[Dict[str, Any]] = None
    ocr_confidence: Optional[float] = None
    text_to_verify: Optional[Any] = None
    text_verification_results: Optional[Dict[str, Any]] = None
    
    # Action node enhancements
    scroll_direction: Optional[str] = None
    scroll_amount: Optional[int] = None
    hover_duration: Optional[float] = None
    mouse_down_at: Optional[Dict[str, int]] = None
    mouse_up_at: Optional[Dict[str, int]] = None
    drag_start: Optional[Dict[str, int]] = None
    drag_end: Optional[Dict[str, int]] = None
    
    # Planner node enhancements
    plan_steps: Optional[List[Dict[str, Any]]] = None
    current_step_index: Optional[int] = None
    plan_critique: Optional[Dict[str, Any]] = {}  # Initialize as empty dict instead of None
    plan_context: Optional[Dict[str, Any]] = None
    planning_progress: Optional[Dict[str, Any]] = None
    planner_error: Optional[str] = None
    
    # Memory timeline
    event_timeline: Optional[List[Dict[str, Any]]] = None
    timeline_summary: Optional[Dict[str, Any]] = None
    timeline_error: Optional[str] = None
    
    # Add more fields as needed for your agent's state

# Example usage:
# state = AgentState(goal_id=uuid.uuid4(), agent_action="Clicked button X")
