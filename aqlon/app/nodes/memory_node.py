from app.logger import logger
from app.state import AgentState
from app.settings import settings
from app.memory import memory
from sqlalchemy import create_engine, Column, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import func
import uuid

Base = declarative_base()

class MemoryEvent(Base):
    __tablename__ = "memory_events"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    goal_id = Column(PG_UUID(as_uuid=True), nullable=True)
    step_id = Column(PG_UUID(as_uuid=True), nullable=True)
    agent_action = Column(Text, nullable=False)
    vision_state = Column(Text, nullable=True)
    terminal_output = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    meta = Column(JSONB, nullable=True)

# Initialize database connection only when the module is loaded
engine = None
SessionLocal = None

try:
    DATABASE_URL = settings.get_effective_database_url()
    if DATABASE_URL:
        engine = create_engine(DATABASE_URL, echo=False, future=True)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        logger.info(f"Database connection initialized with URL: {DATABASE_URL}")
    else:
        logger.warning("No database URL available in settings")
except Exception as e:
    logger.error(f"Failed to connect to database: {e}")

def memory_node(state: AgentState) -> AgentState:
    logger.info(f"[MemoryNode] Received state: {state}")
    
    # Skip database operations if not properly connected
    if not SessionLocal:
        logger.warning("[MemoryNode] Database connection not available, skipping database operations")
        return state
    
    # Record the event in the database
    session = SessionLocal()
    try:
        event = MemoryEvent(
            goal_id=getattr(state, "goal_id", None),
            step_id=getattr(state, "step_id", None),
            agent_action=getattr(state, "agent_action", ""),
            vision_state=getattr(state, "vision_state", None),
            terminal_output=getattr(state, "terminal_output", None),
            notes=getattr(state, "notes", None),
            meta=getattr(state, "meta", None),
            timestamp=getattr(state, "timestamp", None)
        )
        session.add(event)
        session.commit()
        logger.info(f"[MemoryNode] Inserted MemoryEvent: {event}")
    except Exception as e:
        logger.error(f"Memory node error: {e}")
        session.rollback()
    finally:
        session.close()
    
    # Generate and update timeline in state
    try:
        # Check if timeline update is requested or if we should use default settings
        timeline_hours = getattr(state, "timeline_hours", 24)
        timeline_limit = getattr(state, "timeline_limit", 50)
        include_goals = getattr(state, "timeline_include_goals", True)
        include_events = getattr(state, "timeline_include_events", True)
        
        # Get the session ID from state or use the current memory session
        session_id = getattr(state, "session_id", None) or memory.session_id
        
        # Generate timeline
        timeline = memory.get_timeline(
            hours_back=timeline_hours,
            limit=timeline_limit,
            include_goals=include_goals,
            include_events=include_events,
            session_id=session_id
        )
        
        # Update state with timeline
        state.event_timeline = timeline.get("items", [])
        state.timeline_summary = {
            "total_items": timeline.get("total_items", 0),
            "goals_count": timeline.get("goals_count", 0),
            "events_count": timeline.get("events_count", 0),
            "session_id": timeline.get("session_id"),
            "start_time": timeline.get("start_time"),
            "end_time": timeline.get("end_time")
        }
        
        logger.info(f"[MemoryNode] Generated timeline with {len(state.event_timeline)} items")
    except Exception as e:
        logger.error(f"Timeline generation error in memory node: {e}")
        state.timeline_error = str(e)
    
    logger.info(f"[MemoryNode] Resulting state: {state}")
    return state

if __name__ == "__main__":
    if engine:
        try:
            # Note: Create tables is only for development/testing
            # For production, use Alembic migrations
            logger.warning("Creating tables directly is not recommended for production")
            Base.metadata.create_all(engine)
            logger.info("Created memory_events table")
            
            # Test insertion
            from app.state import AgentState
            sample_state = AgentState(
                goal_id=uuid.uuid4(),
                step_id=uuid.uuid4(),
                agent_action="Clicked button X",
                vision_state="{\"screen\": \"main\"}",
                terminal_output="ls -la output...",
                notes="Test event",
                meta={"user": "test", "env": "dev"}
            )
            memory_node(sample_state)
            print("Memory event inserted.")
        except Exception as e:
            logger.error(f"Error in memory_node test: {e}")
    else:
        logger.error("Cannot run memory_node test: No database connection")