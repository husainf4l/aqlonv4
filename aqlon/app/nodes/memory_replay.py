"""
Memory replay functionality for restoring past session state
"""

import uuid
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from app.logger import logger
from app.state import AgentState
from app.memory import memory  # Import the global memory instance
from app.nodes.goal_history import GoalHistory

class SessionReplay:
    """Handles replaying past sessions and restoring state"""
    
    def __init__(self, memory_instance=None):
        """Initialize with a memory instance or use the global one"""
        self.memory = memory_instance or memory
    
    def get_available_sessions(self, hours_back: int = 24 * 7) -> List[Dict[str, Any]]:
        """
        Get a list of available sessions that can be replayed
        Returns a list of session summary dictionaries
        """
        # This would typically query a sessions table in the database
        # For now, infer sessions from goal history
        session_map = {}
        
        # Get goals from the recent past
        goals = self.memory.get_goal_history(hours_back=hours_back, limit=100, session_id=None)
        
        # Group by session
        for goal in goals:
            if not goal.session_id:
                continue
                
            session_id = goal.session_id
            if session_id not in session_map:
                session_map[session_id] = {
                    "session_id": str(session_id),
                    "first_seen": goal.created_at,
                    "last_seen": goal.created_at,
                    "goals": [],
                    "completed_goals": 0,
                    "failed_goals": 0,
                    "active_goals": 0
                }
            
            # Update session info
            session = session_map[session_id]
            session["goals"].append(goal)
            
            # Update timestamps
            if goal.created_at < session["first_seen"]:
                session["first_seen"] = goal.created_at
            if goal.created_at > session["last_seen"]:
                session["last_seen"] = goal.created_at
                
            # Update goal counts
            if goal.status == "completed":
                session["completed_goals"] += 1
            elif goal.status == "failed":
                session["failed_goals"] += 1
            elif goal.is_active:
                session["active_goals"] += 1
        
        # Convert to list and add summary info
        sessions = []
        for session_id, session in session_map.items():
            # Calculate duration
            duration = session["last_seen"] - session["first_seen"]
            
            # Create a summary for each session
            sessions.append({
                "session_id": str(session_id),
                "start_time": session["first_seen"].isoformat(),
                "end_time": session["last_seen"].isoformat(),
                "duration_seconds": duration.total_seconds(),
                "goal_count": len(session["goals"]),
                "completed_goals": session["completed_goals"],
                "failed_goals": session["failed_goals"],
                "active_goals": session["active_goals"],
                "top_goals": [goal.goal_text[:100] for goal in session["goals"][:3]]
            })
        
        # Sort by recency (newest first)
        sessions.sort(key=lambda s: s["end_time"], reverse=True)
        return sessions
    
    def replay_session(self, 
                      session_id: uuid.UUID, 
                      max_events: int = 100) -> Dict[str, Any]:
        """
        Replay a session to gather its state
        Returns a dictionary with the session state
        """
        # Get the session's memory events
        events = self.memory.replay_session(session_id=session_id, limit=max_events)
        
        # Get the session's goals
        goal_session = self.memory.get_goal_history(hours_back=24*30, limit=20, session_id=session_id)
        
        # Build state recovery
        state_recovery = {
            "session_id": str(session_id),
            "event_count": len(events),
            "goal_count": len(goal_session),
            "events": [self._event_to_dict(event) for event in events],
            "goals": [self._goal_to_dict(goal) for goal in goal_session],
            "active_goals": [self._goal_to_dict(goal) for goal in goal_session if goal.is_active],
            "last_action": None,
            "last_vision": None,
            "terminal_history": []
        }
        
        # Extract additional state data from events
        for event in events:
            # Track terminal history
            if event.terminal_output:
                state_recovery["terminal_history"].append({
                    "timestamp": event.timestamp.isoformat(),
                    "output": event.terminal_output
                })
            
            # Track last vision state
            if event.vision_state:
                state_recovery["last_vision"] = event.vision_state
            
            # Track last action
            if event.agent_action:
                state_recovery["last_action"] = event.agent_action
        
        return state_recovery
    
    def restore_session_state(self, session_id: uuid.UUID) -> AgentState:
        """
        Restore an agent state from a past session
        Returns an AgentState object with the restored state
        """
        # Get session replay data
        replay_data = self.replay_session(session_id)
        
        # Create a new state
        state = AgentState()
        
        # Set the session ID
        state.session_id = session_id
        
        # Set active goals if available
        if replay_data["active_goals"]:
            # Find the highest priority active goal
            active_goal = max(replay_data["active_goals"], 
                              key=lambda g: g["priority"])
            
            state.goal = active_goal["goal_text"]
            state.goal_id = uuid.UUID(active_goal["id"])
            state.goal_priority = active_goal["priority"]
            
            # Also set all active goals
            state.active_goals = replay_data["active_goals"]
        
        # Set last vision state if available
        if replay_data["last_vision"]:
            state.vision_state = replay_data["last_vision"]
        
        # Set last action if available
        if replay_data["last_action"]:
            state.last_action = replay_data["last_action"]
        
        # Set replay flag and data
        state.is_replay = True
        state.replay_data = replay_data
        state.restored_at = datetime.now().isoformat()
        
        return state
    
    def _event_to_dict(self, event) -> Dict[str, Any]:
        """Convert a memory event to a serializable dict"""
        return {
            "id": str(event.id),
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "goal_id": str(event.goal_id) if event.goal_id else None,
            "step_id": str(event.step_id) if event.step_id else None,
            "agent_action": event.agent_action,
            "vision_state": event.vision_state,
            "terminal_output": event.terminal_output,
            "notes": event.notes,
            "meta": event.meta
        }
    
    def _goal_to_dict(self, goal: GoalHistory) -> Dict[str, Any]:
        """Convert a goal to a serializable dict"""
        return {
            "id": str(goal.id),
            "goal_text": goal.goal_text,
            "status": goal.status,
            "priority": goal.priority,
            "created_at": goal.created_at.isoformat() if goal.created_at else None,
            "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
            "is_active": goal.is_active,
            "success_score": goal.success_score,
            "parent_goal_id": str(goal.parent_goal_id) if goal.parent_goal_id else None,
            "metadata": goal.metadata
        }

