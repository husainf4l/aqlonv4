"""
Memory subsystem for AQLon agent - handles goal history, working memory, episodic memory and timeline
"""
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import desc

from app.logger import logger
from app.nodes.memory_node import MemoryEvent, SessionLocal as MemorySessionLocal
from app.nodes.goal_history import (
    GoalHistory, 
    save_goal, 
    update_goal_status, 
    get_active_goals,
    SessionLocal as GoalSessionLocal
)

class Memory:
    def __init__(self):
        self.session_id = uuid.uuid4()
        self.working_memory = {}  # Short-term memory cache
        logger.info(f"Memory system initialized with session ID: {self.session_id}")
    
    def record_event(self, 
                    agent_action: str,
                    goal_id: Optional[uuid.UUID] = None,
                    step_id: Optional[uuid.UUID] = None,
                    vision_state: Optional[str] = None,
                    terminal_output: Optional[str] = None,
                    notes: Optional[str] = None,
                    meta: Optional[Dict[str, Any]] = None) -> uuid.UUID:
        """Record a memory event in the database"""
        if not MemorySessionLocal:
            logger.warning("Database connection not available, skipping memory event recording")
            return None
        
        session = MemorySessionLocal()
        try:
            event = MemoryEvent(
                goal_id=goal_id,
                step_id=step_id,
                agent_action=agent_action,
                vision_state=vision_state,
                terminal_output=terminal_output,
                notes=notes,
                meta=meta
            )
            session.add(event)
            session.commit()
            logger.debug(f"Memory event recorded: {agent_action[:50]}...")
            return event.id
        except Exception as e:
            logger.error(f"Memory event recording error: {e}")
            session.rollback()
            return None
        finally:
            session.close()
    
    def store_goal(self, 
                  goal_text: str, 
                  priority: int = 1, 
                  parent_goal_id: Optional[uuid.UUID] = None,
                  metadata: Optional[Dict[str, Any]] = None) -> uuid.UUID:
        """Store a new goal in history"""
        return save_goal(
            goal_text=goal_text,
            session_id=self.session_id,
            priority=priority,
            parent_goal_id=parent_goal_id,
            metadata=metadata
        )
    
    def mark_goal_complete(self, 
                          goal_id: uuid.UUID, 
                          success_score: float = 1.0,
                          metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Mark a goal as completed"""
        return update_goal_status(
            goal_id=goal_id,
            status="completed",
            success_score=success_score,
            metadata=metadata
        )
    
    def mark_goal_failed(self, 
                        goal_id: uuid.UUID, 
                        success_score: float = 0.0,
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Mark a goal as failed"""
        return update_goal_status(
            goal_id=goal_id,
            status="failed",
            success_score=success_score,
            metadata=metadata
        )
    
    def get_current_goals(self, limit: int = 5) -> List[GoalHistory]:
        """Get currently active goals for this session"""
        return get_active_goals(session_id=self.session_id, limit=limit)
    
    def get_goal_history(self, 
                        hours_back: int = 24, 
                        limit: int = 20,
                        session_id: Optional[uuid.UUID] = None) -> List[GoalHistory]:
        """Get goal history within the specified time range"""
        if not GoalSessionLocal:
            logger.warning("Database connection not available, skipping goal history query")
            return []
        
        session = GoalSessionLocal()
        try:
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            query = session.query(GoalHistory).filter(GoalHistory.created_at >= cutoff_time)
            
            # Filter by session if specified
            if session_id:
                query = query.filter(GoalHistory.session_id == session_id)
            else:
                # Use current session ID by default
                query = query.filter(GoalHistory.session_id == self.session_id)
                
            goals = query.order_by(desc(GoalHistory.created_at)).limit(limit).all()
            return goals
        except Exception as e:
            logger.error(f"Goal history query error: {e}")
            return []
        finally:
            session.close()
    
    def get_related_events(self, 
                          goal_id: uuid.UUID, 
                          limit: int = 20) -> List[MemoryEvent]:
        """Get memory events related to a specific goal"""
        if not MemorySessionLocal:
            logger.warning("Database connection not available, skipping event query")
            return []
        
        session = MemorySessionLocal()
        try:
            events = session.query(MemoryEvent).filter(
                MemoryEvent.goal_id == goal_id
            ).order_by(
                desc(MemoryEvent.timestamp)
            ).limit(limit).all()
            return events
        except Exception as e:
            logger.error(f"Memory events query error: {e}")
            return []
        finally:
            session.close()
    
    def replay_session(self, 
                      session_id: Optional[uuid.UUID] = None,
                      limit: int = 100) -> List[MemoryEvent]:
        """Replay memory events from a specific session"""
        if not MemorySessionLocal:
            logger.warning("Database connection not available, skipping session replay")
            return []
            
        # If no session ID provided, use current session
        session_id = session_id or self.session_id
        
        session = MemorySessionLocal()
        try:
            # Get all goals for the session
            goal_session = GoalSessionLocal()
            goals = goal_session.query(GoalHistory).filter(
                GoalHistory.session_id == session_id
            ).all()
            goal_ids = [goal.id for goal in goals]
            goal_session.close()
            
            # Get all memory events for these goals
            if goal_ids:
                events = session.query(MemoryEvent).filter(
                    MemoryEvent.goal_id.in_(goal_ids)
                ).order_by(
                    MemoryEvent.timestamp
                ).limit(limit).all()
                return events
            return []
        except Exception as e:
            logger.error(f"Session replay error: {e}")
            return []
        finally:
            session.close()
    
    def store_in_working_memory(self, key: str, value: Any) -> None:
        """Store data in working memory (short-term)"""
        self.working_memory[key] = value
    
    def get_from_working_memory(self, key: str, default: Any = None) -> Any:
        """Retrieve data from working memory"""
        return self.working_memory.get(key, default)
    
    def clear_working_memory(self) -> None:
        """Clear all working memory"""
        self.working_memory = {}
        logger.info("Working memory cleared")
        
    def get_timeline(self,
                    hours_back: int = 24,
                    limit: int = 50,
                    include_goals: bool = True,
                    include_events: bool = True,
                    session_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        """
        Get a chronological timeline of memory events and goals
        Returns a structured timeline with events and goals merged and sorted by timestamp
        """
        timeline = {
            "events": [],
            "session_id": str(session_id or self.session_id),
            "start_time": (datetime.now() - timedelta(hours=hours_back)).isoformat(),
            "end_time": datetime.now().isoformat(),
            "items": []
        }
        
        try:
            # Use current session if not specified
            target_session_id = session_id or self.session_id
            cutoff_time = datetime.now() - timedelta(hours=hours_back)
            
            # Get goals if requested
            if include_goals and GoalSessionLocal:
                goal_session = GoalSessionLocal()
                try:
                    goals = goal_session.query(GoalHistory).filter(
                        GoalHistory.session_id == target_session_id,
                        GoalHistory.created_at >= cutoff_time
                    ).all()
                    
                    for goal in goals:
                        timeline["items"].append({
                            "type": "goal",
                            "id": str(goal.id),
                            "timestamp": goal.created_at.isoformat() if goal.created_at else None,
                            "content": goal.goal_text,
                            "status": goal.status,
                            "priority": goal.priority,
                            "metadata": goal.metadata
                        })
                except Exception as e:
                    logger.error(f"Timeline goal query error: {e}")
                finally:
                    goal_session.close()
            
            # Get events if requested
            if include_events and MemorySessionLocal:
                memory_session = MemorySessionLocal()
                try:
                    # First get all goals for this session to filter events
                    goal_ids = []
                    if GoalSessionLocal:
                        goal_session = GoalSessionLocal()
                        goals = goal_session.query(GoalHistory).filter(
                            GoalHistory.session_id == target_session_id
                        ).all()
                        goal_ids = [goal.id for goal in goals]
                        goal_session.close()
                    
                    # Get events for these goals
                    if goal_ids:
                        events = memory_session.query(MemoryEvent).filter(
                            MemoryEvent.goal_id.in_(goal_ids),
                            MemoryEvent.timestamp >= cutoff_time
                        ).order_by(
                            MemoryEvent.timestamp
                        ).limit(limit).all()
                        
                        for event in events:
                            timeline["items"].append({
                                "type": "event",
                                "id": str(event.id),
                                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                                "goal_id": str(event.goal_id) if event.goal_id else None,
                                "step_id": str(event.step_id) if event.step_id else None,
                                "action": event.agent_action[:100] + "..." if event.agent_action and len(event.agent_action) > 100 else event.agent_action,
                                "vision": event.vision_state[:100] + "..." if event.vision_state and len(event.vision_state) > 100 else None,
                                "terminal": event.terminal_output[:100] + "..." if event.terminal_output and len(event.terminal_output) > 100 else None,
                                "notes": event.notes,
                                "metadata": event.meta
                            })
                except Exception as e:
                    logger.error(f"Timeline event query error: {e}")
                finally:
                    memory_session.close()
            
            # Sort all items by timestamp
            timeline["items"].sort(key=lambda x: x.get("timestamp", ""))
            
            # Add sequence numbers for easier reference
            for i, item in enumerate(timeline["items"]):
                item["sequence"] = i + 1
                
            timeline["total_items"] = len(timeline["items"])
            timeline["goals_count"] = sum(1 for item in timeline["items"] if item["type"] == "goal")
            timeline["events_count"] = sum(1 for item in timeline["items"] if item["type"] == "event")
            
            return timeline
                
        except Exception as e:
            logger.error(f"Timeline generation error: {e}")
            return timeline

# Global instance for convenient access
memory = Memory()