"""
Manual override module for AQLon agent

This module allows users to manually override agent behavior:
1. Safety restrictions
2. Goal prioritization
3. Action execution
4. Specific node behavior
"""

from typing import Dict, List, Any, Optional
import uuid
from datetime import datetime, timedelta

from app.logger import logger
from app.state import AgentState

class Override:
    """Represents a single override command"""
    def __init__(self, 
                override_id: uuid.UUID,
                target: str, 
                action: str,
                parameters: Optional[Dict[str, Any]] = None,
                duration_seconds: int = 300,  # Default 5 minutes
                reason: str = ""):
        self.id = override_id
        self.target = target  # What system is being overridden
        self.action = action  # What override action to take
        self.parameters = parameters or {}  # Additional parameters
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(seconds=duration_seconds)
        self.reason = reason
        self.applied = False
        self.applied_at = None
        self.revoked = False
        self.revoked_at = None
    
    def is_expired(self) -> bool:
        """Check if this override has expired"""
        return datetime.now() > self.expires_at
    
    def mark_applied(self) -> None:
        """Mark this override as applied"""
        self.applied = True
        self.applied_at = datetime.now()
    
    def revoke(self) -> None:
        """Revoke this override"""
        self.revoked = True
        self.revoked_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "id": str(self.id),
            "target": self.target,
            "action": self.action,
            "parameters": self.parameters,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "reason": self.reason,
            "applied": self.applied,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None
        }

