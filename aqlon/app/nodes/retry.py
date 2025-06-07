"""
Step-level retry mechanism with exponential backoff for AQLon agent

This module provides functionality for retrying failed steps in the agent workflow
with an exponential backoff strategy to avoid overwhelming the system.
"""

import time
import random
from datetime import datetime
from typing import Dict, Any, Optional, Callable, List, Tuple
import uuid

from app.logger import logger
from app.state import AgentState

class RetryState:
    """Tracks retry state for a step"""
    def __init__(self, 
                step_id: str,
                max_retries: int = 3,
                base_delay: float = 1.0,
                max_delay: float = 30.0,
                jitter: bool = True):
        self.step_id = step_id
        self.attempts = 0
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.first_attempt_time = datetime.now()
        self.last_attempt_time = None
        self.next_attempt_time = None
        self.errors: List[Dict[str, Any]] = []
    
    @property
    def should_retry(self) -> bool:
        """Check if the step should be retried"""
        return self.attempts < self.max_retries
    
    @property
    def can_retry_now(self) -> bool:
        """Check if enough time has passed for the next retry"""
        if not self.next_attempt_time:
            return True
        return datetime.now() >= self.next_attempt_time
    
    def record_attempt(self, error: Optional[str] = None) -> None:
        """
        Record an attempt and calculate next retry time
        using exponential backoff with jitter
        """
        self.attempts += 1
        self.last_attempt_time = datetime.now()
        
        if error:
            self.errors.append({
                "attempt": self.attempts,
                "timestamp": self.last_attempt_time.isoformat(),
                "error": error
            })
        
        # Calculate delay with exponential backoff
        delay = min(self.base_delay * (2 ** (self.attempts - 1)), self.max_delay)
        
        # Add jitter if enabled (±25% randomness)
        if self.jitter:
            jitter_factor = 1.0 + random.uniform(-0.25, 0.25)
            delay *= jitter_factor
        
        # Set next attempt time
        self.next_attempt_time = datetime.now().timestamp() + delay
        
        logger.info(
            f"Recorded attempt {self.attempts}/{self.max_retries} for step {self.step_id}. "
            f"Next attempt in {delay:.2f}s"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert retry state to dictionary"""
        return {
            "step_id": self.step_id,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "first_attempt_time": self.first_attempt_time.isoformat(),
            "last_attempt_time": self.last_attempt_time.isoformat() if self.last_attempt_time else None,
            "next_attempt_time": datetime.fromtimestamp(self.next_attempt_time).isoformat() if self.next_attempt_time else None,
            "errors": self.errors,
            "can_retry": self.should_retry,
        }

class RetryManager:
    """Manages retries for multiple steps"""
    def __init__(self):
        self.retries: Dict[str, RetryState] = {}
    
    def get_retry_state(self, step_id: str) -> Optional[RetryState]:
        """Get retry state for a step"""
        return self.retries.get(step_id)
    
    def start_retry_tracking(self, 
                           step_id: Optional[str] = None, 
                           max_retries: int = 3,
                           base_delay: float = 1.0,
                           max_delay: float = 30.0) -> RetryState:
        """
        Start tracking retries for a step
        If step_id is not provided, a UUID will be generated
        """
        if not step_id:
            step_id = str(uuid.uuid4())
            
        retry_state = RetryState(
            step_id=step_id,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay
        )
        
        self.retries[step_id] = retry_state
        return retry_state
    
    def cleanup_old_retries(self, max_age_seconds: int = 3600) -> int:
        """
        Remove retry states older than the specified age
        Returns the number of entries removed
        """
        now = datetime.now().timestamp()
        to_remove = []
        
        for step_id, retry_state in self.retries.items():
            # Calculate age of the retry state
            first_attempt_time = retry_state.first_attempt_time.timestamp()
            age = now - first_attempt_time
            
            if age > max_age_seconds:
                to_remove.append(step_id)
        
        # Remove old entries
        for step_id in to_remove:
            del self.retries[step_id]
            
        return len(to_remove)
        
# Global retry manager instance
retry_manager = RetryManager()

def with_retry(func: Callable[[AgentState], AgentState]) -> Callable[[AgentState], AgentState]:
    """
    Decorator for agent node functions to add retry capability
    Example usage:
    
    @with_retry
    def my_node(state: AgentState) -> AgentState:
        # Node implementation
    """
    def wrapper(state: AgentState) -> AgentState:
        # Get step ID from state or generate one
        step_id = getattr(state, "step_id", None) or str(uuid.uuid4())
        
        # Set step ID in state if not already set
        if not hasattr(state, "step_id") or not state.step_id:
            state.step_id = step_id
        
        # Check if max retries is specified in state
        max_retries = getattr(state, "max_retries", 3)
        base_delay = getattr(state, "retry_base_delay", 1.0)
        max_delay = getattr(state, "retry_max_delay", 30.0)
        
        # Get or create retry state
        retry_state = retry_manager.get_retry_state(step_id)
        if not retry_state:
            retry_state = retry_manager.start_retry_tracking(
                step_id=step_id,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay
            )
        
        # Record attempt
        retry_state.record_attempt()
        
        try:
            # Execute the wrapped function
            result_state = func(state)
            
            # Check for step failure
            step_failed = getattr(result_state, "step_failed", False)
            if step_failed:
                error_msg = getattr(result_state, "step_error", "Unknown error")
                
                # Handle retry logic
                if retry_state.should_retry:
                    # Record error
                    retry_state.errors.append({
                        "attempt": retry_state.attempts,
                        "timestamp": datetime.now().isoformat(),
                        "error": error_msg
                    })
                    
                    # Set retry information in state
                    result_state.retry_info = retry_state.to_dict()
                    result_state.retrying = True
                    result_state.retry_count = retry_state.attempts
                    
                    logger.info(f"Step {step_id} failed, will retry ({retry_state.attempts}/{max_retries})")
                else:
                    # No more retries available
                    result_state.retry_info = retry_state.to_dict()
                    result_state.retrying = False
                    result_state.max_retries_reached = True
                    
                    logger.warning(f"Step {step_id} failed after {retry_state.attempts} attempts, no more retries")
            else:
                # Step succeeded
                result_state.retry_info = retry_state.to_dict() if retry_state.attempts > 1 else None
            
            return result_state
            
        except Exception as e:
            # Handle exceptions by recording the error
            logger.error(f"Error in step {step_id}: {e}")
            
            # Record error in retry state
            retry_state.errors.append({
                "attempt": retry_state.attempts,
                "timestamp": datetime.now().isoformat(),
                "error": str(e)
            })
            
            # Update state with error and retry information
            state.step_failed = True
            state.step_error = str(e)
            state.retry_info = retry_state.to_dict()
            
            # Check if we can retry
            if retry_state.should_retry:
                state.retrying = True
                state.retry_count = retry_state.attempts
            else:
                state.retrying = False
                state.max_retries_reached = True
            
            return state
    
    # Update wrapper metadata
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    
    return wrapper

def retry_node(state: AgentState) -> AgentState:
    """
    Node for managing retries in the agent workflow
    This node checks if a retry is needed and waits if necessary
    """
    logger.info("[RetryNode] Checking if retry is needed")
    
    try:
        # Check if retry is in progress
        retrying = getattr(state, "retrying", False)
        retry_info = getattr(state, "retry_info", None)
        
        if retrying and retry_info:
            step_id = retry_info.get("step_id")
            
            # Get retry state
            retry_state = retry_manager.get_retry_state(step_id)
            
            if retry_state:
                # Check if we need to wait before retrying
                if not retry_state.can_retry_now:
                    # Calculate wait time
                    wait_time = retry_state.next_attempt_time - datetime.now().timestamp()
                    if wait_time > 0:
                        logger.info(f"[RetryNode] Waiting {wait_time:.2f}s before retry {retry_state.attempts}/{retry_state.max_retries}")
                        time.sleep(wait_time)
                
                # Update state with latest retry info
                state.retry_info = retry_state.to_dict()
                logger.info(f"[RetryNode] Ready for retry {retry_state.attempts}/{retry_state.max_retries}")
            else:
                logger.warning(f"[RetryNode] Retry state not found for step {step_id}")
                state.retrying = False
        
        # Clean up old retry states occasionally
        retry_manager.cleanup_old_retries()
        
    except Exception as e:
        logger.error(f"Retry node error: {e}")
    
    return state
