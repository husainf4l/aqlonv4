"""
Safety module for AQLon agent - prevents execution of potentially unsafe actions
"""

import re
from typing import Dict, List, Tuple, Optional, Any, Union
import json

from app.logger import logger
from app.state import AgentState

class SafetyManager:
    def __init__(self):
        # Default list of unsafe terminal commands/patterns
        self.unsafe_commands = [
            # File system destructive operations
            r"rm\s+(-[rf]\s+)*(/|~/|\${?HOME}?)",   # Remove root or home
            r"chmod\s+-[R]*.+\s+(/|~/|\${?HOME}?)", # Recursive chmod on root/home
            r"chown\s+-[R]*.+\s+(/|~/|\${?HOME}?)", # Recursive chown on root/home
            
            # System modification
            r"mkfs",                     # Format filesystems
            r"dd\s+.*of=/dev/([sh]d[a-z]|disk\d+)", # Raw disk writes
            r"(shutdown|reboot|halt)",   # System shutdown commands
            
            # Network attacks
            r"nmap\s+-[p]\s+.*",         # Port scanning
            
            # Potentially destructive commands
            r":(){:|\:&};:",             # Fork bomb
            r"echo.+[|]\s*ssh",          # SSH key overwriting
            r">\s*/etc/passwd",          # Overwrite passwd
            r">\s*/etc/shadow",          # Overwrite shadow
            
            # Cryptocurrency mining/malware
            r"(wget|curl)\s+.*(\.sh)\s+[|]\s*(bash|sh)", # Piping scripts to shell
            
            # Dangerous Python operations
            r"os\.system\(\s*['\"]rm\s+-[rf]",
            r"shutil\.rmtree\(\s*['\"]?/",
            r"__import__\(['\"]os['\"].*system",
        ]
        
        # Default list of unsafe code patterns
        self.unsafe_code_patterns = [
            # Remote code execution
            r"eval\s*\(.*(?:request|input)",
            r"exec\s*\(.*(?:request|input)",
            
            # Command injection
            r"subprocess\.(?:call|Popen|run)\s*\(.*\+.*(?:request|input)",
            r"os\.(?:system|popen)\s*\(.*\+.*(?:request|input)",
            
            # SQL Injection
            r"(?:execute|executemany)\s*\(.*\+.*(?:request|input)",
            r"(?:execute|executemany)\s*\(f['\"].*\{.*(?:request|input)",
            
            # Deserialization vulnerabilities
            r"(?:pickle|yaml|marshal)\.loads\s*\(.*(?:request|input)",
            
            # File operations with user input
            r"open\s*\(.*\+.*(?:request|input)",
            
            # Network connections with dynamic data
            r"(?:urlopen|Request)\s*\(.*\+.*(?:request|input)",
        ]
        
        # Custom rules added at runtime
        self.custom_unsafe_patterns = []
        
        # Safety overrides (temporary disabling of specific rules)
        self.overrides = {}
        
        # Safety level (0=off, 1=warn, 2=block)
        self.safety_level = 2
        
        logger.info("Safety manager initialized with default protection rules")
    
    def add_unsafe_pattern(self, pattern: str, description: str = "") -> None:
        """Add a custom unsafe pattern to block"""
        self.custom_unsafe_patterns.append({
            "pattern": pattern,
            "description": description,
            "added_at": None  # Could add timestamp
        })
        logger.info(f"Added custom unsafe pattern: {pattern}")
    
    def set_safety_level(self, level: int) -> None:
        """Set the safety level (0=off, 1=warn, 2=block)"""
        if level not in [0, 1, 2]:
            logger.error(f"Invalid safety level: {level}. Must be 0, 1, or 2.")
            return
        
        old_level = self.safety_level
        self.safety_level = level
        logger.info(f"Safety level changed from {old_level} to {level}")
    
    def add_override(self, pattern_id: str, duration_seconds: int = 300) -> None:
        """Add a temporary override for a safety rule"""
        # In a real implementation, this would store the override with an expiration
        self.overrides[pattern_id] = {
            "expires_at": None  # Would add actual expiration time
        }
        logger.warning(f"Safety override added for pattern {pattern_id} for {duration_seconds} seconds")
    
    def is_command_safe(self, command: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a terminal command is safe to execute
        Returns: (is_safe, reason_if_unsafe)
        """
        if self.safety_level == 0:
            return True, None
        
        # Check against patterns
        for pattern in self.unsafe_commands:
            if re.search(pattern, command, re.IGNORECASE):
                reason = f"Command matches unsafe pattern: {pattern}"
                logger.warning(f"Unsafe command detected: {command} - {reason}")
                return False, reason
        
        # Check against custom patterns
        for custom in self.custom_unsafe_patterns:
            if re.search(custom["pattern"], command, re.IGNORECASE):
                reason = custom.get("description") or f"Command matches custom unsafe pattern"
                logger.warning(f"Unsafe command detected: {command} - {reason}")
                return False, reason
        
        return True, None
    
    def is_code_safe(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        Check if code is safe to execute
        Returns: (is_safe, reason_if_unsafe)
        """
        if self.safety_level == 0:
            return True, None
        
        # Check against patterns
        for pattern in self.unsafe_code_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                reason = f"Code matches unsafe pattern: {pattern}"
                logger.warning(f"Unsafe code detected - {reason}")
                return False, reason
        
        return True, None
    
    def handle_unsafe_action(self, action_type: str, action_content: str) -> Dict[str, Any]:
        """
        Handle attempted unsafe actions based on current safety level
        Returns response object with status and information
        """
        # Check if the action is safe
        if action_type == "command":
            is_safe, reason = self.is_command_safe(action_content)
        elif action_type == "code":
            is_safe, reason = self.is_code_safe(action_content)
        else:
            is_safe, reason = False, f"Unknown action type: {action_type}"
        
        # If safe, allow it
        if is_safe:
            return {
                "status": "allowed",
                "message": "Action is safe"
            }
        
        # Handle based on safety level
        if self.safety_level == 1:  # Warn only
            logger.warning(f"Unsafe {action_type} detected but allowed (warn mode): {reason}")
            return {
                "status": "allowed_with_warning",
                "message": f"Potentially unsafe action detected: {reason}",
                "reason": reason
            }
        
        elif self.safety_level == 2:  # Block
            logger.error(f"Blocked unsafe {action_type}: {reason}")
            return {
                "status": "blocked",
                "message": f"Action blocked for safety: {reason}",
                "reason": reason
            }
        
        # This should never happen if safety_level is validated
        return {
            "status": "error",
            "message": f"Invalid safety level: {self.safety_level}"
        }

# Initialize global safety manager
safety_manager = SafetyManager()

def safety_check_node(state: AgentState) -> AgentState:
    """
    Node for checking safety of actions in the agent workflow
    """
    logger.info("[SafetyNode] Checking actions for safety")
    
    try:
        # Get the command/code from state
        agent_action = getattr(state, "agent_action", None)
        
        if not agent_action:
            logger.debug("[SafetyNode] No action to check")
            return state
        
        # Determine action type
        action_type = "command" if agent_action.startswith(("!", "sudo")) else "code"
        action_content = agent_action.lstrip("!") if action_type == "command" else agent_action
        
        # Check safety
        result = safety_manager.handle_unsafe_action(action_type, action_content)
        
        # Store result in state
        state.safety_check_result = result
        
        # Block execution if needed
        if result["status"] == "blocked":
            state.block_execution = True
            state.block_reason = result["reason"]
            logger.warning(f"[SafetyNode] Blocked execution: {result['reason']}")
        
    except Exception as e:
        logger.error(f"Safety node error: {e}")
    
    return state
