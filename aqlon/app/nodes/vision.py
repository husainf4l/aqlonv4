from app.logger import logger
from app.state import AgentState
from app.settings import settings
import datetime
import os
import numpy as np
import cv2
from openai import OpenAI
from PIL import ImageGrab, Image
import pytesseract
from typing import List, Dict, Any, Optional, Tuple, Union
import mss
from screeninfo import get_monitors

# Import UI element extractor
from app.nodes.ui_element_extractor import UIElementExtractor

# Initialize OpenAI client using settings
client = OpenAI(api_key=settings.openai_api_key)

VISION_LLM_SYSTEM_PROMPT = """
You are the Vision LLM for the AQLON agent. Given the OCR text, UI elements, and any other available context, summarize the screen and extract actionable information for the agent.
"""

class TemplateMatch:
    """Represents a template match result"""
    def __init__(self, template_name: str, confidence: float, location: Tuple[int, int, int, int]):
        self.template_name = template_name
        self.confidence = confidence  # Match confidence (0-1)
        self.x, self.y, self.w, self.h = location  # x, y, width, height
        self.center_x = self.x + (self.w // 2)
        self.center_y = self.y + (self.h // 2)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "template_name": self.template_name,
            "confidence": float(self.confidence),
            "location": {
                "x": int(self.x),
                "y": int(self.y),
                "width": int(self.w),
                "height": int(self.h)
            },
            "center": {
                "x": int(self.center_x),
                "y": int(self.center_y)
            }
        }

class VisionManager:
    """Manages vision operations including template matching"""
    def __init__(self):
        # Directory for template storage
        self.template_dir = os.path.join(settings.base_dir, "templates")
        os.makedirs(self.template_dir, exist_ok=True)
        
        # Cache of loaded templates
        self.template_cache = {}  # template_name -> (template_image, template_path)
        
        # Minimum confidence for template matching
        self.min_confidence = 0.7  # Default threshold
        
        # Initialize screen capture tool
        self.mss = mss.mss()
        
        # Get monitor information
        try:
            self.monitors = get_monitors()
            logger.info(f"Detected {len(self.monitors)} monitors")
            for i, m in enumerate(self.monitors):
                logger.info(f"Monitor {i}: {m.width}x{m.height} at ({m.x}, {m.y})")
        except Exception as e:
            logger.warning(f"Failed to get monitor information: {e}")
            self.monitors = []
        
        logger.info(f"Vision manager initialized with template directory: {self.template_dir}")
        
        # OCR confidence threshold
        self.ocr_confidence_threshold = 60  # Default threshold percentage
        
        # Load any existing templates
        self._load_templates()
    
    def _load_templates(self) -> None:
        """Load all templates from the template directory"""
        if not os.path.exists(self.template_dir):
            logger.warning(f"Template directory does not exist: {self.template_dir}")
            return
        
        count = 0
        for filename in os.listdir(self.template_dir):
            if filename.endswith(('.png', '.jpg', '.jpeg')):
                template_name = os.path.splitext(filename)[0]
                template_path = os.path.join(self.template_dir, filename)
                
                try:
                    template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
                    if template_img is not None:
                        self.template_cache[template_name] = (template_img, template_path)
                        count += 1
                    else:
                        logger.error(f"Failed to load template image: {template_path}")
                except Exception as e:
                    logger.error(f"Error loading template {template_path}: {e}")
        
        logger.info(f"Loaded {count} templates from {self.template_dir}")
    
    def save_template(self, template_name: str, image: Image.Image) -> str:
        """
        Save a new template from a PIL Image
        Returns the path to the saved template
        """
        # Ensure template name is valid
        safe_name = template_name.replace(' ', '_').lower()
        if not safe_name.endswith(('.png', '.jpg', '.jpeg')):
            safe_name += '.png'
        
        # Create template path
        template_path = os.path.join(self.template_dir, safe_name)
        
        # Save the image
        image.save(template_path)
        
        # Convert to OpenCV format and add to cache
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        self.template_cache[os.path.splitext(safe_name)[0]] = (cv_image, template_path)
        
        logger.info(f"Saved new template: {template_path}")
        return template_path
    
    def save_template_from_region(self, 
                                 template_name: str, 
                                 screenshot: Image.Image, 
                                 region: Tuple[int, int, int, int]) -> str:
        """
        Save a template from a region of a screenshot
        Region format: (x, y, width, height)
        """
        x, y, w, h = region
        template_image = screenshot.crop((x, y, x + w, y + h))
        return self.save_template(template_name, template_image)
    
    def find_template(self, 
                     template_name: str, 
                     screenshot: np.ndarray,
                     threshold: Optional[float] = None) -> Optional[TemplateMatch]:
        """
        Find a single template in the screenshot
        Returns the best match or None if no match found above threshold
        """
        if threshold is None:
            threshold = self.min_confidence
        
        # Check if template exists in cache
        if template_name not in self.template_cache:
            template_path = os.path.join(self.template_dir, f"{template_name}.png")
            if os.path.exists(template_path):
                try:
                    template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
                    self.template_cache[template_name] = (template_img, template_path)
                except Exception as e:
                    logger.error(f"Error loading template {template_path}: {e}")
                    return None
            else:
                logger.error(f"Template not found: {template_name}")
                return None
        
        # Get template from cache
        template_img, _ = self.template_cache[template_name]
        
        # Check if template is valid
        if template_img is None:
            logger.error(f"Invalid template image for {template_name}")
            return None
        
        # Match template
        try:
            result = cv2.matchTemplate(screenshot, template_img, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            
            if max_val >= threshold:
                # Get template dimensions for bounding box
                h, w = template_img.shape[:2]
                match = TemplateMatch(
                    template_name=template_name,
                    confidence=max_val,
                    location=(max_loc[0], max_loc[1], w, h)
                )
                return match
            else:
                logger.debug(f"No match found for {template_name} above threshold {threshold} (best: {max_val:.2f})")
                return None
        except Exception as e:
            logger.error(f"Error matching template {template_name}: {e}")
            return None
    
    def find_all_templates(self, 
                         template_name: str, 
                         screenshot: np.ndarray,
                         threshold: Optional[float] = None) -> List[TemplateMatch]:
        """
        Find all occurrences of a template in the screenshot
        Returns a list of matches sorted by confidence (highest first)
        """
        if threshold is None:
            threshold = self.min_confidence
        
        # Check if template exists
        if template_name not in self.template_cache:
            template_path = os.path.join(self.template_dir, f"{template_name}.png")
            if os.path.exists(template_path):
                try:
                    template_img = cv2.imread(template_path, cv2.IMREAD_COLOR)
                    self.template_cache[template_name] = (template_img, template_path)
                except Exception as e:
                    logger.error(f"Error loading template {template_path}: {e}")
                    return []
            else:
                logger.error(f"Template not found: {template_name}")
                return []
        
        # Get template from cache
        template_img, _ = self.template_cache[template_name]
        
        # Check if template is valid
        if template_img is None:
            logger.error(f"Invalid template image for {template_name}")
            return []
        
        # Match template
        try:
            result = cv2.matchTemplate(screenshot, template_img, cv2.TM_CCOEFF_NORMED)
            h, w = template_img.shape[:2]
            
            # Find all matches above threshold
            locations = np.where(result >= threshold)
            matches = []
            
            # Convert to x,y coordinates and create match objects
            for pt in zip(*locations[::-1]):  # Reverse to get x,y format
                match = TemplateMatch(
                    template_name=template_name,
                    confidence=result[pt[1], pt[0]],
                    location=(pt[0], pt[1], w, h)
                )
                matches.append(match)
            
            # Sort by confidence (highest first)
            matches.sort(key=lambda x: x.confidence, reverse=True)
            
            # Filter out overlapping matches (non-maximum suppression)
            filtered_matches = []
            while matches:
                # Take the best match
                best_match = matches.pop(0)
                filtered_matches.append(best_match)
                
                # Filter out overlapping matches
                non_overlapping = []
                for match in matches:
                    # Calculate IoU (Intersection over Union)
                    x1 = max(best_match.x, match.x)
                    y1 = max(best_match.y, match.y)
                    x2 = min(best_match.x + best_match.w, match.x + match.w)
                    y2 = min(best_match.y + best_match.h, match.y + match.h)
                    
                    if x2 < x1 or y2 < y1:
                        # No overlap
                        non_overlapping.append(match)
                        continue
                    
                    # Calculate overlap area
                    overlap_area = (x2 - x1) * (y2 - y1)
                    best_area = best_match.w * best_match.h
                    match_area = match.w * match.h
                    union_area = best_area + match_area - overlap_area
                    iou = overlap_area / union_area
                    
                    # If IoU is small enough, keep the match
                    if iou < 0.5:  # 0.5 is a typical threshold
                        non_overlapping.append(match)
                
                # Update remaining matches
                matches = non_overlapping
            
            logger.info(f"Found {len(filtered_matches)} matches for {template_name}")
            return filtered_matches
        except Exception as e:
            logger.error(f"Error matching template {template_name}: {e}")
            return []
    
    def get_monitor_count(self) -> int:
        """Get the number of available monitors"""
        return len(self.monitors)
    
    def get_monitor_info(self) -> List[Dict[str, Any]]:
        """Get information about all available monitors"""
        return [
            {
                "index": i,
                "name": f"Monitor {i+1}",
                "width": m.width,
                "height": m.height,
                "x": m.x,
                "y": m.y
            }
            for i, m in enumerate(self.monitors)
        ]
    
    def capture_monitor(self, monitor_index: int = 0) -> Optional[Image.Image]:
        """
        Capture screenshot from a specific monitor
        Returns PIL Image or None if failed
        """
        try:
            if monitor_index < 0 or monitor_index >= len(self.monitors):
                logger.error(f"Invalid monitor index: {monitor_index}")
                return None
                
            monitor = self.monitors[monitor_index]
            monitor_dict = {
                "top": monitor.y,
                "left": monitor.x,
                "width": monitor.width,
                "height": monitor.height
            }
            
            # Capture using mss
            screenshot = self.mss.grab(monitor_dict)
            # Convert to PIL Image
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return img
            
        except Exception as e:
            logger.error(f"Error capturing monitor {monitor_index}: {e}")
            return None
    
    def capture_all_monitors(self) -> List[Image.Image]:
        """Capture screenshots from all monitors"""
        return [self.capture_monitor(i) for i in range(len(self.monitors)) if self.capture_monitor(i) is not None]
    
    def capture_region(self, x: int, y: int, width: int, height: int) -> Optional[Image.Image]:
        """
        Capture a specific region of the screen
        Returns PIL Image or None if failed
        """
        try:
            region = {"top": y, "left": x, "width": width, "height": height}
            screenshot = self.mss.grab(region)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
            return img
        except Exception as e:
            logger.error(f"Error capturing region ({x}, {y}, {width}, {height}): {e}")
            return None
    
    def process_ocr_with_confidence(self, image: Image.Image) -> Dict[str, Any]:
        """
        Process OCR with confidence values for each word
        Returns dictionary with text and word-level confidence data
        """
        try:
            # Get detailed OCR data
            ocr_data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
            
            # Extract words with confidence
            words_with_confidence = []
            full_text = ""
            
            for i, word in enumerate(ocr_data['text']):
                if word.strip():  # Skip empty words
                    confidence = ocr_data['conf'][i]
                    word_data = {
                        "word": word,
                        "confidence": confidence,
                        "box": {
                            "x": ocr_data['left'][i],
                            "y": ocr_data['top'][i],
                            "width": ocr_data['width'][i],
                            "height": ocr_data['height'][i]
                        },
                        "is_reliable": confidence >= self.ocr_confidence_threshold
                    }
                    words_with_confidence.append(word_data)
                    full_text += word + " "
            
            # Calculate overall confidence
            if words_with_confidence:
                avg_confidence = sum(w['confidence'] for w in words_with_confidence) / len(words_with_confidence)
            else:
                avg_confidence = 0
                
            return {
                "full_text": full_text.strip(),
                "words": words_with_confidence,
                "avg_confidence": avg_confidence,
                "reliable_text_only": " ".join([w['word'] for w in words_with_confidence if w['is_reliable']])
            }
        except Exception as e:
            logger.error(f"Error in OCR processing: {e}")
            return {
                "full_text": "",
                "words": [],
                "avg_confidence": 0,
                "reliable_text_only": ""
            }
    
    def verify_text_in_image(self, image: Image.Image, text: str, min_confidence: float = None) -> Dict[str, Any]:
        """
        Verify if text appears in the image with specified confidence
        Returns results with location and confidence information
        """
        if min_confidence is None:
            min_confidence = self.ocr_confidence_threshold
            
        ocr_result = self.process_ocr_with_confidence(image)
        text_lower = text.lower()
        
        # Check if text appears in any of the detected words
        found_instances = []
        for word_data in ocr_result['words']:
            if text_lower in word_data['word'].lower() and word_data['confidence'] >= min_confidence:
                found_instances.append(word_data)
                
        return {
            "text": text,
            "found": len(found_instances) > 0,
            "instances": found_instances,
            "confidence": max([w['confidence'] for w in found_instances], default=0)
        }
        
# Initialize global vision manager
vision_manager = VisionManager()

# Initialize UI element extractor
ui_extractor = UIElementExtractor()

def vision_node(state: AgentState) -> AgentState:
    logger.info(f"[VisionNode] Received state: {state}")
    try:
        timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Check if we should capture a specific monitor
        monitor_index = getattr(state, "monitor_index", 0)
        
        # Check if we should capture a specific region
        capture_region = getattr(state, "capture_region", None)
        
        # Capture appropriate screenshot based on options
        if capture_region:
            x, y, width, height = (
                capture_region.get("x", 0),
                capture_region.get("y", 0), 
                capture_region.get("width", 800),
                capture_region.get("height", 600)
            )
            screenshot = vision_manager.capture_region(x, y, width, height)
            logger.info(f"[VisionNode] Captured region: ({x}, {y}, {width}, {height})")
        else:
            # Try to capture specific monitor
            try:
                screenshot = vision_manager.capture_monitor(monitor_index)
                logger.info(f"[VisionNode] Captured monitor: {monitor_index}")
            except Exception as e:
                logger.warning(f"Failed to capture monitor {monitor_index}: {e}, falling back to primary screen")
                screenshot = ImageGrab.grab()
        
        if screenshot is None:
            logger.error("[VisionNode] Failed to capture screenshot")
            state.vision_error = "Failed to capture screenshot"
            return state
        
        # Save screenshot to a temp file (optional, for debugging)
        temp_path = f"/tmp/aqlon_screenshot_{timestamp}.png"
        screenshot.save(temp_path)
        
        # Convert to OpenCV format for computer vision operations
        cv_screenshot = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        
        # Process OCR with confidence information if requested
        detailed_ocr = getattr(state, "detailed_ocr", False)
        if detailed_ocr:
            ocr_result = vision_manager.process_ocr_with_confidence(screenshot)
            state.ocr_result = ocr_result
            state.vision_state = ocr_result["reliable_text_only"]  # Use only reliable text
            state.ocr_confidence = ocr_result["avg_confidence"]
        else:
            # Basic OCR
            ocr_text = pytesseract.image_to_string(screenshot)
            state.vision_state = ocr_text
            
        state.vision_timestamp = timestamp
        state.vision_screenshot_path = temp_path
        
        # Template matching - check if templates are specified
        template_matches = {}
        template_names = getattr(state, "template_names_to_find", [])
        
        if template_names:
            for template_name in template_names:
                match = vision_manager.find_template(template_name, cv_screenshot)
                if match:
                    template_matches[template_name] = match.to_dict()
        
        # Store template matching results
        state.template_matches = template_matches
        
        # Find all templates if requested
        find_all_templates = getattr(state, "find_all_templates", False)
        if find_all_templates:
            all_template_matches = {}
            for template_name in template_names:
                matches = vision_manager.find_all_templates(template_name, cv_screenshot)
                if matches:
                    all_template_matches[template_name] = [match.to_dict() for match in matches]
            
            state.all_template_matches = all_template_matches
        
        # Verify text presence if specified
        text_to_verify = getattr(state, "text_to_verify", None)
        if text_to_verify:
            min_confidence = getattr(state, "text_verification_confidence", vision_manager.ocr_confidence_threshold)
            verification_results = {}
            
            if isinstance(text_to_verify, str):
                # Single text verification
                result = vision_manager.verify_text_in_image(screenshot, text_to_verify, min_confidence)
                verification_results = result
            elif isinstance(text_to_verify, list):
                # Multiple text verifications
                for text in text_to_verify:
                    result = vision_manager.verify_text_in_image(screenshot, text, min_confidence)
                    verification_results[text] = result
            
            state.text_verification_results = verification_results
            
        # Extract UI elements if requested
        extract_ui_elements = getattr(state, "extract_ui_elements", True)
        if extract_ui_elements:
            ui_elements = ui_extractor.process_screenshot(cv_screenshot)
            state.ui_elements = ui_elements
            
            # Create simplified UI summary for LLM
            ui_summary = {
                "count": ui_elements["element_count"],
                "types": ui_elements["element_types"],
                "root_elements": len(ui_elements["root_elements"]),
            }
            
            # Extract text elements for easier access
            text_elements = [
                element for element_id, element in ui_elements["elements"].items()
                if element["element_type"] == "text" and element["text"]
            ]
            state.text_elements = text_elements
            
            # Extract button elements for easier access
            button_elements = [
                element for element_id, element in ui_elements["elements"].items()
                if element["element_type"] == "button"
            ]
            state.button_elements = button_elements
        
        # Vision LLM step
        try:
            # Include template matching results in prompt if available
            user_content = ocr_text or ""
            
            # Add template matching results if available
            if template_matches:
                user_content += f"\n\nTemplate matches found: {template_matches}"
            
            # Add UI element summary if available
            if extract_ui_elements:
                user_content += f"\n\nUI elements detected: {ui_summary}"
                
                # Include most confident text elements
                confident_texts = [e["text"] for e in text_elements[:5] if e["confidence"] > 0.7]
                if confident_texts:
                    user_content += f"\n\nDetected text elements: {', '.join(confident_texts)}"
            
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": VISION_LLM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                max_tokens=256,
                temperature=0.2
            )
            vision_llm_summary = response.choices[0].message.content.strip()
            state.vision_llm_summary = vision_llm_summary
        except Exception as llm_e:
            logger.error(f"Vision LLM error: {llm_e}")
            state.vision_llm_summary = ""
            state.vision_llm_error = str(llm_e)
        logger.info(f"[VisionNode] Resulting state: {state}")
    except Exception as e:
        logger.error(f"Vision node error: {e}")
        state.vision_state = ""
        state.vision_error = str(e)
    return state

# Save template from screenshot region
def save_template_from_screenshot(name: str, region: Tuple[int, int, int, int] = None) -> str:
    """
    Take screenshot and save as template
    If region is provided, will crop to that region
    Returns path to the saved template
    """
    try:
        # Take screenshot
        screenshot = ImageGrab.grab()
        
        # If region provided, crop the image
        if region:
            return vision_manager.save_template_from_region(name, screenshot, region)
        else:
            return vision_manager.save_template(name, screenshot)
    except Exception as e:
        logger.error(f"Error saving template from screenshot: {e}")
        return None

# Function to find UI element by text content
def find_element_by_text(text: str, exact_match: bool = False):
    """Find a UI element by its text content"""
    return ui_extractor.find_element_by_text(text, exact_match)

# Example test usage:
if __name__ == "__main__":
    sample_state = AgentState()
    sample_state.template_names_to_find = ["test_button"]
    sample_state.extract_ui_elements = True
    result = vision_node(sample_state)
    print(result.vision_state)
    print(result.vision_llm_summary)
    print(f"Detected {len(result.text_elements)} text elements")
    print(f"Detected {len(result.button_elements)} button elements")
