"""
Recursive planning module for handling complex multi-goal workflows
"""
from typing import Dict, List, Any, Optional, Tuple
import json
import time
import uuid
from datetime import datetime

from app.logger import logger
from app.state import AgentState
from app.settings import settings
from openai import OpenAI

# Initialize the OpenAI client
client = OpenAI(api_key=settings.openai_api_key)

# System prompts for recursive planning
GOAL_DECOMPOSITION_PROMPT = """
You are the AQLON Recursive Planner, responsible for breaking down complex goals into manageable subgoals.
Given a high-level goal, decompose it into a sequence of subgoals that can be tackled independently.

HIGH-LEVEL GOAL: {goal}

CONTEXT: {context}

Your task is to break down this goal into 2-5 specific subgoals.
Return your response as JSON with this structure:
{{
  "subgoals": [
    {{
      "id": "subgoal-1",
      "text": "First subgoal description",
      "depends_on": [],
      "estimated_complexity": "medium"
    }},
    {{
      "id": "subgoal-2",
      "text": "Second subgoal description",
      "depends_on": ["subgoal-1"],
      "estimated_complexity": "low"
    }},
    ...
  ],
  "execution_order": ["subgoal-1", "subgoal-2", ...],
  "reasoning": "Brief explanation of how you decomposed the goal"
}}

Complexity can be "low", "medium", or "high". The execution_order field should contain a sequence of subgoal IDs that respects the dependencies.
"""

SUBGOAL_PLANNING_PROMPT = """
You are the AQLON Recursive Planner, responsible for creating detailed plans for specific subgoals.
Given a subgoal, create a detailed step-by-step plan to accomplish it.

SUBGOAL: {subgoal}

CONTEXT: {context}

PREVIOUS_SUBGOALS_RESULTS: {previous_results}

Your task is to create a detailed plan for this specific subgoal.
Return your response as JSON with this structure:
{{
  "steps": [
    {{
      "name": "Step name",
      "description": "Detailed step description",
      "estimated_duration": "30s"
    }},
    ...
  ],
  "success_criteria": [
    "Specific observable condition that indicates success",
    ...
  ],
  "fallback_strategies": [
    "Strategy to try if the plan fails",
    ...
  ]
}}

Be specific and concrete about each action the agent should take.
"""

PLAN_INTEGRATION_PROMPT = """
You are the AQLON Recursive Planner, responsible for integrating subplans into a cohesive final plan.
Given multiple subplans for different subgoals, integrate them into a unified plan.

SUBGOALS AND SUBPLANS:
{subplans}

EXECUTION ORDER: {execution_order}

HIGH-LEVEL GOAL: {goal}

Your task is to integrate these subplans into a unified plan, resolving any inconsistencies.
Return your response as JSON with this structure:
{{
  "integrated_steps": [
    {{
      "name": "Step name",
      "description": "Detailed step description",
      "estimated_duration": "30s"
    }},
    ...
  ],
  "execution_flow": {{
    "type": "sequence",  // or "conditional", "parallel"
    "details": {{
      // Additional flow details like conditions or parallel branches
    }}
  }},
  "integration_notes": "Notes about how the subplans were integrated"
}}

Ensure the integrated plan accomplishes the high-level goal and properly sequences the subgoals.
"""