def memory_replay_node(state: AgentState) -> AgentState:
    """
    Node for replaying memory and restoring past session state in the agent workflow
    """
    logger.info("[MemoryReplayNode] Processing state")
    
    try:
        # Check if this is a replay request
        replay_session_id = getattr(state, "replay_session_id", None)
        
        if replay_session_id:
            # Convert string to UUID if needed
            if isinstance(replay_session_id, str):
                replay_session_id = uuid.UUID(replay_session_id)
            
            # Create replayer and restore state
            replayer = SessionReplay()
            restored_state = replayer.restore_session_state(replay_session_id)
            
            # Copy restored values to current state
            for key, value in restored_state.__dict__.items():
                if key not in ["replay_session_id"]:  # Avoid overwriting the request itself
                    setattr(state, key, value)
                    
            logger.info(f"[MemoryReplayNode] Restored session: {replay_session_id}")
            state.memory_replay_result = "success"
        
        # If list_sessions flag is set, list available sessions
        list_sessions = getattr(state, "list_sessions", False)
        if list_sessions:
            replayer = SessionReplay()
            hours_back = getattr(state, "list_sessions_hours", 24 * 7)
            
            available_sessions = replayer.get_available_sessions(hours_back=hours_back)
            state.available_sessions = available_sessions
            logger.info(f"[MemoryReplayNode] Listed {len(available_sessions)} available sessions")
    
    except Exception as e:
        logger.error(f"Memory replay node error: {e}")
        state.memory_replay_error = str(e)
    
    return state
