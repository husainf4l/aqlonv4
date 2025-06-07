"""
Memory export/import functionality for AQLON
Allows exporting and importing full memory snapshots
"""
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
import base64
import gzip
import pickle

from app.logger import logger
from app.memory import Memory

class MemorySnapshotEncoder(json.JSONEncoder):
    """
    Custom JSON encoder for serializing memory objects that might contain non-serializable types
    """
    def default(self, obj):
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return base64.b64encode(obj).decode('utf-8')
        try:
            return super().default(obj)
        except TypeError:
            # For non-serializable objects, convert to string representation
            return str(obj)

def export_memory_snapshot(memory_instance: Memory, include_events: bool = True, 
                           include_goals: bool = True, compress: bool = True) -> Dict[str, Any]:
    """
    Export a complete snapshot of the memory system
    
    Args:
        memory_instance: The memory instance to export
        include_events: Whether to include full event history
        include_goals: Whether to include goal history
        compress: Whether to compress the large fields
        
    Returns:
        A dictionary containing the memory snapshot
    """
    snapshot = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "session_id": str(memory_instance.session_id),
            "version": "1.0"
        },
        "working_memory": memory_instance.working_memory
    }
    
    if include_events:
        try:
            # Get events from database
            events = []
            session = None
            try:
                from app.models.database import SessionLocal
                from app.models.memory_models import MemoryEvent
                
                if SessionLocal:
                    session = SessionLocal()
                    # Query all events for this session
                    db_events = session.query(MemoryEvent).all()
                    for event in db_events:
                        events.append({
                            "id": str(event.id),
                            "goal_id": str(event.goal_id) if event.goal_id else None,
                            "step_id": str(event.step_id) if event.step_id else None,
                            "agent_action": event.agent_action,
                            "vision_state": event.vision_state,
                            "terminal_output": event.terminal_output,
                            "notes": event.notes,
                            "meta": event.meta,
                            "timestamp": event.timestamp.isoformat() if event.timestamp else None
                        })
            finally:
                if session:
                    session.close()
            
            # Add to snapshot
            if compress and events:
                snapshot["events"] = {
                    "format": "gzip+base64",
                    "data": base64.b64encode(gzip.compress(json.dumps(events).encode('utf-8'))).decode('utf-8')
                }
            else:
                snapshot["events"] = events
        except Exception as e:
            logger.error(f"Error exporting events: {e}")
            snapshot["events"] = {"error": str(e)}
            
    if include_goals:
        try:
            # Get goals from database
            goals = []
            try:
                from app.nodes.goal_history import get_all_goals
                
                # Get all goals for this session
                goals_objs = get_all_goals(session_id=memory_instance.session_id)
                for goal in goals_objs:
                    goals.append({
                        "id": str(goal.id),
                        "session_id": str(goal.session_id),
                        "goal_text": goal.goal_text,
                        "status": goal.status,
                        "priority": goal.priority,
                        "parent_goal_id": str(goal.parent_goal_id) if goal.parent_goal_id else None,
                        "success_score": goal.success_score,
                        "created_at": goal.created_at.isoformat() if goal.created_at else None,
                        "completed_at": goal.completed_at.isoformat() if goal.completed_at else None,
                        "metadata": goal.metadata
                    })
            except ImportError:
                goals = {"error": "Goal history module not available"}
            except Exception as e:
                goals = {"error": str(e)}
                
            # Add to snapshot
            if compress and isinstance(goals, list) and goals:
                snapshot["goals"] = {
                    "format": "gzip+base64",
                    "data": base64.b64encode(gzip.compress(json.dumps(goals).encode('utf-8'))).decode('utf-8')
                }
            else:
                snapshot["goals"] = goals
        except Exception as e:
            logger.error(f"Error exporting goals: {e}")
            snapshot["goals"] = {"error": str(e)}
    
    return snapshot

