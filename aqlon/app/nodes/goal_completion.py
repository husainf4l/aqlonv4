"""
Goal Completion Check Module for AQLon agent

This module provides functionality for checking if a goal has been completed successfully,
using smart success/failure detection based on various data sources:
1. Direct success flags
2. Action results
3. Vision state analysis
4. Terminal output analysis 
5. Goal-specific verification criteria
"""

import re
from typing import Dict, Any, Optional, List, Tuple
import json
from openai import OpenAI
from datetime import datetime

from app.logger import logger
from app.state import AgentState
from app.settings import settings
from app.memory import memory

# Initialize OpenAI client using settings for LLM-based success detection
client = OpenAI(api_key=settings.openai_api_key)

# System prompt for goal completion LLM
GOAL_COMPLETION_SYSTEM_PROMPT = """
You are the Goal Completion Detector for the AQLON agent. Your task is to analyze the current state and determine if the agent's goal has been successfully completed.

Analyze:
1. The original goal
2. The current state of the environment (vision)
3. Results of recent actions
4. Terminal output (if relevant)
5. Any relevant metrics or data

Rate the goal completion on a scale from 0.0 to 1.0 where:
- 0.0: Complete failure, goal not achieved at all
- 0.5: Partial success, goal partially achieved
- 1.0: Complete success, goal fully achieved

Provide a short explanation of your reasoning.

Your response must be JSON with this format:
{
    "success_score": 0.0-1.0,
    "status": "completed"|"failed"|"in_progress",
    "explanation": "explanation of the score"
}
"""

class CompletionCriterion:
    """Base class for goal completion criteria"""
    def check(self, state: AgentState) -> Tuple[bool, float, str]:
        """
        Check if criterion is met
        Returns: (is_met, confidence, explanation)
        """
        raise NotImplementedError("Subclasses must implement check method")

class ExplicitFlagCriterion(CompletionCriterion):
    """Checks explicit success/failure flags in state"""
    def check(self, state: AgentState) -> Tuple[bool, float, str]:
        # Check for explicit success flag
        if hasattr(state, "goal_complete") and state.goal_complete:
            return True, 1.0, "Explicit goal_complete flag is set to True"
            
        # Check for explicit failure flag
        if hasattr(state, "goal_failed") and state.goal_failed:
            return False, 1.0, f"Explicit goal_failed flag is set to True: {getattr(state, 'goal_failed_reason', 'No reason given')}"
        
        # No explicit flags
        return None, 0.0, "No explicit success/failure flags found"

class ActionResultCriterion(CompletionCriterion):
    """Checks action results for success/failure indicators"""
    def check(self, state: AgentState) -> Tuple[bool, float, str]:
        action_result = getattr(state, "action_result", None)
        if not action_result:
            return None, 0.0, "No action_result found"
            
        # Check for common success patterns in action result
        success_patterns = [
            r"success(fully)?", r"completed", r"clicked", r"found", 
            r"created", r"added", r"installed"
        ]
        
        # Check for common failure patterns in action result
        failure_patterns = [
            r"fail(ed|ure)?", r"error", r"exception", r"not found",
            r"invalid", r"missing", r"unable"
        ]
        
        # Check for success patterns
        for pattern in success_patterns:
            if re.search(pattern, action_result, re.IGNORECASE):
                return True, 0.7, f"Action result indicates success: {action_result}"
        
        # Check for failure patterns
        for pattern in failure_patterns:
            if re.search(pattern, action_result, re.IGNORECASE):
                return False, 0.7, f"Action result indicates failure: {action_result}"
        
        # No strong indicators
        return None, 0.0, "No clear success/failure indicators in action result"

