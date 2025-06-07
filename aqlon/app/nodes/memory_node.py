from app.logger import logger
from app.state import AgentState
from app.models.database import SessionLocal
from app.models.memory_models import MemoryEvent
import uuid
import os
from datetime import datetime
from pathlib import Path

# Import memory after our imports to prevent circular dependency
from app.memory import memory
# Import memory export functionality
from app.memory_export import export_memory_snapshot, import_memory_snapshot, save_memory_snapshot_to_file

def memory_node(state: AgentState) -> AgentState:
    logger.info(f"[MemoryNode] Received state: {state}")
    
    # Skip database operations if not properly connected
    if not SessionLocal:
        logger.warning("[MemoryNode] Database connection not available, skipping database operations")
        return state
    
    # Check if we should export memory snapshot
    if getattr(state, "export_memory", False):
        # Export memory snapshot
        try:
            snapshot_dir = Path(os.environ.get("AQLON_SNAPSHOTS_DIR", "./snapshots"))
            snapshot_dir.mkdir(parents=True, exist_ok=True)
            
            session_id = getattr(state, "session_id", None)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"memory_snapshot_{session_id}_{timestamp}.json"
            file_path = snapshot_dir / filename
            
            # Get snapshot
            snapshot = export_memory_snapshot(
                memory_instance=memory,
                include_events=getattr(state, "export_include_events", True),
                include_goals=getattr(state, "export_include_goals", True),
                compress=getattr(state, "export_compress", True)
            )
            
            # Save to file
            success = save_memory_snapshot_to_file(snapshot, str(file_path))
            
            # Update state
            if success:
                state.memory_export_path = str(file_path)
                state.memory_export_success = True
                logger.info(f"[MemoryNode] Memory snapshot exported to {file_path}")
            else:
                state.memory_export_success = False
                state.memory_export_error = "Failed to export memory snapshot"
                logger.error("[MemoryNode] Failed to export memory snapshot")
        except Exception as e:
            state.memory_export_success = False
            state.memory_export_error = str(e)
            logger.error(f"[MemoryNode] Memory export error: {e}")
    
    # Check if we should import memory snapshot
    if getattr(state, "import_memory", False) and getattr(state, "memory_import_path", None):
        # Import memory snapshot
        try:
            from app.memory_export import load_memory_snapshot_from_file
            
            # Load snapshot
            snapshot = load_memory_snapshot_from_file(state.memory_import_path)
            
            if snapshot:
                # Import snapshot
                success = import_memory_snapshot(
                    memory_instance=memory,
                    snapshot=snapshot,
                    import_events=getattr(state, "import_include_events", True),
                    import_goals=getattr(state, "import_include_goals", True)
                )
                
                # Update state
                if success:
                    state.memory_import_success = True
                    logger.info(f"[MemoryNode] Memory snapshot imported from {state.memory_import_path}")
                else:
                    state.memory_import_success = False
                    state.memory_import_error = "Failed to import memory snapshot"
                    logger.error("[MemoryNode] Failed to import memory snapshot")
            else:
                state.memory_import_success = False
                state.memory_import_error = f"Failed to load snapshot from {state.memory_import_path}"
                logger.error(f"[MemoryNode] Failed to load snapshot from {state.memory_import_path}")
        except Exception as e:
            state.memory_import_success = False
            state.memory_import_error = str(e)
            logger.error(f"[MemoryNode] Memory import error: {e}")
    
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
        logger.info(f"[MemoryNode] Recorded memory event: {event.id}")
        
        # Use memory system to record event
        if memory:
            memory.record_db_event(event)
        
        # Update state with event ID
        state.last_event_id = event.id
    except Exception as e:
        logger.error(f"Error recording memory event: {e}")
        session.rollback()
    finally:
        session.close()
    
    # Generate timeline for state
    try:
        timeline = memory.get_timeline() if memory else {"items": [], "total_items": 0}
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
    from app.models.database import engine, Base
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