def import_memory_snapshot(memory_instance: Memory, snapshot: Dict[str, Any], 
                           import_events: bool = True, import_goals: bool = True) -> bool:
    """
    Import a memory snapshot into the current memory system
    
    Args:
        memory_instance: The memory instance to import into
        snapshot: The snapshot to import
        import_events: Whether to import events
        import_goals: Whether to import goals
        
    Returns:
        True if import was successful, False otherwise
    """
    try:
        # Import working memory
        if "working_memory" in snapshot:
            memory_instance.working_memory.update(snapshot["working_memory"])
            
        # Import events if requested
        if import_events and "events" in snapshot:
            events = snapshot["events"]
            
            # Handle compressed events
            if isinstance(events, dict) and events.get("format") == "gzip+base64":
                compressed_data = base64.b64decode(events["data"])
                decompressed_data = gzip.decompress(compressed_data)
                events = json.loads(decompressed_data.decode('utf-8'))
            
            if isinstance(events, list):
                from app.models.database import SessionLocal
                from app.models.memory_models import MemoryEvent
                
                if not SessionLocal:
                    logger.warning("Database not available, skipping event import")
                else:
                    session = SessionLocal()
                    try:
                        # First clear existing events
                        session.query(MemoryEvent).delete()
                        
                        # Import new events
                        for event_data in events:
                            # Convert string IDs back to UUIDs
                            if "id" in event_data and event_data["id"]:
                                event_data["id"] = uuid.UUID(event_data["id"])
                            if "goal_id" in event_data and event_data["goal_id"]:
                                event_data["goal_id"] = uuid.UUID(event_data["goal_id"])
                            if "step_id" in event_data and event_data["step_id"]:
                                event_data["step_id"] = uuid.UUID(event_data["step_id"])
                                
                            # Handle timestamp
                            if "timestamp" in event_data and event_data["timestamp"]:
                                event_data["timestamp"] = datetime.fromisoformat(event_data["timestamp"])
                            
                            # Create and add event
                            event = MemoryEvent(**event_data)
                            session.add(event)
                            
                        session.commit()
                    except Exception as e:
                        logger.error(f"Error importing events: {e}")
                        session.rollback()
                        return False
                    finally:
                        session.close()
        
        # Import goals if requested
        if import_goals and "goals" in snapshot:
            goals = snapshot["goals"]
            
            # Handle compressed goals
            if isinstance(goals, dict) and goals.get("format") == "gzip+base64":
                compressed_data = base64.b64decode(goals["data"])
                decompressed_data = gzip.decompress(compressed_data)
                goals = json.loads(decompressed_data.decode('utf-8'))
                
            if isinstance(goals, list):
                try:
                    from app.nodes.goal_history import GoalHistory, clear_goals, add_goal_direct
                    
                    # Clear existing goals
                    clear_goals(session_id=memory_instance.session_id)
                    
                    # Import new goals
                    for goal_data in goals:
                        # Convert string IDs back to UUIDs
                        if "id" in goal_data and goal_data["id"]:
                            goal_data["id"] = uuid.UUID(goal_data["id"])
                        if "session_id" in goal_data and goal_data["session_id"]:
                            goal_data["session_id"] = uuid.UUID(goal_data["session_id"])
                        if "parent_goal_id" in goal_data and goal_data["parent_goal_id"]:
                            goal_data["parent_goal_id"] = uuid.UUID(goal_data["parent_goal_id"])
                            
                        # Handle timestamps
                        if "created_at" in goal_data and goal_data["created_at"]:
                            goal_data["created_at"] = datetime.fromisoformat(goal_data["created_at"])
                        if "completed_at" in goal_data and goal_data["completed_at"]:
                            goal_data["completed_at"] = datetime.fromisoformat(goal_data["completed_at"])
                        
                        # Add goal directly
                        add_goal_direct(**goal_data)
                except ImportError:
                    logger.warning("Goal history module not available, skipping goal import")
                except Exception as e:
                    logger.error(f"Error importing goals: {e}")
                    return False
        
        return True
    except Exception as e:
        logger.error(f"Error importing memory snapshot: {e}")
        return False

def save_memory_snapshot_to_file(snapshot: Dict[str, Any], file_path: str) -> bool:
    """
    Save a memory snapshot to a file
    
    Args:
        snapshot: The snapshot to save
        file_path: Path to save the snapshot to
        
    Returns:
        True if save was successful, False otherwise
    """
    try:
        # Ensure directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON with custom encoder
        with open(file_path, 'w') as f:
            json.dump(snapshot, f, cls=MemorySnapshotEncoder, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving memory snapshot to file: {e}")
        return False

def load_memory_snapshot_from_file(file_path: str) -> Optional[Dict[str, Any]]:
    """
    Load a memory snapshot from a file
    
    Args:
        file_path: Path to load the snapshot from
        
    Returns:
        The loaded snapshot, or None if loading failed
    """
    try:
        with open(file_path, 'r') as f:
            snapshot = json.load(f)
        return snapshot
    except Exception as e:
        logger.error(f"Error loading memory snapshot from file: {e}")
        return None

# Extended functionality for pickle-based binary snapshots for large memory instances
def export_memory_binary(memory_instance: Memory, file_path: str) -> bool:
    """
    Export memory to a binary file using pickle
    
    Args:
        memory_instance: The memory instance to export
        file_path: Path to save the snapshot to
        
    Returns:
        True if export was successful, False otherwise
    """
    try:
        # Create a copy to avoid pickle issues with DB connections
        serializable_memory = {
            "session_id": memory_instance.session_id,
            "working_memory": memory_instance.working_memory,
            "export_time": datetime.now()
        }
        
        # Ensure directory exists
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Use pickle for the most reliable serialization
        with open(file_path, 'wb') as f:
            pickle.dump(serializable_memory, f)
        
        return True
    except Exception as e:
        logger.error(f"Error exporting memory binary: {e}")
        return False

def import_memory_binary(memory_instance: Memory, file_path: str) -> bool:
    """
    Import memory from a binary file using pickle
    
    Args:
        memory_instance: The memory instance to import into
        file_path: Path to load the snapshot from
        
    Returns:
        True if import was successful, False otherwise
    """
    try:
        with open(file_path, 'rb') as f:
            data = pickle.load(f)
        
        # Update memory instance
        memory_instance.working_memory = data.get("working_memory", {})
        
        return True
    except Exception as e:
        logger.error(f"Error importing memory binary: {e}")
        return False
