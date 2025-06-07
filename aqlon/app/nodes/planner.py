"""
Enhanced planner module for AQLon agent
Features:
- Step decomposition with LLM
- Memory context incorporation
- Self-critique and plan refinement
"""
import json
import time
from typing import Dict, List, Any
from datetime import datetime

from app.logger import logger
from app.state import AgentState
from app.memory import memory
from app.settings import settings
from openai import OpenAI

# Initialize the OpenAI client
client = OpenAI(api_key=settings.openai_api_key)

# System prompts for different planner operations
STEP_DECOMPOSITION_PROMPT = """
You are the AQLon Planner, responsible for breaking down high-level goals into specific, actionable steps.
Given a goal, decompose it into a sequence of steps that the agent can execute.
Each step should be clear, concise, and actionable.

GOAL: {goal}

VISION STATE: {vision_state}

Your task is to break down this goal into 3-7 specific steps.
Return your response as JSON with this structure:
{{
  "steps": [
    {{"name": "Step name", "description": "Detailed step description", "estimated_duration": "30s"}},
    ...
  ]
}}

Be specific and concrete about each action the agent should take.
"""

CONTEXT_INCORPORATION_PROMPT = """
You are the AQLon Planner, responsible for refining plans based on memory context.
Review the goal, initial plan, and memory context to create an improved plan.

GOAL: {goal}

INITIAL PLAN: {initial_plan}

MEMORY CONTEXT: {memory_context}

VISION STATE: {vision_state}

Your task is to refine the initial plan incorporating context from memory.
Return your response as JSON with this structure:
{{
  "steps": [
    {{"name": "Step name", "description": "Detailed step description", "estimated_duration": "30s"}},
    ...
  ],
  "context_utilized": "Brief explanation of how memory context informed this plan"
}}

Be specific and concrete about each action. Consider what you've learned from past interactions in your plan.
"""

SELF_CRITIQUE_PROMPT = """
You are the AQLon Planner, conducting a self-critique of your plan.
Analyze the current plan for potential issues and suggest improvements.

GOAL: {goal}

CURRENT PLAN: {current_plan}

VISION STATE: {vision_state}

Your task is to critique this plan and improve it:
1. Identify potential issues, inefficiencies, or missing steps
2. Suggest improvements or alternative approaches
3. Produce a refined plan that addresses these issues

Return your response as JSON with this structure:
{{
  "critique": [
    {{"issue": "Description of issue", "impact": "Why this matters", "recommendation": "How to fix it"}}
  ],
  "improved_steps": [
    {{"name": "Step name", "description": "Detailed step description", "estimated_duration": "30s"}}
  ]
}}

Be constructively critical and focus on making the plan more robust, efficient, and likely to succeed.
"""

def get_memory_context(state: AgentState) -> Dict[str, Any]:
    """
    Retrieve relevant context from memory to inform planning
    """
    context = {
        "recent_events": [],
        "related_goals": [],
        "relevant_observations": []
    }
    
    try:
        # Get recent events from memory if goal_id is available
        goal_id = getattr(state, "goal_id", None)
        if goal_id:
            events = memory.get_related_events(goal_id=goal_id, limit=5)
            for event in events:
                context["recent_events"].append({
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                    "action": event.agent_action,
                    "vision": event.vision_state[:100] + "..." if event.vision_state and len(event.vision_state) > 100 else event.vision_state,
                    "terminal": event.terminal_output[:100] + "..." if event.terminal_output and len(event.terminal_output) > 100 else event.terminal_output
                })
        
        # Get working memory items
        for key in ["observations", "results", "errors"]:
            value = memory.get_from_working_memory(key)
            if value:
                context["relevant_observations"].append({key: value})
        
        # Include session-specific information
        session_id = getattr(state, "session_id", None) or getattr(memory, "session_id", None)
        if session_id:
            active_goals = memory.get_current_goals(limit=3)
            for goal in active_goals:
                if goal.id != goal_id:  # Don't include current goal
                    context["related_goals"].append({
                        "text": goal.goal_text,
                        "status": goal.status,
                        "priority": goal.priority
                    })
    except Exception as e:
        logger.error(f"Error retrieving memory context: {e}")
    
    return context

