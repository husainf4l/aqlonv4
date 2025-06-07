from langgraph.graph import StateGraph, END

from app.state import AgentState
from app.nodes.action import action_node
from app.nodes.browser_action import browser_action_node
from app.nodes.memory_node import memory_node
from app.nodes.goal_generator import goal_generator_node
from app.nodes.planner import planner_node
from app.logger import logger

# Goal completion check node with configurable loop counter
def goal_completion_check_node(state: AgentState) -> AgentState:
    # Mark complete if any of the following conditions are met:
    # 1. state.goal contains 'done'
    # 2. We've completed max_iterations
    # 3. An explicit goal_complete flag has been set
    # 4. A success criterion was met in an action
    goal = getattr(state, "goal", "")
    
    # Initialize loop counter if not present
    loop_counter = getattr(state, "internal_loop_counter", 0)
    state.internal_loop_counter = loop_counter + 1
    
    # Get max iterations (default to 3 if not specified)
    max_iterations = getattr(state, "max_iterations", 3)
    
    # Check if goal was explicitly marked complete by another node
    explicit_complete = getattr(state, "goal_complete", False)
    
    # Check if an action succeeded and reported goal completion
    action_success = getattr(state, "action_success", False)
    action_completed_goal = getattr(state, "action_completed_goal", False)
    
    # Determine if the goal should be considered complete
    should_complete = (
        "done" in goal.lower() or
        state.internal_loop_counter >= max_iterations or
        explicit_complete or
        (action_success and action_completed_goal)
    )
    
    # Set goal_complete flag
    state.goal_complete = should_complete
    
    if state.goal_complete:
        # Append completion message if not already marked
        if " (Goal complete!)" not in state.goal:
            state.goal = state.goal + " (Goal complete!)"
        
        # Set appropriate status message
        if state.internal_loop_counter >= max_iterations:
            state.status_message = f"Goal processing stopped after reaching maximum iterations ({max_iterations})"
        else:
            state.status_message = "Goal processing completed successfully"
        
        logger.info(f"[GoalCompletionCheck] Goal complete after {state.internal_loop_counter} iterations")
        
    return state

# Optimization node to dynamically skip steps based on context
def optimization_node(state: AgentState) -> AgentState:
    """
    Dynamically determine if certain nodes can be skipped based on context
    """
    # Initialize or update optimization context
    if not hasattr(state, "optimizations") or state.optimizations is None:
        state.optimizations = {
            "skipped_nodes": [],
            "optimization_reason": {},
            "cumulative_time_saved": 0
        }
    
    # Check if previous action was successful
    action_success = getattr(state, "action_success", None)
    
    # Get information about the current plan
    plan_steps = getattr(state, "plan_steps", [])
    current_step_index = getattr(state, "current_step_index", 0)
    
    # Flag for whether to skip the next planning step
    skip_planning = False
    skip_memory = False
    skip_goal_generator = False
    
    # Logic for determining if planning can be skipped
    if action_success is True and plan_steps and current_step_index < len(plan_steps) - 1:
        # If we have a successful action and more steps in the plan, we can skip re-planning
        skip_planning = True
        state.optimizations["skipped_nodes"].append("planner_node")
        state.optimizations["optimization_reason"]["planner_node"] = "Action successful and more steps in plan"
        state.optimizations["cumulative_time_saved"] += 1.5  # Estimated seconds saved
        
        # Auto-advance to next step in the plan
        state.current_step_index = current_step_index + 1
    
    # Logic for determining if memory operations can be streamlined
    if not getattr(state, "memory_intensive", False):
        # For non-memory intensive operations, we can simplify memory operations
        skip_memory = False  # We can't actually skip memory as it's essential, but we might optimize it
        
        # Set a flag to indicate that memory operations should be lighter
        state.memory_light_mode = True
    
    # Logic for determining if goal generator can be skipped
    if not getattr(state, "goal_complete", False) and getattr(state, "internal_loop_counter", 0) > 1:
        # After first iteration, if goal isn't complete, we can sometimes skip goal generation
        if getattr(state, "action_success", False) and plan_steps and current_step_index < len(plan_steps):
            # If we're making progress on the plan, goal generation can be skipped
            skip_goal_generator = True
            state.optimizations["skipped_nodes"].append("goal_generator_node")
            state.optimizations["optimization_reason"]["goal_generator_node"] = "Making progress on existing plan"
            state.optimizations["cumulative_time_saved"] += 0.8  # Estimated seconds saved
    
    # Store optimization decisions in state
    state.skip_planning = skip_planning
    state.skip_memory = skip_memory
    state.skip_goal_generator = skip_goal_generator
    
    return state

