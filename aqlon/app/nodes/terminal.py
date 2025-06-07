from app.logger import logger
from app.state import AgentState
import time
import re
import subprocess

# List of forbidden commands for safety
FORBIDDEN_TERMINAL_PATTERNS = [
    r"\brm\b",
    r"\breboot\b",
    r"\bshutdown\b",
    r"\bhalt\b",
    r"\bpoweroff\b",
    r"\bmkfs\b",
    r"\bdd\b",
    r"\binit\b",
    r"\b:(){:|:&};:\b",  # fork bomb
]

def is_command_safe(command: str) -> bool:
    for pattern in FORBIDDEN_TERMINAL_PATTERNS:
        if re.search(pattern, command):
            return False
    return True

def terminal_node(state: AgentState) -> AgentState:
    logger.info(f"[TerminalNode] Received state: {state}")
    try:
        command = getattr(state, "terminal_command", None)
        if command:
            if not is_command_safe(command):
                state.terminal_output = "Command blocked for safety."
                state.terminal_error = "Forbidden or dangerous command detected."
                state.terminal_exit_code = -2
            else:
                result = subprocess.run(command, shell=True, capture_output=True, text=True)
                state.terminal_output = result.stdout.strip()
                state.terminal_error = result.stderr.strip() if result.stderr else None
                state.terminal_exit_code = result.returncode
        else:
            state.terminal_output = "No command provided"
            state.terminal_exit_code = None
        state.terminal_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logger.info(f"[TerminalNode] Resulting state: {state}")
    except Exception as e:
        logger.error(f"Terminal node error: {e}")
        state.terminal_output = ""
        state.terminal_error = str(e)
        state.terminal_exit_code = -1
    return state

# Example test usage:
if __name__ == "__main__":
    safe_state = AgentState(terminal_command="echo Hello, AQLON!")
    dangerous_state = AgentState(terminal_command="rm -rf /")
    print(terminal_node(safe_state).terminal_output)
    print(terminal_node(dangerous_state).terminal_output)