def generate_initial_plan(state: AgentState) -> List[Dict[str, Any]]:
    """
    Generate an initial plan by breaking down the goal into steps
    """
    goal = getattr(state, "goal", "")
    vision_state = getattr(state, "vision_state", "")
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": STEP_DECOMPOSITION_PROMPT.format(
                    goal=goal,
                    vision_state=vision_state[:1000] if vision_state else "No vision state available"
                )},
                {"role": "user", "content": "Generate a step-by-step plan for this goal."}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        plan_text = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        try:
            # Look for JSON structure in the response
            start_idx = plan_text.find('{')
            end_idx = plan_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = plan_text[start_idx:end_idx]
                plan_data = json.loads(json_str)
                return plan_data.get("steps", [])
            else:
                logger.warning("No valid JSON structure found in LLM response")
                return []
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse plan JSON: {json_err}")
            return []
            
    except Exception as e:
        logger.error(f"Error generating initial plan: {e}")
        return []

def incorporate_context(state: AgentState, initial_plan: List[Dict[str, Any]], memory_context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Incorporate memory context to refine the plan
    """
    goal = getattr(state, "goal", "")
    vision_state = getattr(state, "vision_state", "")
    
    try:
        # Convert plan and context to strings for the prompt
        initial_plan_str = json.dumps(initial_plan, indent=2)
        memory_context_str = json.dumps(memory_context, indent=2)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": CONTEXT_INCORPORATION_PROMPT.format(
                    goal=goal,
                    initial_plan=initial_plan_str,
                    memory_context=memory_context_str,
                    vision_state=vision_state[:1000] if vision_state else "No vision state available"
                )},
                {"role": "user", "content": "Refine the plan based on memory context."}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        refined_plan_text = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        try:
            start_idx = refined_plan_text.find('{')
            end_idx = refined_plan_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = refined_plan_text[start_idx:end_idx]
                refined_data = json.loads(json_str)
                return {
                    "steps": refined_data.get("steps", initial_plan),
                    "context_utilized": refined_data.get("context_utilized", "No context information utilized")
                }
            else:
                logger.warning("No valid JSON structure found in context incorporation")
                return {"steps": initial_plan, "context_utilized": "Failed to incorporate context"}
        except json.JSONDecodeError:
            logger.error("Failed to parse refined plan JSON")
            return {"steps": initial_plan, "context_utilized": "Failed to parse context incorporation"}
            
    except Exception as e:
        logger.error(f"Error incorporating context into plan: {e}")
        return {"steps": initial_plan, "context_utilized": f"Error: {str(e)}"}

def self_critique_plan(state: AgentState, current_plan: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Perform self-critique on the plan and generate improvements
    """
    goal = getattr(state, "goal", "")
    vision_state = getattr(state, "vision_state", "")
    
    try:
        current_plan_str = json.dumps(current_plan, indent=2)
        
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SELF_CRITIQUE_PROMPT.format(
                    goal=goal,
                    current_plan=current_plan_str,
                    vision_state=vision_state[:1000] if vision_state else "No vision state available"
                )},
                {"role": "user", "content": "Critique and improve this plan."}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        critique_text = response.choices[0].message.content.strip()
        
        # Extract JSON from response
        try:
            start_idx = critique_text.find('{')
            end_idx = critique_text.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = critique_text[start_idx:end_idx]
                critique_data = json.loads(json_str)
                return {
                    "critique": critique_data.get("critique", []),
                    "improved_steps": critique_data.get("improved_steps", current_plan)
                }
            else:
                logger.warning("No valid JSON structure found in critique")
                return {"critique": [], "improved_steps": current_plan}
        except json.JSONDecodeError:
            logger.error("Failed to parse critique JSON")
            return {"critique": [], "improved_steps": current_plan}
            
    except Exception as e:
        logger.error(f"Error during plan self-critique: {e}")
        return {"critique": [], "improved_steps": current_plan}

