from app.logger import logger
from app.state import AgentState
from sqlalchemy import Column, Text, TIMESTAMP, Integer, Boolean, Float
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.sql import func
import uuid
from datetime import datetime

# Import Base and SessionLocal from database module
from app.models.database import Base, SessionLocal, engine

# Define Goal History Schema
class GoalHistory(Base):
    __tablename__ = "goal_history"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    goal_text = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="created")  # created, in_progress, completed, failed
    priority = Column(Integer, nullable=False, default=1)  # 1-5, higher is more important
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    meta_info = Column(JSONB, nullable=True)  # Renamed from 'metadata' which is reserved in SQLAlchemy
    success_score = Column(Float, nullable=True)  # 0-1, measure of goal completion
    parent_goal_id = Column(PG_UUID(as_uuid=True), nullable=True)  # For hierarchical goals

def save_goal(
    goal_text: str, 
    session_id=None, 
    priority=1, 
    status="created", 
    parent_goal_id=None,
    metadata=None
) -> uuid.UUID:
    """Save a new goal to the goal history database"""
    if not SessionLocal:
        logger.warning("Database connection not available, skipping goal history save")
        return None
    
    session = SessionLocal()
    try:
        goal = GoalHistory(
            session_id=session_id,
            goal_text=goal_text,
            status=status,
            priority=priority,
            parent_goal_id=parent_goal_id,
            meta_info=metadata
        )
        session.add(goal)
        session.commit()
        logger.info(f"New goal saved to history: {goal_text[:50]}...")
        return goal.id
    except Exception as e:
        logger.error(f"Goal history save error: {e}")
        session.rollback()
        return None
    finally:
        session.close()

def update_goal_status(goal_id: uuid.UUID, status: str, success_score=None, metadata=None):
    """Update the status of an existing goal"""
    if not SessionLocal:
        logger.warning("Database connection not available, skipping goal status update")
        return False
    
    session = SessionLocal()
    try:
        goal = session.query(GoalHistory).filter(GoalHistory.id == goal_id).first()
        if not goal:
            logger.warning(f"Goal {goal_id} not found in history")
            return False
        
        goal.status = status
        if status in ["completed", "failed"]:
            goal.completed_at = datetime.now()
            goal.is_active = False
        
        if success_score is not None:
            goal.success_score = success_score
            
        if metadata:
            if goal.meta_info:
                goal.meta_info.update(metadata)
            else:
                goal.meta_info = metadata
                
        session.commit()
        logger.info(f"Goal {goal_id} updated: status={status}")
        return True
    except Exception as e:
        logger.error(f"Goal status update error: {e}")
        session.rollback()
        return False
    finally:
        session.close()

def get_active_goals(session_id=None, limit=5):
    """Get currently active goals, optionally filtered by session"""
    if not SessionLocal:
        logger.warning("Database connection not available, skipping active goals query")
        return []
    
    session = SessionLocal()
    try:
        query = session.query(GoalHistory).filter(GoalHistory.is_active.is_(True))
        if session_id:
            query = query.filter(GoalHistory.session_id == session_id)
        
        goals = query.order_by(GoalHistory.priority.desc(), GoalHistory.created_at.asc()).limit(limit).all()
        return goals
    except Exception as e:
        logger.error(f"Get active goals error: {e}")
        return []
    finally:
        session.close()

def get_goal_by_id(goal_id: uuid.UUID):
    """Get a goal by its ID"""
    if not SessionLocal:
        logger.warning("Database connection not available, skipping goal query")
        return None
    
    session = SessionLocal()
    try:
        goal = session.query(GoalHistory).filter(GoalHistory.id == goal_id).first()
        return goal
    except Exception as e:
        logger.error(f"Goal query error: {e}")
        return None
    finally:
        session.close()

def goal_history_node(state: AgentState) -> AgentState:
    """
    Node for persisting goal-related information in the agent workflow
    """
    logger.info("[GoalHistoryNode] Processing state")
    
    try:
        # Save goal if it's new or changed
        goal_text = getattr(state, "goal", None)
        goal_id = getattr(state, "goal_id", None)
        goal_complete = getattr(state, "goal_complete", False)
        
        if goal_text and not goal_id:
            # This is a new goal, save it to history
            goal_id = save_goal(goal_text)
            state.goal_id = goal_id
            logger.info(f"[GoalHistoryNode] New goal saved with ID: {goal_id}")
        
        elif goal_id and goal_complete:
            # Goal is marked as complete, update its status
            success = update_goal_status(
                goal_id, 
                "completed", 
                success_score=1.0,  # TODO: Calculate real success score
                metadata={"completed_iteration": getattr(state, "internal_loop_counter", 0)}
            )
            if success:
                logger.info(f"[GoalHistoryNode] Goal {goal_id} marked as completed")
        
    except Exception as e:
        logger.error(f"Goal history node error: {e}")
    
    return state

# Initialize goal_history table if needed
if __name__ == "__main__":
    if engine:
        Base.metadata.create_all(engine)
        print("Created goal_history table")
