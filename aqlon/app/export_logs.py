"""
Export session logs in different formats (JSON, HTML, Markdown)
"""
import json
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
import os
import base64

from app.logger import logger
from app.models.database import SessionLocal
from app.models.memory_models import MemoryEvent

def generate_session_log(session_id: str, format: str = "json") -> Union[Dict[str, Any], str]:
    """
    Generate session log in specified format
    
    Args:
        session_id: The session ID
        format: The output format (json, markdown, html)
        
    Returns:
        The session log in the specified format
    """
    try:
        # Get session events from database
        events = get_session_events(session_id)
        
        if not events:
            if format == "json":
                return {"error": f"No events found for session {session_id}"}
            else:
                return f"No events found for session {session_id}"
        
        # Generate log in specified format
        if format.lower() == "json":
            return {"session_id": session_id, "events": events}
        elif format.lower() == "markdown":
            return generate_markdown_log(session_id, events)
        elif format.lower() == "html":
            return generate_html_log(session_id, events)
        else:
            logger.error(f"Unsupported log format: {format}")
            if format == "json":
                return {"error": f"Unsupported log format: {format}"}
            else:
                return f"Unsupported log format: {format}"
    except Exception as e:
        logger.error(f"Error generating session log: {e}")
        if format == "json":
            return {"error": str(e)}
        else:
            return f"Error generating session log: {e}"

def export_session_logs(session_id: str, output_file: str, format: str = "markdown", include_screenshots: bool = False) -> bool:
    """
    Export session logs to a file
    
    Args:
        session_id: The session ID
        output_file: The output file path
        format: The output format (markdown or html)
        include_screenshots: Whether to include screenshots
        
    Returns:
        True if export was successful, False otherwise
    """
    try:
        # Generate log content
        log_content = generate_session_log(session_id, format)
        
        # Create output directory if it doesn't exist
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to file
        with open(output_file, 'w') as f:
            f.write(log_content)
        
        # Copy screenshots if requested
        if include_screenshots and format.lower() in ["markdown", "html"]:
            try:
                # Handle screenshot copying
                copy_session_screenshots(session_id, output_path.parent)
            except Exception as e:
                logger.warning(f"Error copying screenshots: {e}")
        
        return True
    except Exception as e:
        logger.error(f"Error exporting session logs: {e}")
        return False

def get_session_events(session_id: str) -> List[Dict[str, Any]]:
    """
    Get events for a session from the database
    
    Args:
        session_id: The session ID
        
    Returns:
        A list of events
    """
    events = []
    
    if not SessionLocal:
        logger.warning("Database connection not available, cannot retrieve session events")
        return events
    
    session = SessionLocal()
    try:
        # Convert session_id from string to UUID if necessary
        try:
            session_uuid = uuid.UUID(session_id)
        except ValueError:
            logger.error(f"Invalid session ID format: {session_id}")
            return events
            
        # Query events for this session
        # This query assumes we're filtering by the goal_id field since it often contains the session_id
        # You may need to adjust this based on how sessions are tracked in your data model
        query = session.query(MemoryEvent).filter(
            MemoryEvent.goal_id == session_uuid
        ).order_by(MemoryEvent.timestamp.asc())
        
        # Alternative query method if we store session_id in meta data
        # query = session.query(MemoryEvent).filter(
        #    MemoryEvent.meta.contains({"session_id": session_id})
        # ).order_by(MemoryEvent.timestamp.asc())
        
        db_events = query.all()
        
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
        
        return events
    except Exception as e:
        logger.error(f"Error retrieving session events: {e}")
        return events
    finally:
        session.close()

def generate_markdown_log(session_id: str, events: List[Dict[str, Any]]) -> str:
    """
    Generate markdown log from events
    
    Args:
        session_id: The session ID
        events: The session events
        
    Returns:
        Markdown log content
    """
    # Generate markdown header
    md = f"# AQLON Session Log: {session_id}\n\n"
    md += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    md += f"Total Events: {len(events)}\n\n"
    md += "---\n\n"
    
    # Generate markdown for each event
    for idx, event in enumerate(events):
        timestamp_str = event.get("timestamp", "Unknown Time")
        timestamp_display = timestamp_str.replace("T", " ").split(".")[0] if timestamp_str != "Unknown Time" else timestamp_str
        
        md += f"## Event {idx + 1} - {timestamp_display}\n\n"
        
        # Add agent action
        if event.get("agent_action"):
            md += f"### Action\n```\n{event['agent_action']}\n```\n\n"
        
        # Add vision state (if not too large)
        if event.get("vision_state"):
            vision_state = event["vision_state"]
            if len(vision_state) > 1000:
                vision_state = vision_state[:1000] + "... (truncated)"
            md += f"### Vision State\n```json\n{vision_state}\n```\n\n"
        
        # Add terminal output
        if event.get("terminal_output"):
            terminal_output = event["terminal_output"]
            if len(terminal_output) > 1000:
                terminal_output = terminal_output[:1000] + "... (truncated)"
            md += f"### Terminal Output\n```\n{terminal_output}\n```\n\n"
        
        # Add notes
        if event.get("notes"):
            md += f"### Notes\n{event['notes']}\n\n"
        
        # Add metadata (if available)
        if event.get("meta"):
            try:
                meta_display = json.dumps(event["meta"], indent=2) if isinstance(event["meta"], dict) else str(event["meta"])
                md += f"### Metadata\n```json\n{meta_display}\n```\n\n"
            except Exception as e:
                md += f"### Metadata\nError serializing metadata: {e}\n\n"
        
        md += "---\n\n"
    
    return md