def derive_action_from_plan(state: AgentState) -> Dict[str, Any]:
    """
    Derive the next action from the current plan step
    """
    plan_steps = getattr(state, "plan_steps", [])
    current_step_index = getattr(state, "current_step_index", 0)
    
    if not plan_steps or current_step_index >= len(plan_steps):
        # Default action if no plan or all steps completed
        return {"type": "click", "x": 100, "y": 200}
    
    # Get current step
    current_step = plan_steps[current_step_index]
    description = current_step.get("description", "").lower()
    
    # Parse step description to determine action type
    if any(keyword in description for keyword in ["type", "enter", "input"]):
        # Extract text to type if possible
        text_match = description.split("type", 1)[-1].strip().strip('"\'').split('"')[0] if "type" in description else "Hello"
        return {"type": "type", "text": text_match or "Hello from AQLON!"}
    
    elif any(keyword in description for keyword in ["click", "select", "press", "choose"]):
        # If coordinates are mentioned, try to extract them
        if "click on" in description and "at coordinates" in description:
            coords_text = description.split("at coordinates")[-1].strip()
            import re
            coords_match = re.search(r'\((\d+),\s*(\d+)\)', coords_text)
            if coords_match:
                x, y = map(int, coords_match.groups())
                return {"type": "click", "x": x, "y": y}
        
        # Look for template matching in description
        template_match = None
        if "click on" in description:
            template_candidate = description.split("click on")[-1].strip().split(".")[0].strip('"\'')
            if template_candidate:
                template_match = template_candidate
                
        if template_match:
            return {"type": "click_template", "template_name": template_match}
        else:
            return {"type": "click", "x": 100, "y": 200}
    
    elif any(keyword in description for keyword in ["scroll", "move page"]):
        direction = "down"
        amount = 3
        
        if "up" in description:
            direction = "up"
        elif "left" in description:
            direction = "left"
        elif "right" in description:
            direction = "right"
            
        # Try to extract amount
        import re
        amount_match = re.search(r'scroll\s+(\d+)', description)
        if amount_match:
            amount = int(amount_match.group(1))
            
        return {"type": "scroll", "direction": direction, "amount": amount}
    
    elif any(keyword in description for keyword in ["drag", "move element", "drag and drop"]):
        # Default drag coordinates
        return {
            "type": "drag_and_drop",
            "start_x": 100, "start_y": 100,
            "end_x": 200, "end_y": 200,
            "duration": 0.5
        }
    
    elif any(keyword in description for keyword in ["hover", "move mouse to"]):
        # Default hover action
        return {"type": "hover", "x": 150, "y": 150, "duration": 1.0}
    
    # Default action
    return {"type": "click", "x": 100, "y": 200}

def planner_node(state: AgentState) -> AgentState:
    """
    Enhanced planner node that breaks goals into steps, incorporates memory context,
    performs self-critique, and generates improved plans.
    """
    logger.info(f"[PlannerNode] Received state: {state}")
    start_time = time.time()
    
    try:
        # 1. Generate initial plan by decomposing the goal into steps
        initial_plan = generate_initial_plan(state)
        if not initial_plan:
            logger.warning("[PlannerNode] Failed to generate initial plan")
            # Fall back to simple action
            state.action = {"type": "click", "x": 100, "y": 200}
            return state
        
        # Record planning progress in state for transparency
        state.planning_progress = {"phase": "initial_plan_generated", "timestamp": datetime.now().isoformat()}
        
        # 2. Retrieve memory context
        memory_context = get_memory_context(state)
        
        # 3. Incorporate memory context into the plan
        context_result = incorporate_context(state, initial_plan, memory_context)
        refined_plan = context_result["steps"]
        context_utilized = context_result["context_utilized"]
        
        # Update planning progress
        state.planning_progress = {"phase": "context_incorporated", "timestamp": datetime.now().isoformat()}
        
        # 4. Self-critique and improve plan
        critique_result = self_critique_plan(state, refined_plan)
        critique = critique_result["critique"]
        final_plan = critique_result["improved_steps"]
        
        # 5. Store the final plan in state
        state.plan_steps = final_plan
        state.current_step_index = 0
        state.plan_critique = critique
        state.plan_context = {
            "context_utilized": context_utilized,
            "generated_at": datetime.now().isoformat(),
            "generation_time_seconds": round(time.time() - start_time, 2)
        }
        
        # 6. Determine the next action based on the first step in the plan
        state.action = derive_action_from_plan(state)
        
        # Log plan summary
        logger.info(f"[PlannerNode] Generated plan with {len(final_plan)} steps")
        logger.info(f"[PlannerNode] Next action: {state.action}")
        
    except Exception as e:
        logger.error(f"Planner node error: {e}")
        # Fall back to simple action on error
        state.action = {"type": "click", "x": 100, "y": 200}
        state.planner_error = str(e)
    
    return state