async def decompose_goal(goal: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decompose a complex goal into subgoals
    
    Args:
        goal: The high-level goal
        context: Additional context for decomposition
        
    Returns:
        Decomposition result with subgoals and execution order
    """
    try:
        # Convert context to string for prompt
        context_str = json.dumps(context, indent=2)
        
        response = await client.chat.completions.acreate(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": GOAL_DECOMPOSITION_PROMPT.format(
                    goal=goal,
                    context=context_str
                )},
                {"role": "user", "content": "Decompose this goal into subgoals."}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        decomposition_text = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        try:
            # Look for JSON structure in the response
            start_idx = decomposition_text.find('{')
            end_idx = decomposition_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = decomposition_text[start_idx:end_idx]
                decomposition_data = json.loads(json_str)
                return decomposition_data
            else:
                logger.warning("No valid JSON structure found in decomposition response")
                return {"error": "Failed to parse decomposition response"}
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse decomposition JSON: {json_err}")
            return {"error": f"JSON parsing error: {json_err}"}
            
    except Exception as e:
        logger.error(f"Error decomposing goal: {e}")
        return {"error": str(e)}

async def create_subgoal_plan(subgoal: Dict[str, Any], context: Dict[str, Any], previous_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a detailed plan for a specific subgoal
    
    Args:
        subgoal: The subgoal to plan for
        context: Additional context for planning
        previous_results: Results from previous subgoals
        
    Returns:
        Detailed plan for the subgoal
    """
    try:
        # Convert context and previous results to strings for prompt
        context_str = json.dumps(context, indent=2)
        previous_results_str = json.dumps(previous_results, indent=2)
        
        response = await client.chat.completions.acreate(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SUBGOAL_PLANNING_PROMPT.format(
                    subgoal=subgoal["text"],
                    context=context_str,
                    previous_results=previous_results_str
                )},
                {"role": "user", "content": f"Create a plan for this subgoal: {subgoal['text']}"}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        plan_text = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        try:
            start_idx = plan_text.find('{')
            end_idx = plan_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = plan_text[start_idx:end_idx]
                plan_data = json.loads(json_str)
                return plan_data
            else:
                logger.warning("No valid JSON structure found in subgoal planning")
                return {"error": "Failed to parse subgoal plan"}
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse subgoal plan JSON: {json_err}")
            return {"error": f"JSON parsing error: {json_err}"}
            
    except Exception as e:
        logger.error(f"Error creating subgoal plan: {e}")
        return {"error": str(e)}

async def integrate_subplans(subgoals: List[Dict[str, Any]], subplans: Dict[str, Any], execution_order: List[str], goal: str) -> Dict[str, Any]:
    """
    Integrate multiple subplans into a cohesive final plan
    
    Args:
        subgoals: List of subgoals
        subplans: Dictionary mapping subgoal IDs to their plans
        execution_order: Order to execute subgoals in
        goal: The original high-level goal
        
    Returns:
        Integrated plan
    """
    try:
        # Create a structured representation of subgoals and their plans for the prompt
        subplans_str = ""
        for sg in subgoals:
            sg_id = sg["id"]
            sg_plan = subplans.get(sg_id, {"error": "No plan available"})
            subplans_str += f"SUBGOAL ID: {sg_id}\n"
            subplans_str += f"SUBGOAL TEXT: {sg['text']}\n"
            subplans_str += f"PLAN: {json.dumps(sg_plan, indent=2)}\n\n"
        
        response = await client.chat.completions.acreate(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": PLAN_INTEGRATION_PROMPT.format(
                    subplans=subplans_str,
                    execution_order=json.dumps(execution_order),
                    goal=goal
                )},
                {"role": "user", "content": "Integrate these subplans into a cohesive final plan."}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        integration_text = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        try:
            start_idx = integration_text.find('{')
            end_idx = integration_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = integration_text[start_idx:end_idx]
                integration_data = json.loads(json_str)
                return integration_data
            else:
                logger.warning("No valid JSON structure found in plan integration")
                return {"error": "Failed to parse integrated plan"}
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse integration JSON: {json_err}")
            return {"error": f"JSON parsing error: {json_err}"}
            
    except Exception as e:
        logger.error(f"Error integrating subplans: {e}")
        return {"error": str(e)}