def generate_html_log(session_id: str, events: List[Dict[str, Any]]) -> str:
    """
    Generate HTML log from events
    
    Args:
        session_id: The session ID
        events: The session events
        
    Returns:
        HTML log content
    """
    # Generate HTML header
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>AQLON Session Log: {session_id}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }}
        .header {{ background-color: #f0f0f0; padding: 10px; border-radius: 5px; }}
        .event {{ margin-bottom: 30px; border: 1px solid #ddd; padding: 15px; border-radius: 5px; }}
        .event-header {{ background-color: #eaeaea; padding: 10px; margin-bottom: 15px; }}
        .section {{ margin-top: 15px; }}
        .section-title {{ font-weight: bold; margin-bottom: 5px; }}
        pre {{ background-color: #f8f8f8; padding: 10px; border-radius: 3px; overflow-x: auto; }}
        .timestamp {{ color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>AQLON Session Log: {session_id}</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Total Events: {len(events)}</p>
    </div>
"""
    
    # Generate HTML for each event
    for idx, event in enumerate(events):
        timestamp_str = event.get("timestamp", "Unknown Time")
        timestamp_display = timestamp_str.replace("T", " ").split(".")[0] if timestamp_str != "Unknown Time" else timestamp_str
        
        html += f"""
    <div class="event">
        <div class="event-header">
            <h2>Event {idx + 1}</h2>
            <p class="timestamp">{timestamp_display}</p>
        </div>
"""
        
        # Add agent action
        if event.get("agent_action"):
            html += f"""
        <div class="section">
            <div class="section-title">Action</div>
            <pre>{event['agent_action']}</pre>
        </div>
"""
        
        # Add vision state (if not too large)
        if event.get("vision_state"):
            vision_state = event["vision_state"]
            if len(vision_state) > 1000:
                vision_state = vision_state[:1000] + "... (truncated)"
            html += f"""
        <div class="section">
            <div class="section-title">Vision State</div>
            <pre>{vision_state}</pre>
        </div>
"""
        
        # Add terminal output
        if event.get("terminal_output"):
            terminal_output = event["terminal_output"]
            if len(terminal_output) > 1000:
                terminal_output = terminal_output[:1000] + "... (truncated)"
            html += f"""
        <div class="section">
            <div class="section-title">Terminal Output</div>
            <pre>{terminal_output}</pre>
        </div>
"""
        
        # Add notes
        if event.get("notes"):
            html += f"""
        <div class="section">
            <div class="section-title">Notes</div>
            <p>{event['notes']}</p>
        </div>
"""
        
        # Add metadata (if available)
        if event.get("meta"):
            try:
                meta_display = json.dumps(event["meta"], indent=2) if isinstance(event["meta"], dict) else str(event["meta"])
                html += f"""
        <div class="section">
            <div class="section-title">Metadata</div>
            <pre>{meta_display}</pre>
        </div>
"""
            except Exception as e:
                html += f"""
        <div class="section">
            <div class="section-title">Metadata</div>
            <p>Error serializing metadata: {str(e)}</p>
        </div>
"""
        
        html += "    </div>\n"
    
    # Close HTML
    html += """
</body>
</html>
"""
    
    return html

def copy_session_screenshots(session_id: str, output_dir: Path) -> None:
    """
    Copy session screenshots to the output directory
    
    Args:
        session_id: The session ID
        output_dir: The output directory
    """
    # Create screenshots directory
    screenshots_dir = output_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)
    
    # Check for screenshot paths in database
    events = get_session_events(session_id)
    
    for event in events:
        # Look for screenshot paths in meta or vision_state
        meta = event.get("meta", {})
        
        # Check for screenshot paths in meta
        if isinstance(meta, dict) and "screenshot_path" in meta:
            screenshot_path = meta["screenshot_path"]
            if os.path.exists(screenshot_path):
                # Copy the screenshot
                filename = os.path.basename(screenshot_path)
                destination = screenshots_dir / filename
                
                try:
                    with open(screenshot_path, "rb") as src, open(destination, "wb") as dst:
                        dst.write(src.read())
                except Exception as e:
                    logger.warning(f"Error copying screenshot {screenshot_path}: {e}")
        
        # Also check for screenshot paths in vision_state (might be JSON string)
        vision_state = event.get("vision_state", "")
        if isinstance(vision_state, str) and vision_state:
            try:
                vision_data = json.loads(vision_state)
                if isinstance(vision_data, dict) and "screenshot_path" in vision_data:
                    screenshot_path = vision_data["screenshot_path"]
                    if os.path.exists(screenshot_path):
                        # Copy the screenshot
                        filename = os.path.basename(screenshot_path)
                        destination = screenshots_dir / filename
                        
                        try:
                            with open(screenshot_path, "rb") as src, open(destination, "wb") as dst:
                                dst.write(src.read())
                        except Exception as e:
                            logger.warning(f"Error copying screenshot {screenshot_path}: {e}")
            except json.JSONDecodeError:
                # Not a JSON string, ignore
                pass
