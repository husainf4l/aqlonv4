#!/usr/bin/env python3
"""
Test script for the full AQLON workflow
This script tests the complete AQLON agent workflow by:
1. Starting a new session
2. Monitoring session status
3. Checking session results
"""

import requests
import time
import json
from pprint import pprint
import sys

# Configuration
API_URL = "http://localhost:8000/api/v1"
TEST_GOAL = "Research and summarize the benefits of quantum computing in healthcare applications. Focus on recent developments and potential future impacts."
MAX_ITERATIONS = 3

def print_section(title):
    """Print a section title with dashes"""
    print(f"\n{'-' * 40}")
    print(f"-- {title}")
    print(f"{'-' * 40}")

def main():
    """Run the main test workflow"""
    print_section("Starting AQLON Test")
    
    # Step 1: Start a new session
    print("Creating new agent session...")
    session_data = {
        "goal": TEST_GOAL,
        "max_iterations": MAX_ITERATIONS,
        "monitor_index": 0
    }
    
    try:
        response = requests.post(f"{API_URL}/session", json=session_data)
        response.raise_for_status()
        session = response.json()
        session_id = session["session_id"]
        
        print(f"Session created with ID: {session_id}")
        print(f"Goal: {session['goal']}")
        print(f"Max iterations: {session['iterations_max']}")
        
        # Step 2: Monitor session status until completion
        print_section("Monitoring Session Progress")
        completed = False
        
        while not completed:
            print("Checking session status...")
            response = requests.get(f"{API_URL}/session/{session_id}")
            
            if response.status_code != 200:
                print(f"Error retrieving session: {response.status_code}")
                break
                
            session_status = response.json()
            status = session_status["status"]
            iterations = session_status["iterations_completed"]
            
            print(f"Status: {status}, Iterations completed: {iterations}/{MAX_ITERATIONS}")
            
            if status in ["completed", "error"]:
                completed = True
                print(f"Session {status}")
                if status == "error" and "error" in session_status:
                    print(f"Error: {session_status.get('error', 'Unknown error')}")
            else:
                # Check agent status
                try:
                    agent_status = requests.get(f"{API_URL}/agent/status").json()
                    print(f"Agent active: {agent_status['active']}")
                    if agent_status.get("last_action"):
                        print(f"Last action: {agent_status['last_action'].get('type', 'unknown')}")
                except Exception as e:
                    print(f"Error getting agent status: {e}")
                
                # Wait before checking again
                print("Waiting 5 seconds...")
                time.sleep(5)
        
        # Step 3: Print final results
        print_section("Final Results")
        response = requests.get(f"{API_URL}/session/{session_id}")
        final_status = response.json()
        
        print("Session Summary:")
        print(f"  Status: {final_status['status']}")
        print(f"  Iterations: {final_status['iterations_completed']}/{final_status['iterations_max']}")
        
        # Print state if available
        if final_status.get("current_state"):
            print("\nFinal Agent State:")
            state = final_status["current_state"]
            
            # Print key state values
            important_keys = ["goal", "goal_complete", "status_message", "action_result"]
            for key in important_keys:
                if key in state:
                    print(f"  {key}: {state[key]}")
        
        # Try to get the session log
        try:
            print_section("Session Log")
            log_response = requests.get(f"{API_URL}/session/{session_id}/log", params={"format": "json"})
            if log_response.status_code == 200:
                log_data = log_response.json()
                print(f"Log entries: {len(log_data.get('events', []))}")
                # Print a few log entries
                for i, event in enumerate(log_data.get("events", [])[:3]):
                    print(f"Event {i+1}:")
                    if "action_result" in event:
                        print(f"  Action result: {event['action_result']}")
            else:
                print(f"Error retrieving log: {log_response.status_code}")
        except Exception as e:
            print(f"Error getting session log: {e}")
            
        print_section("Test Completed")
        return True
        
    except Exception as e:
        print(f"Test failed with error: {e}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
