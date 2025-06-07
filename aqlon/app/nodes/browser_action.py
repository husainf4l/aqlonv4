"""
Upgraded Action node with Playwright browser control integration
"""
from app.logger import logger
from app.state import AgentState
import time
import asyncio
from typing import Optional, Dict, Any, Tuple, List
import json

# Import original action module functionality
from app.nodes.action import (
    find_and_click_template,
    find_and_click_ui_element,
    scroll_page,
    hover_at_position,
    hover_over_template,
    drag_and_drop,
    drag_template_to_position
)

# Import browser control functionality
from app.browser_control import get_browser_controller, run_async, PLAYWRIGHT_AVAILABLE

async def browser_navigate(url: str) -> Tuple[bool, str]:
    """
    Navigate browser to URL
    
    Args:
        url: The URL to navigate to
        
    Returns:
        (success, result_message)
    """
    try:
        browser = await get_browser_controller()
        if not browser:
            return False, "Browser controller not available"
            
        success = await browser.navigate_to(url)
        
        if success:
            return True, f"Navigated to {url}"
        else:
            return False, f"Failed to navigate to {url}"
    except Exception as e:
        logger.error(f"Browser navigation error: {e}")
        return False, f"Browser navigation error: {e}"

async def browser_click(selector: str) -> Tuple[bool, str]:
    """
    Click element in browser
    
    Args:
        selector: CSS selector for the element
        
    Returns:
        (success, result_message)
    """
    try:
        browser = await get_browser_controller()
        if not browser:
            return False, "Browser controller not available"
            
        success = await browser.click_element(selector)
        
        if success:
            return True, f"Clicked element: {selector}"
        else:
            return False, f"Failed to click element: {selector}"
    except Exception as e:
        logger.error(f"Browser click error: {e}")
        return False, f"Browser click error: {e}"

async def browser_fill_form(selector: str, value: str) -> Tuple[bool, str]:
    """
    Fill form field in browser
    
    Args:
        selector: CSS selector for the form field
        value: Value to fill
        
    Returns:
        (success, result_message)
    """
    try:
        browser = await get_browser_controller()
        if not browser:
            return False, "Browser controller not available"
            
        success = await browser.fill_form(selector, value)
        
        if success:
            return True, f"Filled form field {selector} with value: {value}"
        else:
            return False, f"Failed to fill form field: {selector}"
    except Exception as e:
        logger.error(f"Browser form fill error: {e}")
        return False, f"Browser form fill error: {e}"

async def browser_screenshot() -> Tuple[bool, str, Optional[str]]:
    """
    Take browser screenshot
    
    Returns:
        (success, result_message, screenshot_path)
    """
    try:
        browser = await get_browser_controller()
        if not browser:
            return False, "Browser controller not available", None
            
        screenshot_path = await browser.take_screenshot(full_page=True)
        
        if screenshot_path:
            return True, f"Screenshot taken: {screenshot_path}", screenshot_path
        else:
            return False, "Failed to take screenshot", None
    except Exception as e:
        logger.error(f"Browser screenshot error: {e}")
        return False, f"Browser screenshot error: {e}", None

async def browser_evaluate(script: str) -> Tuple[bool, str, Any]:
    """
    Evaluate JavaScript in browser
    
    Args:
        script: JavaScript to evaluate
        
    Returns:
        (success, result_message, script_result)
    """
    try:
        browser = await get_browser_controller()
        if not browser:
            return False, "Browser controller not available", None
            
        result = await browser.evaluate_script(script)
        
        result_str = str(result)
        if len(result_str) > 100:
            result_str = result_str[:100] + "... (truncated)"
            
        return True, f"Script evaluated with result: {result_str}", result
    except Exception as e:
        logger.error(f"Browser script evaluation error: {e}")
        return False, f"Browser script evaluation error: {e}", None

