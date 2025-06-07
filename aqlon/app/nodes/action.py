# filepath: /Users/al-husseinabdullah/Desktop/aqlonv4/aqlon/app/nodes/action.py
from app.logger import logger
from app.state import AgentState
from app.nodes.vision import vision_manager, ui_extractor
import pyautogui
import time
import cv2
import numpy as np
from typing import Optional, Tuple
from PIL import ImageGrab

def find_and_click_template(template_name: str, confidence_threshold: float = 0.7) -> Tuple[bool, str]:
    """
    Find a template on screen and click its center
    Returns: (success, result_message)
    """
    try:
        # Take screenshot
        screenshot = ImageGrab.grab()
        cv_screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        # Find template
        match = vision_manager.find_template(template_name, cv_screenshot, threshold=confidence_threshold)
        
        if not match:
            return False, f"Template '{template_name}' not found on screen"
        
        # Click at the center of the match
        pyautogui.moveTo(match.center_x, match.center_y)
        time.sleep(0.1)  # Small pause for realism
        pyautogui.click()
        
        return True, f"Clicked template '{template_name}' at ({match.center_x}, {match.center_y}) with confidence {match.confidence:.2f}"
    
    except Exception as e:
        logger.error(f"Error clicking template: {e}")
        return False, f"Error clicking template: {e}"

def find_and_click_ui_element(text: str, element_type: Optional[str] = None, exact_match: bool = False) -> Tuple[bool, str]:
    """
    Find a UI element by text and/or type and click its center
    Returns: (success, result_message)
    """
    try:
        # Take screenshot to update UI elements
        screenshot = ImageGrab.grab()
        cv_screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        # Process the screenshot to extract UI elements
        ui_extractor.process_screenshot(cv_screenshot)
        
        # Find element by text
        element = None
        if text:
            element = ui_extractor.find_element_by_text(text, exact_match)
        
        # If text search failed and element_type is provided, try to find by type
        if not element and element_type:
            elements = ui_extractor.find_element_by_type(element_type)
            if elements:
                # Use the first element of the specified type
                element = elements[0]
        
        if not element:
            return False, f"UI element with text '{text}' and type '{element_type}' not found"
        
        # Get center coordinates
        center_x, center_y = element.center
        
        # Click at the center of the element
        pyautogui.moveTo(center_x, center_y)
        time.sleep(0.1)  # Small pause for realism
        pyautogui.click()
        
        return True, f"Clicked UI element with text '{element.text}' at ({center_x}, {center_y})"
    
    except Exception as e:
        logger.error(f"Error clicking UI element: {e}")
        return False, f"Error clicking UI element: {e}"

def scroll_page(direction: str = "down", amount: int = 3, pause: float = 0.1) -> Tuple[bool, str]:
    """
    Scroll page in specified direction with given amount
    Direction: "up", "down", "left", or "right"
    Amount: Number of "clicks" to scroll
    Returns: (success, result_message)
    """
    try:
        if direction.lower() == "down":
            for _ in range(amount):
                pyautogui.scroll(-100)  # Negative values scroll down
                time.sleep(pause)
        elif direction.lower() == "up":
            for _ in range(amount):
                pyautogui.scroll(100)  # Positive values scroll up
                time.sleep(pause)
        elif direction.lower() == "right":
            for _ in range(amount):
                pyautogui.hscroll(-100)  # Negative values scroll right
                time.sleep(pause)
        elif direction.lower() == "left":
            for _ in range(amount):
                pyautogui.hscroll(100)  # Positive values scroll left
                time.sleep(pause)
        else:
            return False, f"Invalid scroll direction: {direction}"
            
        return True, f"Scrolled {direction} {amount} times"
    except Exception as e:
        logger.error(f"Error scrolling: {e}")
        return False, f"Error scrolling: {e}"

def hover_at_position(x: int, y: int, duration: float = 0.5) -> Tuple[bool, str]:
    """
    Move mouse to position and hover for specified duration
    Returns: (success, result_message)
    """
    try:
        pyautogui.moveTo(x, y, duration=0.25)  # Move to position with slight animation
        time.sleep(duration)  # Hover for specified duration
        return True, f"Hovered at position ({x}, {y}) for {duration}s"
    except Exception as e:
        logger.error(f"Error hovering at position: {e}")
        return False, f"Error hovering at position: {e}"

