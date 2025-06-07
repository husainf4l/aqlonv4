from app.logger import logger
from app.state import AgentState
from app.settings import settings
from openai import OpenAI
import time

# Initialize the OpenAI client using settings
client = OpenAI(api_key=settings.openai_api_key)

LLM_SYSTEM_PROMPT = """
You are the Goal Generator for the AQLON agent. Given the current state, generate a clear, actionable goal for the agent to pursue next. Be concise and specific.
"""

def goal_generator_node(state: AgentState) -> AgentState:
    """
    Calls an LLM to generate the next goal for the agent based on the current state.
    Updates state with 'goal' and 'goal_generation_timestamp'.
    """
    try:
        user_context = getattr(state, "user_context", None) or str(state)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_context}
            ],
            max_tokens=128,
            temperature=0.3
        )
        goal = response.choices[0].message.content.strip()
        state.goal = goal
        state.goal_generation_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logger.info(f"[GoalGenerator] Generated goal: {goal}")
    except Exception as e:
        logger.error(f"Goal Generator node error: {e}")
        state.goal = "Explore the current screen and report what you see (fallback goal)"
        state.goal_generation_error = str(e)
    return state

# Example test usage:
if __name__ == "__main__":
    from app.state import AgentState
    sample_state = AgentState()
    sample_state.user_context = "The agent just opened the browser and is ready for a new task."
    result = goal_generator_node(sample_state)
    print(result.goal)