async def browser_get_page_info() -> Dict[str, Any]:
    """
    Get current page information
    
    Returns:
        Dictionary with page information
    """
    try:
        browser = await get_browser_controller()
        if not browser:
            return {"error": "Browser controller not available"}
            
        # Get basic page info
        page_info = {
            "url": await browser.get_current_url(),
            "title": await browser.evaluate_script("document.title"),
        }
        
        # Get key elements
        try:
            page_info["elements"] = {
                "links": len(await browser.find_elements("a")),
                "buttons": len(await browser.find_elements("button")),
                "inputs": len(await browser.find_elements("input")),
                "images": len(await browser.find_elements("img")),
            }
            
            # Extract meta information
            meta_tags = await browser.evaluate_script("""
                Array.from(document.querySelectorAll('meta')).map(m => ({
                    name: m.getAttribute('name'),
                    property: m.getAttribute('property'),
                    content: m.getAttribute('content')
                })).filter(m => m.name || m.property)
            """)
            page_info["meta"] = meta_tags
            
            # Get main content text
            main_content = await browser.evaluate_script("""
                Array.from(document.querySelectorAll('h1, h2, p')).slice(0, 10).map(el => el.textContent.trim())
            """)
            page_info["content_preview"] = main_content
            
        except Exception as inner_e:
            logger.error(f"Error extracting page elements: {inner_e}")
            page_info["elements_error"] = str(inner_e)
        
        return page_info
    except Exception as e:
        logger.error(f"Error getting page info: {e}")
        return {"error": str(e)}

def browser_action_node(state: AgentState) -> AgentState:
    """
    Enhanced action node with browser control support
    
    Args:
        state: Agent state
        
    Returns:
        Updated agent state
    """
    logger.info(f"[BrowserActionNode] Received state: {state}")
    
    try:
        action = getattr(state, "action", {}) or {}
        action_type = action.get("type", "")
        
        if not PLAYWRIGHT_AVAILABLE and action_type.startswith("browser_"):
            state.action_result = "Browser actions not available: Playwright not installed"
            state.action_success = False
            return state
            
        # Browser actions
        if action_type == "browser_navigate":
            url = action.get("url")
            if url:
                success, message = run_async(browser_navigate(url))
                state.action_result = message
                state.action_success = success
                
                if success:
                    # Get page info after navigation
                    page_info = run_async(browser_get_page_info())
                    state.browser_page_info = page_info
            else:
                state.action_result = "No URL provided for browser navigation"
                state.action_success = False
                
        elif action_type == "browser_click":
            selector = action.get("selector")
            if selector:
                success, message = run_async(browser_click(selector))
                state.action_result = message
                state.action_success = success
                
                # Small delay to allow for page changes
                time.sleep(0.5)
                
                # Get updated page info
                page_info = run_async(browser_get_page_info())
                state.browser_page_info = page_info
            else:
                state.action_result = "No selector provided for browser click"
                state.action_success = False
                
        elif action_type == "browser_fill":
            selector = action.get("selector")
            value = action.get("value")
            if selector and value is not None:
                success, message = run_async(browser_fill_form(selector, value))
                state.action_result = message
                state.action_success = success
            else:
                state.action_result = "Missing selector or value for browser form fill"
                state.action_success = False
                
        elif action_type == "browser_screenshot":
            success, message, screenshot_path = run_async(browser_screenshot())
            state.action_result = message
            state.action_success = success
            if success and screenshot_path:
                state.browser_screenshot_path = screenshot_path
                
        elif action_type == "browser_evaluate":
            script = action.get("script")
            if script:
                success, message, result = run_async(browser_evaluate(script))
                state.action_result = message
                state.action_success = success
                state.browser_script_result = result
            else:
                state.action_result = "No script provided for browser evaluation"
                state.action_success = False
                
        elif action_type == "browser_get_info":
            page_info = run_async(browser_get_page_info())
            state.browser_page_info = page_info
            state.action_result = f"Retrieved page info for {page_info.get('url', 'unknown URL')}"
            state.action_success = "error" not in page_info
            
        # Fall back to original action node implementation for non-browser actions
        else:
            from app.nodes.action import action_node
            state = action_node(state)
            
        state.action_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    except Exception as e:
        logger.error(f"Browser action node error: {e}")
        state.action_result = f"Error: {e}"
        state.action_success = False
        
    logger.info(f"[BrowserActionNode] Resulting state: {state}")
    return state
