"""
Browser control module using Playwright for advanced web automation
"""
import asyncio
from typing import Dict, Any, Optional, List, Tuple, Union
import os
import base64
from pathlib import Path
import time

from app.logger import logger

try:
    from playwright.async_api import async_playwright, Page, Browser, ElementHandle
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    logger.warning("Playwright not installed. Browser control functionality will not be available.")
    PLAYWRIGHT_AVAILABLE = False

class BrowserController:
    """
    Browser controller class for Playwright-based web automation
    """
    def __init__(self):
        self.browser = None
        self.page = None
        self.context = None
        self.playwright = None
        
        # Create screenshots directory if it doesn't exist
        self.screenshots_dir = Path(os.environ.get("AQLON_SCREENSHOTS_DIR", "./screenshots"))
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # Store browser state for persistence
        self._is_initialized = False
        self._current_url = None
        self._browser_type = "chromium"  # chromium, firefox, webkit
        
    async def initialize(self, browser_type: str = "chromium", headless: bool = False) -> bool:
        """
        Initialize browser controller
        
        Args:
            browser_type: The browser type to launch (chromium, firefox, webkit)
            headless: Whether to run in headless mode
            
        Returns:
            True if initialization was successful, False otherwise
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available. Cannot initialize browser.")
            return False
            
        if self._is_initialized and self.browser:
            logger.info("Browser already initialized.")
            return True
            
        try:
            self._browser_type = browser_type
            self.playwright = await async_playwright().start()
            
            # Get browser instance by type
            if browser_type == "firefox":
                browser_instance = self.playwright.firefox
            elif browser_type == "webkit":
                browser_instance = self.playwright.webkit
            else:  # Default to chromium
                browser_instance = self.playwright.chromium
            
            # Launch browser
            self.browser = await browser_instance.launch(headless=headless)
            self.context = await self.browser.new_context(
                viewport={"width": 1280, "height": 800}
            )
            self.page = await self.context.new_page()
            
            # Set up page event handlers
            self.page.on("console", lambda msg: logger.debug(f"Browser console {msg.type}: {msg.text}"))
            self.page.on("pageerror", lambda err: logger.error(f"Browser page error: {err}"))
            
            self._is_initialized = True
            logger.info(f"Browser initialized: {browser_type}")
            return True
        except Exception as e:
            logger.error(f"Browser initialization error: {e}")
            await self.cleanup()
            return False
    
    async def cleanup(self) -> None:
        """
        Close browser and clean up resources
        """
        try:
            if self.page:
                await self.page.close()
                self.page = None
                
            if self.context:
                await self.context.close()
                self.context = None
                
            if self.browser:
                await self.browser.close()
                self.browser = None
                
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
                
            self._is_initialized = False
            logger.info("Browser cleaned up successfully")
        except Exception as e:
            logger.error(f"Error during browser cleanup: {e}")
    
    async def navigate_to(self, url: str, wait_until: str = "load") -> bool:
        """
        Navigate to a URL
        
        Args:
            url: The URL to navigate to
            wait_until: When to consider navigation complete (load, domcontentloaded, networkidle)
            
        Returns:
            True if navigation was successful, False otherwise
        """
        if not self._ensure_initialized():
            return False
            
        try:
            await self.page.goto(url, wait_until=wait_until)
            self._current_url = url
            logger.info(f"Navigated to URL: {url}")
            return True
        except Exception as e:
            logger.error(f"Navigation error: {e}")
            return False
    
    async def take_screenshot(self, full_page: bool = False) -> Optional[str]:
        """
        Take a screenshot of the current page
        
        Args:
            full_page: Whether to take a screenshot of the full page
            
        Returns:
            Path to the screenshot file, or None if failed
        """
        if not self._ensure_initialized():
            return None
            
        try:
            timestamp = int(time.time())
            filename = f"screenshot_{timestamp}.png"
            file_path = self.screenshots_dir / filename
            
            await self.page.screenshot(path=str(file_path), full_page=full_page)
            logger.info(f"Screenshot saved to {file_path}")
            
            return str(file_path)
        except Exception as e:
            logger.error(f"Screenshot error: {e}")
            return None
    
    async def get_page_content(self) -> Optional[str]:
        """
        Get the HTML content of the current page
        
        Returns:
            HTML content, or None if failed
        """
        if not self._ensure_initialized():
            return None
            
        try:
            content = await self.page.content()
            return content
        except Exception as e:
            logger.error(f"Error getting page content: {e}")
            return None
    
    async def get_current_url(self) -> Optional[str]:
        """
        Get the current URL
        
        Returns:
            Current URL, or None if not available
        """
        if not self._ensure_initialized():
            return None
            
        try:
            url = self.page.url
            self._current_url = url
            return url
        except Exception as e:
            logger.error(f"Error getting current URL: {e}")
            return self._current_url  # Return cached URL if available
    
    async def evaluate_script(self, script: str) -> Any:
        """
        Evaluate JavaScript on the page
        
        Args:
            script: The JavaScript code to evaluate
            
        Returns:
            Result of the script evaluation
        """
        if not self._ensure_initialized():
            return None
            
        try:
            result = await self.page.evaluate(script)
            return result
        except Exception as e:
            logger.error(f"Script evaluation error: {e}")
            return None
    
    async def click_element(self, selector: str, timeout: int = 5000) -> bool:
        """
        Click an element on the page
        
        Args:
            selector: The CSS selector for the element
            timeout: Timeout in milliseconds
            
        Returns:
            True if click was successful, False otherwise
        """
        if not self._ensure_initialized():
            return False
            
        try:
            await self.page.click(selector, timeout=timeout)
            logger.info(f"Clicked element: {selector}")
            return True
        except Exception as e:
            logger.error(f"Click error: {e}")
            return False
    
    async def fill_form(self, selector: str, value: str, timeout: int = 5000) -> bool:
        """
        Fill a form field
        
        Args:
            selector: The CSS selector for the form field
            value: The value to fill
            timeout: Timeout in milliseconds
            
        Returns:
            True if fill was successful, False otherwise
        """
        if not self._ensure_initialized():
            return False
            
        try:
            await self.page.fill(selector, value, timeout=timeout)
            logger.info(f"Filled form field {selector} with value: {value}")
            return True
        except Exception as e:
            logger.error(f"Form fill error: {e}")
            return False
    
    async def wait_for_selector(self, selector: str, timeout: int = 5000, state: str = "visible") -> bool:
        """
        Wait for an element to appear on the page
        
        Args:
            selector: The CSS selector for the element
            timeout: Timeout in milliseconds
            state: State to wait for (attached, detached, visible, hidden)
            
        Returns:
            True if element appeared, False otherwise
        """
        if not self._ensure_initialized():
            return False
            
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state=state)
            logger.info(f"Selector appeared: {selector}")
            return True
        except Exception as e:
            logger.error(f"Wait for selector error: {e}")
            return False
    
    async def find_elements(self, selector: str) -> List[Dict[str, Any]]:
        """
        Find elements matching a selector
        
        Args:
            selector: The CSS selector for the elements
            
        Returns:
            List of elements with their properties
        """
        if not self._ensure_initialized():
            return []
            
        try:
            handles = await self.page.query_selector_all(selector)
            elements = []
            
            for handle in handles:
                # Extract useful properties
                text = await handle.text_content() or ""
                is_visible = await handle.is_visible()
                bounding_box = await handle.bounding_box()
                
                elements.append({
                    "text": text.strip(),
                    "visible": is_visible,
                    "bounding_box": bounding_box or {},
                    "tag_name": await handle.evaluate("el => el.tagName.toLowerCase()"),
                    "attributes": await handle.evaluate("el => Object.entries(el.attributes).reduce((attrs, attr) => { attrs[attr[1].name] = attr[1].value; return attrs; }, {})")
                })
            
            return elements
        except Exception as e:
            logger.error(f"Find elements error: {e}")
            return []
    
    def _ensure_initialized(self) -> bool:
        """
        Ensure the browser is initialized
        
        Returns:
            True if initialized, False otherwise
        """
        if not PLAYWRIGHT_AVAILABLE:
            logger.error("Playwright not available.")
            return False
            
        if not self._is_initialized or not self.browser or not self.page:
            logger.error("Browser not initialized. Call initialize() first.")
            return False
            
        return True

# Global browser controller instance
browser_controller = BrowserController() if PLAYWRIGHT_AVAILABLE else None

async def get_browser_controller() -> Optional[BrowserController]:
    """
    Get or create a browser controller instance
    
    Returns:
        Browser controller instance, or None if not available
    """
    global browser_controller
    
    if not PLAYWRIGHT_AVAILABLE:
        return None
        
    if browser_controller is None:
        browser_controller = BrowserController()
    
    if not browser_controller._is_initialized:
        await browser_controller.initialize(headless=False)
        
    return browser_controller

# Helper function to run async functions in sync context
def run_async(coro):
    """
    Run an async function in a sync context
    
    Args:
        coro: The coroutine to run
        
    Returns:
        Result of the coroutine
    """
    if asyncio.get_event_loop().is_running():
        # Already in an async context, create a new loop
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    else:
        # No running event loop, use the default loop
        return asyncio.run(coro)
