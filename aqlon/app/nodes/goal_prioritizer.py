"""
Goal prioritization logic for AQLon agent

Evaluates goals and assigns priority scores based on various factors:
1. User-specified priority (explicit)
2. Goal urgency (time-sensitive tasks)
3. Goal importance (impact on overall objectives)
4. Goal dependencies (prerequisites for other goals)
5. Resource availability (can it be accomplished now)
"""

import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

from app.logger import logger
from app.state import AgentState
from app.nodes.goal_history import GoalHistory, update_goal_status, get_active_goals, SessionLocal

class GoalPrioritizer:
    def __init__(self):
        # Default weights for prioritization factors
        self.weights = {
            "user_priority": 2.0,     # User-specified priority (highest weight)
            "urgency": 1.5,           # Time sensitivity
            "importance": 1.2,        # Strategic importance
            "dependency": 1.0,        # Has dependent goals
            "resource_avail": 0.8,    # Resources currently available
        }
        
        # Safe ranges for priority
        self.min_priority = 1
        self.max_priority = 5
    
    def adjust_weights(self, new_weights: Dict[str, float]) -> None:
        """Adjust the weights used for prioritization"""
        self.weights.update(new_weights)
        logger.info(f"Goal prioritization weights adjusted: {self.weights}")
    
    def evaluate_urgency(self, goal: GoalHistory) -> float:
        """Evaluate time sensitivity of a goal"""
        urgency = 1.0  # Default baseline
        
        # Check if goal has metadata with deadline
        if goal.metadata and "deadline" in goal.metadata:
            try:
                deadline = datetime.fromisoformat(goal.metadata["deadline"])
                now = datetime.now()
                time_remaining = (deadline - now).total_seconds()
                
                if time_remaining <= 0:
                    # Overdue
                    urgency = 2.0
                elif time_remaining < 3600:  # Less than 1 hour
                    urgency = 1.8
                elif time_remaining < 86400:  # Less than 1 day
                    urgency = 1.5
                elif time_remaining < 259200:  # Less than 3 days
                    urgency = 1.2
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid deadline format for goal {goal.id}: {e}")
        
        # Check for urgency keywords in goal text
        urgency_keywords = ["urgent", "immediately", "asap", "emergency", "critical"]
        if any(keyword in goal.goal_text.lower() for keyword in urgency_keywords):
            urgency += 0.5
            
        return min(urgency, 2.0)  # Cap at 2.0
    
    def evaluate_importance(self, goal: GoalHistory) -> float:
        """Evaluate strategic importance of a goal"""
        importance = 1.0  # Default baseline
        
        # Check if goal is explicitly marked as important in metadata
        if goal.metadata and "importance" in goal.metadata:
            try:
                importance = float(goal.metadata["importance"])
                importance = min(max(importance, 0.5), 2.0)  # Constrain between 0.5 and 2.0
            except (ValueError, TypeError):
                pass
        
        # Check for importance keywords in goal text
        importance_keywords = {
            "critical": 0.4,
            "important": 0.3, 
            "essential": 0.3, 
            "crucial": 0.3,
            "key": 0.2,
            "major": 0.2,
            "significant": 0.2,
            "primary": 0.2
        }
        
        for keyword, value in importance_keywords.items():
            if keyword in goal.goal_text.lower():
                importance += value
                
        return min(importance, 2.0)  # Cap at 2.0
    
    def evaluate_dependencies(self, goal: GoalHistory, all_goals: List[GoalHistory]) -> Tuple[float, List[GoalHistory]]:
        """
        Evaluate if goal has dependencies or is a dependency for others
        Returns: (dependency_score, list_of_dependent_goals)
        """
        dependency_score = 1.0  # Default baseline
        dependent_goals = []
        
        # Check if this goal is a parent for other active goals (has dependents)
        for other_goal in all_goals:
            if other_goal.parent_goal_id == goal.id:
                dependent_goals.append(other_goal)
                dependency_score += 0.2  # Increment for each dependent
        
        # Check if this goal is explicitly marked as blocking in metadata
        if goal.metadata and "blocks_goals" in goal.metadata and goal.metadata["blocks_goals"]:
            dependency_score += 0.5
            
        return min(dependency_score, 2.0), dependent_goals  # Cap at 2.0
    
    def calculate_priority_score(self, goal: GoalHistory, all_goals: List[GoalHistory]) -> float:
        """Calculate overall priority score for a goal"""
        # Start with user-specified priority (1-5 scale)
        base_priority = float(goal.priority)
        
        # Get scores for each factor
        urgency = self.evaluate_urgency(goal)
        importance = self.evaluate_importance(goal)
        dependency_score, _ = self.evaluate_dependencies(goal, all_goals)
        
        # Resource availability is assumed to be 1.0 by default
        # In a real implementation, this would check system resources, current load, etc.
        resource_avail = 1.0
        
        # Calculate weighted score
        weighted_score = (
            base_priority * self.weights["user_priority"] +
            urgency * self.weights["urgency"] +
            importance * self.weights["importance"] +
            dependency_score * self.weights["dependency"] +
            resource_avail * self.weights["resource_avail"]
        )
        
        # Normalize back to 1-5 range
        total_weight = sum(self.weights.values())
        normalized_score = (weighted_score / total_weight) * 4 + 1  # Scale to 1-5
        
        # Ensure within bounds
        priority = min(max(normalized_score, self.min_priority), self.max_priority)
        return round(priority, 1)
    
    def prioritize_goals(self, goals: List[GoalHistory]) -> List[Dict]:
        """
        Prioritize a list of goals based on various factors
        Returns sorted list of dictionaries with goal and priority information
        """
        if not goals:
            return []
            
        prioritized_goals = []
        
        for goal in goals:
            priority_score = self.calculate_priority_score(goal, goals)
            prioritized_goals.append({
                "goal": goal,
                "priority_score": priority_score,
                "original_priority": goal.priority,
                "urgency": self.evaluate_urgency(goal),
                "importance": self.evaluate_importance(goal),
                "dependency_score": self.evaluate_dependencies(goal, goals)[0]
            })
            
        # Sort by priority score (descending)
        prioritized_goals.sort(key=lambda x: x["priority_score"], reverse=True)
        return prioritized_goals
    
    def update_goal_priorities(self, session_id: Optional[uuid.UUID] = None) -> List[Dict]:
        """
        Update priorities for all active goals in the database
        Returns the list of updated goals with their new priorities
        """
        if not SessionLocal:
            logger.warning("Database connection not available, skipping goal prioritization")
            return []
        
        # Get all active goals
        active_goals = get_active_goals(session_id=session_id, limit=100)
        
        if not active_goals:
            logger.info("No active goals to prioritize")
            return []
        
        # Calculate priorities
        prioritized_goals = self.prioritize_goals(active_goals)
        
        # Update priorities in database
        session = SessionLocal()
        try:
            for goal_info in prioritized_goals:
                goal = goal_info["goal"]
                new_priority = int(round(goal_info["priority_score"]))
                
                # Only update if priority changed
                if new_priority != goal.priority:
                    goal.priority = new_priority
                    # Add metadata about prioritization
                    if not goal.metadata:
                        goal.metadata = {}
                    goal.metadata["prioritization"] = {
                        "updated_at": datetime.now().isoformat(),
                        "original_priority": goal_info["original_priority"],
                        "urgency_score": goal_info["urgency"],
                        "importance_score": goal_info["importance"],
                        "dependency_score": goal_info["dependency_score"]
                    }
            
            session.commit()
            logger.info(f"Updated priorities for {len(prioritized_goals)} goals")
        except Exception as e:
            logger.error(f"Priority update error: {e}")
            session.rollback()
        finally:
            session.close()
        
        return prioritized_goals

def goal_prioritizer_node(state: AgentState) -> AgentState:
    """
    Node for prioritizing goals in the agent workflow
    """
    logger.info("[GoalPrioritizerNode] Evaluating goals for prioritization")
    
    try:
        prioritizer = GoalPrioritizer()
        session_id = getattr(state, "session_id", None)
        
        # Get custom weights if specified
        custom_weights = getattr(state, "prioritization_weights", None)
        if custom_weights:
            prioritizer.adjust_weights(custom_weights)
        
        # Update priorities for active goals
        prioritized_goals = prioritizer.update_goal_priorities(session_id)
        
        if prioritized_goals:
            # Store top priority goals in state
            top_goals = [pg["goal"] for pg in prioritized_goals[:3]]
            state.prioritized_goals = top_goals
            state.top_priority_goal = top_goals[0] if top_goals else None
            
            logger.info(f"Top priority goal: {top_goals[0].goal_text[:50]}..." if top_goals else "No goals available")
    except Exception as e:
        logger.error(f"Goal prioritizer node error: {e}")
    
    return state