def hover_over_template(template_name: str, duration: float = 0.5, confidence_threshold: float = 0.7) -> Tuple[bool, str]:
    """
    Hover over a template match for specified duration
    Returns: (success, result_message)
    """
    try:
        # Take screenshot
        screenshot = ImageGrab.grab()
        cv_screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        # Find template
        match = vision_manager.find_template(template_name, cv_screenshot, threshold=confidence_threshold)
        
        if not match:
            return False, f"Template '{template_name}' not found on screen"
        
        # Hover at the center of the match
        return hover_at_position(match.center_x, match.center_y, duration)
        
    except Exception as e:
        logger.error(f"Error hovering over template: {e}")
        return False, f"Error hovering over template: {e}"

def drag_and_drop(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> Tuple[bool, str]:
    """
    Perform drag and drop operation from start to end position
    Returns: (success, result_message)
    """
    try:
        # Move to start position
        pyautogui.moveTo(start_x, start_y, duration=0.25)
        
        # Perform drag and drop
        pyautogui.dragTo(end_x, end_y, duration=duration, button='left')
        
        return True, f"Dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"
    except Exception as e:
        logger.error(f"Error performing drag and drop: {e}")
        return False, f"Error performing drag and drop: {e}"

def drag_template_to_position(template_name: str, end_x: int, end_y: int, confidence_threshold: float = 0.7) -> Tuple[bool, str]:
    """
    Drag a template to a specific position
    Returns: (success, result_message)
    """
    try:
        # Take screenshot
        screenshot = ImageGrab.grab()
        cv_screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        # Find template
        match = vision_manager.find_template(template_name, cv_screenshot, threshold=confidence_threshold)
        
        if not match:
            return False, f"Template '{template_name}' not found on screen"
        
        # Drag from template center to target position
        return drag_and_drop(match.center_x, match.center_y, end_x, end_y)
        
    except Exception as e:
        logger.error(f"Error dragging template to position: {e}")
        return False, f"Error dragging template to position: {e}"

def action_node(state: AgentState) -> AgentState:
    logger.info(f"[ActionNode] Received state: {state}")
    try:
        action = getattr(state, "action", {}) or {}
        if action.get("type") == "click":
            # Direct coordinate click
            x = action.get("x")
            y = action.get("y")
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
                time.sleep(0.1)  # Small pause for realism
                pyautogui.click()
                state.action_result = f"Clicked at ({x}, {y})"
                state.action_success = True
            else:
                state.action_result = "Missing x or y for click action"
                state.action_success = False
        
        elif action.get("type") == "click_template":
            # Template matching click
            template_name = action.get("template_name")
            confidence = action.get("confidence", 0.7)
            
            if template_name:
                success, message = find_and_click_template(template_name, confidence)
                state.action_result = message
                state.action_success = success
            else:
                state.action_result = "No template name provided for click_template action"
                state.action_success = False
        
        elif action.get("type") == "click_ui_element":
            # UI element click
            text = action.get("text")
            element_type = action.get("element_type")
            exact_match = action.get("exact_match", False)
            
            if text or element_type:
                success, message = find_and_click_ui_element(text, element_type, exact_match)
                state.action_result = message
                state.action_success = success
            else:
                state.action_result = "No text or element_type provided for click_ui_element action"
                state.action_success = False
        
        elif action.get("type") == "scroll":
            # Scroll action
            direction = action.get("direction", "down")
            amount = action.get("amount", 3)
            pause = action.get("pause", 0.1)
            
            success, message = scroll_page(direction, amount, pause)
            state.action_result = message
            state.action_success = success
            
        elif action.get("type") == "hover":
            # Hover action
            x = action.get("x")
            y = action.get("y")
            duration = action.get("duration", 0.5)
            
            if x is not None and y is not None:
                success, message = hover_at_position(x, y, duration)
                state.action_result = message
                state.action_success = success
            else:
                template_name = action.get("template_name")
                if template_name:
                    confidence = action.get("confidence", 0.7)
                    success, message = hover_over_template(template_name, duration, confidence)
                    state.action_result = message
                    state.action_success = success
                else:
                    state.action_result = "Missing coordinates or template name for hover action"
                    state.action_success = False
        
        elif action.get("type") == "drag_and_drop":
            # Drag and drop action
            start_x = action.get("start_x")
            start_y = action.get("start_y")
            end_x = action.get("end_x")
            end_y = action.get("end_y")
            duration = action.get("duration", 0.5)
            
            if all(param is not None for param in [start_x, start_y, end_x, end_y]):
                success, message = drag_and_drop(start_x, start_y, end_x, end_y, duration)
                state.action_result = message
                state.action_success = success
            else:
                template_name = action.get("template_name")
                if template_name and end_x is not None and end_y is not None:
                    confidence = action.get("confidence", 0.7)
                    success, message = drag_template_to_position(template_name, end_x, end_y, confidence)
                    state.action_result = message
                    state.action_success = success
                else:
                    state.action_result = "Missing required parameters for drag and drop action"
                    state.action_success = False
        
        elif action.get("type") == "type":
            text = action.get("text")
            if text:
                pyautogui.typewrite(text)
                state.action_result = f"Typed: {text}"
                state.action_success = True
            else:
                state.action_result = "No text provided for typing"
                state.action_success = False
        
        elif action.get("type") == "hotkey":
            keys = action.get("keys")
            if keys and isinstance(keys, list) and all(isinstance(k, str) for k in keys):
                pyautogui.hotkey(*keys)
                state.action_result = f"Pressed hotkey: {' + '.join(keys)}"
                state.action_success = True
            else:
                state.action_result = "No valid keys provided for hotkey action"
                state.action_success = False
        
        elif action.get("type") == "mouse_down":
            # Mouse down action (press and hold)
            x = action.get("x")
            y = action.get("y")
            button = action.get("button", "left")
            
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
                time.sleep(0.1)
                pyautogui.mouseDown(button=button)
                state.action_result = f"Mouse down at ({x}, {y}) with {button} button"
                state.action_success = True
                state.mouse_down_at = {"x": x, "y": y, "button": button}
            else:
                state.action_result = "Missing x or y for mouse down action"
                state.action_success = False
        
        elif action.get("type") == "mouse_up":
            # Mouse up action (release)
            x = action.get("x")
            y = action.get("y")
            button = action.get("button", "left")
            
            if x is not None and y is not None:
                pyautogui.moveTo(x, y)
                time.sleep(0.1)
            
            pyautogui.mouseUp(button=button)
            
            if x is not None and y is not None:
                state.action_result = f"Mouse up at ({x}, {y}) with {button} button"
            else:
                state.action_result = f"Mouse up at current position with {button} button"
            
            state.action_success = True
            state.mouse_up_at = {"x": x or pyautogui.position()[0], 
                                 "y": y or pyautogui.position()[1],
                                 "button": button}
        
        else:
            state.action_result = "No valid action specified"
            state.action_success = False
            
        state.action_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        logger.info(f"[ActionNode] Resulting state: {state}")
    except Exception as e:
        logger.error(f"Action node error: {e}")
        state.action_result = f"Error: {e}"
        state.action_success = False
    return state

# Example test usage:
if __name__ == "__main__":
    # Basic actions
    sample_state_click = AgentState()
    sample_state_click.action = {"type": "click", "x": 100, "y": 200}
    
    sample_state_type = AgentState()
    sample_state_type.action = {"type": "type", "text": "Hello, world!"}
    
    sample_state_hotkey = AgentState()
    sample_state_hotkey.action = {"type": "hotkey", "keys": ["command", "c"]}
    
    # Template matching actions
    sample_state_template = AgentState()
    sample_state_template.action = {"type": "click_template", "template_name": "test_button", "confidence": 0.7}
    
    # UI element actions
    sample_state_ui = AgentState()
    sample_state_ui.action = {"type": "click_ui_element", "text": "Submit", "element_type": "button"}
    
    # Test an action
    result = action_node(sample_state_click)
    print(f"Action result: {result.action_result}")