class VisionStateCriterion(CompletionCriterion):
    """Analyzes vision state for goal completion indicators"""
    def check(self, state: AgentState) -> Tuple[bool, float, str]:
        vision_state = getattr(state, "vision_state", None)
        vision_llm_summary = getattr(state, "vision_llm_summary", None)
        
        if not vision_state and not vision_llm_summary:
            return None, 0.0, "No vision data available"
            
        # Use vision LLM summary if available as it's more reliable
        if vision_llm_summary:
            # Check for success indicators in vision LLM summary
            success_patterns = [
                r"success(fully)?", r"completed", r"done", r"finished",
                r"created", r"installed", r"ready"
            ]
            
            # Check for failure indicators in vision LLM summary
            failure_patterns = [
                r"fail(ed|ure)?", r"error", r"exception", r"not found",
                r"invalid", r"missing", r"unable"
            ]
            
            # Check for success patterns
            for pattern in success_patterns:
                if re.search(pattern, vision_llm_summary, re.IGNORECASE):
                    return True, 0.6, f"Vision LLM summary indicates success: {vision_llm_summary[:100]}"
            
            # Check for failure patterns
            for pattern in failure_patterns:
                if re.search(pattern, vision_llm_summary, re.IGNORECASE):
                    return False, 0.6, f"Vision LLM summary indicates failure: {vision_llm_summary[:100]}"
                    
        # No strong indicators or no vision data
        return None, 0.0, "No clear success/failure indicators in vision data"

class TerminalOutputCriterion(CompletionCriterion):
    """Analyzes terminal output for goal completion indicators"""
    def check(self, state: AgentState) -> Tuple[bool, float, str]:
        terminal_output = getattr(state, "terminal_output", None)
        if not terminal_output:
            return None, 0.0, "No terminal output available"
        
        # Check for common success patterns in terminal output
        success_patterns = [
            r"success(fully)?", r"completed", r"saved", r"created", r"installed",
            r"BUILD SUCCESS", r"PASSED", r"OK", r"100%"
        ]
        
        # Check for common failure patterns in terminal output
        failure_patterns = [
            r"fail(ed|ure)?", r"error", r"exception", r"not found",
            r"invalid", r"missing", r"unable", r"FAILED", r"BUILD FAILED",
            r"Traceback", r"Exception", r"Error:", r"fatal:"
        ]
        
        # Check for success patterns
        for pattern in success_patterns:
            if re.search(pattern, terminal_output, re.IGNORECASE):
                return True, 0.8, f"Terminal output indicates success: {pattern}"
        
        # Check for failure patterns
        for pattern in failure_patterns:
            if re.search(pattern, terminal_output, re.IGNORECASE):
                return False, 0.8, f"Terminal output indicates failure: {pattern}"
        
        # No strong indicators
        return None, 0.0, "No clear success/failure indicators in terminal output"

class UIElementCriterion(CompletionCriterion):
    """Checks for specific UI elements that indicate success/failure"""
    def check(self, state: AgentState) -> Tuple[bool, float, str]:
        ui_elements = getattr(state, "ui_elements", None)
        text_elements = getattr(state, "text_elements", None)
        
        if not ui_elements and not text_elements:
            return None, 0.0, "No UI element data available"
        
        # Success text patterns to look for in UI elements
        success_patterns = [
            r"success(fully)?", r"completed", r"done", r"finished",
            r"congrats", r"congratulations", r"thank you"
        ]
        
        # Failure text patterns to look for in UI elements
        failure_patterns = [
            r"fail(ed|ure)?", r"error", r"exception", r"not found",
            r"invalid", r"retry", r"try again"
        ]
        
        # Check text elements first as they're most reliable
        if text_elements:
            for element in text_elements:
                element_text = element.get("text", "")
                
                # Check for success patterns
                for pattern in success_patterns:
                    if re.search(pattern, element_text, re.IGNORECASE):
                        return True, 0.7, f"UI text element indicates success: {element_text[:100]}"
                
                # Check for failure patterns
                for pattern in failure_patterns:
                    if re.search(pattern, element_text, re.IGNORECASE):
                        return False, 0.7, f"UI text element indicates failure: {element_text[:100]}"
        
        # No indicators found
        return None, 0.0, "No clear success/failure indicators in UI elements"

