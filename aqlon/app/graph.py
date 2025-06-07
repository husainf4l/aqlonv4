from langgraph.graph import StateGraph, END

from app.state import AgentState
from app.nodes.action import action_node
from app.nodes.memory_node import memory_node
from app.nodes.goal_generator import goal_generator_node
from app.nodes.planner import planner_node

# Dummy goal completion check node with loop counter
def goal_completion_check_node(state: AgentState) -> AgentState:
    # For demo: mark complete if state.goal contains 'done' or we've completed several iterations
    goal = getattr(state, "goal", "")
    
    # Initialize loop counter if not present
    loop_counter = getattr(state, "internal_loop_counter", 0)
    state.internal_loop_counter = loop_counter + 1
    
    # Exit after 3 loops or if 'done' in goal
    state.goal_complete = "done" in goal.lower() or state.internal_loop_counter >= 3
    
    if state.goal_complete:
        state.goal = state.goal + " (Goal complete!)"
        
    return state

# Define router for conditional branching
def should_continue(state: AgentState) -> str:
    if getattr(state, "goal_complete", False):
        return "exit"
    else:
        return "continue"

# Build the LangGraph workflow

graph = StateGraph(state_schema=AgentState)

graph.add_node("goal_generator_node", goal_generator_node)
graph.add_node("planner_node", planner_node)
graph.add_node("action_node", action_node)
graph.add_node("memory_node", memory_node)
graph.add_node("goal_completion_check_node", goal_completion_check_node)

# Define the flow: GoalGen → Planner → Action → Memory → GoalCompletionCheck
# If not complete, loop; if complete, break

graph.add_edge("goal_generator_node", "planner_node")
graph.add_edge("planner_node", "action_node")
graph.add_edge("action_node", "memory_node")
graph.add_edge("memory_node", "goal_completion_check_node")

# Add conditional routing based on goal completion
graph.add_conditional_edges(
    "goal_completion_check_node",
    should_continue,
    {
        "continue": "goal_generator_node",  # Loop: continue to generate new goals
        "exit": END  # Exit the workflow
    }
)

graph.set_entry_point("goal_generator_node")

# Compile the graph for execution (LangGraph v0.0.38+)
compiled_graph = graph.compile()

if __name__ == "__main__":
    state = AgentState()
    state.internal_loop_counter = 0  # Initialize loop counter
    print("Starting agent loop...")
    state = compiled_graph.invoke(state)
    print(f"Final state: {state}")
    print("Agent workflow completed!")