# Define router for conditional branching
def should_continue(state: AgentState) -> str:
    if getattr(state, "goal_complete", False):
        return "exit"
    else:
        return "continue"

# Router for optimization-based node selection
def route_with_optimization(state: AgentState) -> str:
    """
    Route to appropriate node based on optimization decisions
    """
    # Check if planning should be skipped
    if getattr(state, "skip_planning", False):
        # Skip planning and go directly to action
        return "to_action"
    else:
        # Normal flow through planning
        return "to_planner"

# Router for browser vs regular action
def select_action_type(state: AgentState) -> str:
    """
    Select appropriate action node based on action type
    """
    action = getattr(state, "action", {}) or {}
    action_type = action.get("type", "")
    
    if action_type.startswith("browser_"):
        return "browser_action"
    else:
        return "regular_action"

# Router for goal generator optimization
def route_after_goal_check(state: AgentState) -> str:
    """
    Determine whether to go to goal generator or skip it
    """
    if getattr(state, "skip_goal_generator", False):
        return "skip_to_optimization"
    else:
        return "to_goal_generator"

# Build the enhanced LangGraph workflow with optimizations
graph = StateGraph(state_schema=AgentState)

# Add nodes
graph.add_node("goal_generator_node", goal_generator_node)
graph.add_node("optimization_node", optimization_node)
graph.add_node("planner_node", planner_node)
graph.add_node("action_node", action_node)
graph.add_node("browser_action_node", browser_action_node)
graph.add_node("memory_node", memory_node)
graph.add_node("goal_completion_check_node", goal_completion_check_node)
# Add dummy select_action_type node to handle routing logic
graph.add_node("select_action_type", lambda state: state)

# Define the enhanced flow with optimization paths

# After goal completion check, conditionally go to goal generator or optimization
graph.add_conditional_edges(
    "goal_completion_check_node",
    route_after_goal_check,
    {
        "to_goal_generator": "goal_generator_node",
        "skip_to_optimization": "optimization_node"
    }
)

# From goal generator to optimization node
graph.add_edge("goal_generator_node", "optimization_node")

# From optimization node, conditionally route to planner or action selection
graph.add_conditional_edges(
    "optimization_node",
    route_with_optimization,
    {
        "to_planner": "planner_node",
        "to_action": "select_action_type"  # Skip directly to action selection
    }
)

# From planner to action selection
graph.add_edge("planner_node", "select_action_type")

# Select between browser action or regular action
graph.add_conditional_edges(
    "select_action_type",
    select_action_type,
    {
        "browser_action": "browser_action_node",
        "regular_action": "action_node"
    }
)

# Both action nodes go to memory
graph.add_edge("browser_action_node", "memory_node")
graph.add_edge("action_node", "memory_node")

# Memory to goal completion check
graph.add_edge("memory_node", "goal_completion_check_node")

# Add conditional routing based on goal completion
graph.add_conditional_edges(
    "goal_completion_check_node",
    should_continue,
    {
        "continue": "goal_generator_node",  # Continue loop
        "exit": END  # Exit the workflow
    }
)

graph.set_entry_point("goal_generator_node")

# Compile the graph for execution
# Note: recursion_limit parameter might not be supported in this version
# Fallback to standard compilation
compiled_graph = graph.compile()

if __name__ == "__main__":
    state = AgentState()
    state.internal_loop_counter = 0  # Initialize loop counter
    print("Starting agent loop...")
    state = compiled_graph.invoke(state)
    print(f"Final state: {state}")
    print("Agent workflow completed!")