class ManualOverrideManager:
    """Manages manual overrides for various agent systems"""
    
    def __init__(self):
        self.overrides: Dict[uuid.UUID, Override] = {}
        self.active_safety_overrides: Dict[str, uuid.UUID] = {}  # pattern -> override_id
        logger.info("Manual override manager initialized")
    
    def create_override(self, 
                       target: str, 
                       action: str, 
                       parameters: Optional[Dict[str, Any]] = None, 
                       duration_seconds: int = 300,
                       reason: str = "") -> uuid.UUID:
        """Create a new override"""
        override_id = uuid.uuid4()
        override = Override(
            override_id=override_id,
            target=target,
            action=action,
            parameters=parameters,
            duration_seconds=duration_seconds,
            reason=reason
        )
        self.overrides[override_id] = override
        logger.info(f"Created manual override: {target}/{action} (expires in {duration_seconds}s)")
        return override_id
    
    def get_override(self, override_id: uuid.UUID) -> Optional[Override]:
        """Get an override by ID"""
        return self.overrides.get(override_id)
    
    def list_active_overrides(self) -> List[Override]:
        """List all active (non-expired, non-revoked) overrides"""
        return [
            override for override in self.overrides.values() 
            if not override.is_expired() and not override.revoked
        ]
    
    def revoke_override(self, override_id: uuid.UUID) -> bool:
        """Revoke an override"""
        override = self.get_override(override_id)
        if override and not override.revoked:
            override.revoke()
            logger.info(f"Revoked manual override: {override_id}")
            
            # Clean up any references
            for pattern, ref_id in list(self.active_safety_overrides.items()):
                if ref_id == override_id:
                    del self.active_safety_overrides[pattern]
                    
            return True
        return False
    
    def cleanup_expired(self) -> int:
        """Remove expired overrides and return count of removed items"""
        expired_ids = [
            override_id for override_id, override in self.overrides.items() 
            if override.is_expired()
        ]
        
        # Clean up active safety overrides
        for pattern, override_id in list(self.active_safety_overrides.items()):
            if override_id in expired_ids:
                del self.active_safety_overrides[pattern]
        
        # Remove expired overrides
        for override_id in expired_ids:
            if override_id in self.overrides:
                del self.overrides[override_id]
        
        if expired_ids:
            logger.debug(f"Cleaned up {len(expired_ids)} expired overrides")
            
        return len(expired_ids)
    
    def handle_override(self, override_id: uuid.UUID) -> Dict[str, Any]:
        """
        Process an override request and apply it
        Returns result of the operation
        """
        # Clean up expired overrides first
        self.cleanup_expired()
        
        # Get the override
        override = self.get_override(override_id)
        if not override:
            return {"success": False, "message": f"Override {override_id} not found"}
        
        # Check if revoked or expired
        if override.revoked:
            return {"success": False, "message": f"Override {override_id} has been revoked"}
        
        if override.is_expired():
            return {"success": False, "message": f"Override {override_id} has expired"}
        
        # Handle based on target and action
        result = {"success": False, "message": "Unknown override target/action"}
        
        # Handle safety overrides
        if override.target == "safety":
            if override.action == "disable":
                # Import here to avoid circular imports
                from app.nodes.safety import safety_manager
                
                # Get safety level from parameters or use default (0 = off)
                level = override.parameters.get("level", 0)
                duration = override.parameters.get("duration_seconds", 300)
                
                # Save the original level to restore later
                original_level = safety_manager.safety_level
                override.parameters["original_level"] = original_level
                
                # Apply the override
                safety_manager.set_safety_level(level)
                
                # Register a timer to revert this (in a real system)
                # For now, just log it
                logger.warning(
                    f"Safety level temporarily set to {level} for {duration}s "
                    f"(will revert to {original_level})"
                )
                
                override.mark_applied()
                result = {
                    "success": True, 
                    "message": f"Safety level set to {level} for {duration} seconds"
                }
                
            elif override.action == "allow_pattern":
                # Allow a specific safety pattern temporarily
                from app.nodes.safety import safety_manager
                
                pattern = override.parameters.get("pattern")
                if not pattern:
                    return {"success": False, "message": "No pattern specified for override"}
                
                # Store reference to this override
                self.active_safety_overrides[pattern] = override.id
                
                # In a real implementation, this would configure the safety system
                # to ignore this specific pattern temporarily
                logger.warning(f"Temporarily allowing safety pattern: {pattern}")
                
                override.mark_applied()
                result = {
                    "success": True,
                    "message": f"Temporarily allowing pattern: {pattern}"
                }
        
        # Handle goal prioritization overrides
        elif override.target == "prioritization":
            if override.action == "set_priority":
                goal_id = override.parameters.get("goal_id")
                priority = override.parameters.get("priority")
                
                if not goal_id or priority is None:
                    return {"success": False, "message": "Missing goal_id or priority"}
                
                # In a real implementation, update goal priority in database
                logger.info(f"Manually setting goal {goal_id} priority to {priority}")
                
                override.mark_applied()
                result = {
                    "success": True,
                    "message": f"Goal {goal_id} priority set to {priority}"
                }
        
        # Handle agent state overrides
        elif override.target == "agent_state":
            if override.action == "set_field":
                field = override.parameters.get("field")
                value = override.parameters.get("value")
                
                if not field:
                    return {"success": False, "message": "No field specified"}
                
                # This will be handled in the override_node
                override.mark_applied()
                result = {
                    "success": True,
                    "message": f"Will set agent state field '{field}'"
                }
        
        return result

# Global instance for convenient access
override_manager = ManualOverrideManager()

def manual_override_node(state: AgentState) -> AgentState:
    """
    Node for processing manual overrides in the agent workflow
    """
    logger.info("[ManualOverrideNode] Checking for manual overrides")
    
    try:
        # Check if there's a pending override request
        override_id = getattr(state, "pending_override_id", None)
        
        if override_id:
            # Process the override
            result = override_manager.handle_override(override_id)
            state.override_result = result
            
            # Apply state field changes if applicable
            override = override_manager.get_override(override_id)
            if (override and override.target == "agent_state" 
                    and override.action == "set_field" 
                    and override.parameters):
                
                field = override.parameters.get("field")
                value = override.parameters.get("value")
                
                if field:
                    logger.info(f"[ManualOverrideNode] Setting state.{field} = {value}")
                    setattr(state, field, value)
            
            # Clear the pending override
            state.pending_override_id = None
        
        # Clean up any expired overrides
        override_manager.cleanup_expired()
        
    except Exception as e:
        logger.error(f"Manual override node error: {e}")
    
    return state