class LLMCompletionCriterion(CompletionCriterion):
    """Uses LLM to evaluate goal completion based on all available data"""
    def check(self, state: AgentState) -> Tuple[bool, float, str]:
        goal = getattr(state, "goal", None)
        if not goal:
            return None, 0.0, "No goal specified"
        
        try:
            # Gather relevant state information
            context = {
                "goal": goal,
                "vision_state": getattr(state, "vision_state", "")[:500],  # Limit size
                "vision_llm_summary": getattr(state, "vision_llm_summary", ""),
                "action_result": getattr(state, "action_result", ""),
                "terminal_output": getattr(state, "terminal_output", "")[-500:] if getattr(state, "terminal_output", "") else "",  # Last 500 chars
                "last_action": getattr(state, "last_action", ""),
                "steps_completed": getattr(state, "steps_completed", []),
            }
            
            # Prepare user content
            user_content = f"""
Goal: {context['goal']}

Current vision state summary: {context['vision_llm_summary']}

Latest action result: {context['action_result']}

Terminal output: {context['terminal_output']}

Steps completed: {', '.join(context['steps_completed']) if context['steps_completed'] else 'None'}

Has this goal been successfully completed? Rate the success on a scale from 0.0 to 1.0.
"""
            
            # Call LLM for evaluation
            response = client.chat.completions.create(
                model="gpt-4",  # Using a powerful model for better evaluation
                messages=[
                    {"role": "system", "content": GOAL_COMPLETION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=500,
                temperature=0.2
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                success_score = float(result.get("success_score", 0.0))
                status = result.get("status", "in_progress")
                explanation = result.get("explanation", "No explanation provided")
                
                # Determine success based on score and status
                is_success = None
                if status == "completed" or success_score > 0.8:
                    is_success = True
                elif status == "failed" or success_score < 0.2:
                    is_success = False
                
                return is_success, success_score, explanation
                
            except json.JSONDecodeError:
                # Fallback if JSON parsing failed - look for keywords
                if "success" in result_text.lower() or "completed" in result_text.lower():
                    return True, 0.7, f"LLM indicates success: {result_text[:100]}"
                elif "fail" in result_text.lower() or "not achieved" in result_text.lower():
                    return False, 0.3, f"LLM indicates failure: {result_text[:100]}"
                    
                return None, 0.5, f"Unclear LLM evaluation (non-JSON): {result_text[:100]}"
                
        except Exception as e:
            logger.error(f"LLM completion criterion error: {e}")
            return None, 0.0, f"Error in LLM evaluation: {e}"

class GoalCompletionChecker:
    """Checks if a goal has been completed using multiple criteria"""
    def __init__(self):
        # Default criteria
        self.criteria = [
            ExplicitFlagCriterion(),
            ActionResultCriterion(),
            VisionStateCriterion(),
            TerminalOutputCriterion(),
            UIElementCriterion(),
            LLMCompletionCriterion()
        ]
        
        # Confidence threshold for automated decision
        self.confidence_threshold = 0.7
        
        # Weights for different criteria
        self.criterion_weights = {
            "ExplicitFlagCriterion": 1.0,
            "ActionResultCriterion": 0.7,
            "VisionStateCriterion": 0.6,
            "TerminalOutputCriterion": 0.8,
            "UIElementCriterion": 0.7,
            "LLMCompletionCriterion": 0.9
        }
    
    def check_completion(self, state: AgentState) -> Dict[str, Any]:
        """
        Check if the current goal has been completed
        Returns a result dictionary with details
        """
        goal = getattr(state, "goal", None)
        if not goal:
            return {
                "completed": False,
                "success": False,
                "confidence": 1.0,
                "success_score": 0.0,
                "explanation": "No goal specified",
                "details": []
            }
        
        # Apply all criteria
        results = []
        for criterion in self.criteria:
            criterion_name = criterion.__class__.__name__
            weight = self.criterion_weights.get(criterion_name, 0.5)
            
            try:
                is_success, confidence, explanation = criterion.check(state)
                
                # Store result if criterion returned a usable result
                if is_success is not None:
                    results.append({
                        "criterion": criterion_name,
                        "success": is_success,
                        "confidence": confidence,
                        "weight": weight,
                        "explanation": explanation,
                        "weighted_confidence": confidence * weight
                    })
            except Exception as e:
                logger.error(f"Error in {criterion_name}: {e}")
        
        # If no criteria gave usable results
        if not results:
            return {
                "completed": False,
                "success": False,
                "confidence": 0.0,
                "success_score": 0.0,
                "explanation": "Insufficient data to determine goal completion",
                "details": []
            }
        
        # Aggregate results
        success_votes = sum(1 for r in results if r["success"])
        failure_votes = sum(1 for r in results if not r["success"])
        
        # Calculate weighted confidence scores
        success_confidence = sum(r["weighted_confidence"] for r in results if r["success"])
        failure_confidence = sum(r["weighted_confidence"] for r in results if not r["success"])
        total_confidence = success_confidence + failure_confidence
        
        # Determine overall result
        is_completed = (success_votes > 0 or failure_votes > 0)
        is_success = success_votes > failure_votes
        
        # Calculate normalized confidence (0-1)
        if total_confidence > 0:
            if is_success:
                confidence = success_confidence / total_confidence
            else:
                confidence = failure_confidence / total_confidence
        else:
            confidence = 0.0
            
        # Calculate success score (0-1)
        if total_confidence > 0:
            success_score = success_confidence / (success_confidence + failure_confidence)
        else:
            success_score = 0.0
        
        # Generate explanation
        if is_completed and is_success:
            explanation = f"Goal completed successfully with {confidence:.2f} confidence"
        elif is_completed and not is_success:
            explanation = f"Goal failed with {confidence:.2f} confidence"
        else:
            explanation = "Goal completion status unclear"
        
        # Return detailed result
        return {
            "completed": is_completed,
            "success": is_success if is_completed else False,
            "confidence": confidence,
            "success_score": success_score,
            "explanation": explanation,
            "details": results
        }

def goal_completion_node(state: AgentState) -> AgentState:
    """
    Node for checking goal completion in the agent workflow
    """
    logger.info("[GoalCompletionNode] Checking if goal is complete")
    
    try:
        # Skip if no goal
        if not getattr(state, "goal", None) or not getattr(state, "goal_id", None):
            logger.info("[GoalCompletionNode] No goal to check")
            return state
        
        # Check if goal is explicitly marked as complete/failed
        if getattr(state, "goal_complete", False) or getattr(state, "goal_failed", False):
            logger.info("[GoalCompletionNode] Goal explicitly marked as complete/failed")
            
            # If goal is completed, update the goal in memory
            if getattr(state, "goal_complete", False):
                memory.mark_goal_complete(
                    goal_id=state.goal_id, 
                    success_score=1.0,
                    metadata={"completion_time": datetime.now().isoformat()}
                )
            
            # If goal is failed, update the goal in memory
            if getattr(state, "goal_failed", False):
                memory.mark_goal_failed(
                    goal_id=state.goal_id,
                    success_score=0.0,
                    metadata={
                        "failure_time": datetime.now().isoformat(),
                        "reason": getattr(state, "goal_failed_reason", "Unknown reason")
                    }
                )
                
            return state
        
        # Check goal completion
        checker = GoalCompletionChecker()
        completion_result = checker.check_completion(state)
        
        # Store result in state
        state.goal_completion_result = completion_result
        
        # If completion status determined with high confidence, update goal status
        if completion_result["completed"] and completion_result["confidence"] >= checker.confidence_threshold:
            if completion_result["success"]:
                # Mark goal as complete
                state.goal_complete = True
                memory.mark_goal_complete(
                    goal_id=state.goal_id, 
                    success_score=completion_result["success_score"],
                    metadata={
                        "completion_time": datetime.now().isoformat(),
                        "completion_details": completion_result
                    }
                )
                logger.info(f"[GoalCompletionNode] Goal marked as complete: {completion_result['explanation']}")
            else:
                # Mark goal as failed
                state.goal_failed = True
                state.goal_failed_reason = completion_result["explanation"]
                memory.mark_goal_failed(
                    goal_id=state.goal_id,
                    success_score=completion_result["success_score"],
                    metadata={
                        "failure_time": datetime.now().isoformat(),
                        "failure_details": completion_result
                    }
                )
                logger.info(f"[GoalCompletionNode] Goal marked as failed: {completion_result['explanation']}")
    
    except Exception as e:
        logger.error(f"Goal completion node error: {e}")
    
    return state