async def recursive_planning(goal: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform recursive planning for a complex goal
    
    Args:
        goal: The high-level goal
        context: Additional context
        
    Returns:
        Final recursive plan
    """
    start_time = time.time()
    result = {
        "goal": goal,
        "planning_started_at": datetime.now().isoformat(),
        "subgoals": [],
        "subplans": {},
        "final_plan": None,
        "planning_time": None,
        "status": "in_progress"
    }
    
    try:
        # 1. Decompose the goal into subgoals
        decomposition = await decompose_goal(goal, context)
        
        if "error" in decomposition:
            result["status"] = "error"
            result["error"] = decomposition["error"]
            return result
            
        result["subgoals"] = decomposition.get("subgoals", [])
        execution_order = decomposition.get("execution_order", [])
        result["execution_order"] = execution_order
        result["decomposition_reasoning"] = decomposition.get("reasoning", "")
        
        # 2. Create plans for each subgoal
        previous_results = {}
        
        for sg_id in execution_order:
            # Find the subgoal by ID
            subgoal = next((sg for sg in result["subgoals"] if sg["id"] == sg_id), None)
            
            if subgoal:
                # Create plan for this subgoal
                plan = await create_subgoal_plan(subgoal, context, previous_results)
                result["subplans"][sg_id] = plan
                
                # Update previous results
                previous_results[sg_id] = {
                    "subgoal": subgoal["text"],
                    "plan": plan
                }
        
        # 3. Integrate subplans into a final plan
        if result["subplans"]:
            final_plan = await integrate_subplans(
                result["subgoals"],
                result["subplans"],
                execution_order,
                goal
            )
            result["final_plan"] = final_plan
        
        result["status"] = "completed"
        
    except Exception as e:
        logger.error(f"Error in recursive planning: {e}")
        result["status"] = "error"
        result["error"] = str(e)
        
    # Record planning time
    result["planning_completed_at"] = datetime.now().isoformat()
    result["planning_time"] = round(time.time() - start_time, 2)
    
    return result

async def get_next_action_from_recursive_plan(state: AgentState) -> Dict[str, Any]:
    """
    Get the next action to perform from a recursive plan
    
    Args:
        state: The current agent state
        
    Returns:
        Action to perform
    """
    try:
        # Get current plan and tracking information
        recursive_plan = getattr(state, "recursive_plan", None)
        current_subgoal_idx = getattr(state, "current_subgoal_idx", 0)
        current_step_idx = getattr(state, "current_step_idx", 0)
        
        if not recursive_plan or "final_plan" not in recursive_plan or not recursive_plan["final_plan"]:
            # No recursive plan or no final plan available
            logger.warning("No recursive plan available, falling back to default action")
            return {"type": "click", "x": 100, "y": 200}
            
        # Get integrated steps from final plan
        integrated_steps = recursive_plan["final_plan"].get("integrated_steps", [])
        
        if not integrated_steps or current_step_idx >= len(integrated_steps):
            # No more steps in this plan
            if current_subgoal_idx < len(recursive_plan.get("execution_order", [])):
                # Move to next subgoal
                state.current_subgoal_idx = current_subgoal_idx + 1
                state.current_step_idx = 0
                # Recursive call to get action for next subgoal
                return await get_next_action_from_recursive_plan(state)
            else:
                # No more subgoals
                logger.info("Recursive plan completed")
                return {"type": "completed", "message": "All subgoals completed"}
        
        # Get current step
        current_step = integrated_steps[current_step_idx]
        
        # Update state to move to next step next time
        state.current_step_idx = current_step_idx + 1
        
        # Parse step description to determine action type
        description = current_step.get("description", "").lower()
        
        # Similar action derivation logic as in the original planner
        if "browser_navigate" in description or "go to url" in description or "open website" in description:
            # Extract URL if possible
            import re
            url_match = re.search(r'https?://[^\s)"\']+', description)
            url = url_match.group(0) if url_match else "https://www.example.com"
            return {"type": "browser_navigate", "url": url}
        
        elif "browser_click" in description or "click on element" in description:
            # Extract selector if possible
            selector = None
            if "selector" in description:
                selector_match = re.search(r'selector[:\s]+[\'"]([^\'"]+)[\'"]', description)
                if selector_match:
                    selector = selector_match.group(1)
            
            if selector:
                return {"type": "browser_click", "selector": selector}
            else:
                # Fall back to regular click
                return {"type": "click", "x": 100, "y": 200}
                
        elif "browser_fill" in description or "type in field" in description or "enter text" in description:
            # Try to extract selector and value
            selector = None
            value = None
            
            if "selector" in description:
                selector_match = re.search(r'selector[:\s]+[\'"]([^\'"]+)[\'"]', description)
                if selector_match:
                    selector = selector_match.group(1)
                    
            if "value" in description or "text" in description:
                value_match = re.search(r'(?:value|text)[:\s]+[\'"]([^\'"]+)[\'"]', description)
                if value_match:
                    value = value_match.group(1)
            
            if selector and value:
                return {"type": "browser_fill", "selector": selector, "value": value}
            elif "type" in description:
                # Extract text to type if possible
                text_match = description.split("type", 1)[-1].strip().strip('"\'').split('"')[0]
                return {"type": "type", "text": text_match or "Hello"}
        
        elif "screenshot" in description or "capture screen" in description:
            return {"type": "browser_screenshot"}
            
        # Fall through to other action types from the original planner
        from app.nodes.planner import derive_action_from_plan
        
        # Create a temporary state with the current step as the plan
        temp_state = AgentState()
        temp_state.plan_steps = [current_step]
        temp_state.current_step_index = 0
        
        return derive_action_from_plan(temp_state)
        
    except Exception as e:
        logger.error(f"Error getting next action from recursive plan: {e}")
        return {"type": "click", "x": 100, "y": 200}  # Default fallback action
