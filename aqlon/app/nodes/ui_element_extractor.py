"""
UI Element Extraction Module for AQLon Vision System

This module provides functionality for extracting UI elements from screenshots
and building a basic element hierarchy for navigation and interaction.
"""

import numpy as np
import cv2
import pytesseract
from PIL import Image
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union
import json

from app.logger import logger

@dataclass
class UIElement:
    """Represents a UI element on screen"""
    element_id: str  # Unique identifier for the element
    element_type: str  # button, text, link, image, input, etc.
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    text: Optional[str] = None  # Text content if available
    confidence: float = 1.0  # Detection confidence
    parent_id: Optional[str] = None  # Parent element ID
    children: List[str] = field(default_factory=list)  # Child element IDs
    attributes: Dict[str, Any] = field(default_factory=dict)  # Additional attributes
    
    @property
    def center(self) -> Tuple[int, int]:
        """Get center coordinates of the element"""
        x, y, w, h = self.bbox
        return (x + w // 2, y + h // 2)
    
    @property
    def area(self) -> int:
        """Get area of the element bounding box"""
        _, _, w, h = self.bbox
        return w * h
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "element_id": self.element_id,
            "element_type": self.element_type,
            "bbox": {
                "x": self.bbox[0],
                "y": self.bbox[1],
                "width": self.bbox[2],
                "height": self.bbox[3]
            },
            "text": self.text,
            "confidence": self.confidence,
            "parent_id": self.parent_id,
            "children": self.children,
            "attributes": self.attributes,
            "center": {
                "x": self.center[0],
                "y": self.center[1]
            }
        }

    def contains_point(self, x: int, y: int) -> bool:
        """Check if the element contains the given point"""
        el_x, el_y, el_w, el_h = self.bbox
        return (el_x <= x <= el_x + el_w) and (el_y <= y <= el_y + el_h)
    
    def contains_element(self, other: 'UIElement') -> bool:
        """Check if this element fully contains another element"""
        x1, y1, w1, h1 = self.bbox
        x2, y2, w2, h2 = other.bbox
        
        return (x1 <= x2 and y1 <= y2 and 
                x1 + w1 >= x2 + w2 and 
                y1 + h1 >= y2 + h2)
    
    def overlaps_with(self, other: 'UIElement') -> bool:
        """Check if this element overlaps with another element"""
        x1, y1, w1, h1 = self.bbox
        x2, y2, w2, h2 = other.bbox
        
        # Check if one rectangle is to the left of the other
        if x1 + w1 <= x2 or x2 + w2 <= x1:
            return False
        
        # Check if one rectangle is above the other
        if y1 + h1 <= y2 or y2 + h2 <= y1:
            return False
        
        return True
    
    def overlap_area(self, other: 'UIElement') -> int:
        """Calculate the overlap area with another element"""
        x1, y1, w1, h1 = self.bbox
        x2, y2, w2, h2 = other.bbox
        
        # Calculate intersection
        x_overlap = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
        y_overlap = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
        
        return x_overlap * y_overlap

class UIElementExtractor:
    """Extracts UI elements from screenshots and builds hierarchy"""
    
    def __init__(self):
        # Detection parameters
        self.text_confidence_threshold = 60  # OCR confidence threshold
        self.button_match_threshold = 0.6  # Template matching threshold for buttons
        
        # Element counter for generating IDs
        self.element_counter = 0
        
        # Cache of processed results
        self.last_elements = {}  # ID -> UIElement
        self.root_elements = []  # List of top-level element IDs
        
        logger.info("UI Element Extractor initialized")
    
    def _generate_element_id(self, prefix: str = "element") -> str:
        """Generate a unique element ID"""
        self.element_counter += 1
        return f"{prefix}_{self.element_counter}"
    
    def extract_text_elements(self, image: np.ndarray) -> List[UIElement]:
        """Extract text elements from image using OCR"""
        elements = []
        
        # Convert image to RGB for OCR if needed
        if len(image.shape) == 3 and image.shape[2] == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
            
        # Get detailed OCR results with bounding boxes
        try:
            ocr_data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
            
            # Process each detected text element
            for i, conf in enumerate(ocr_data["conf"]):
                # Filter out low confidence and empty text
                if conf < self.text_confidence_threshold:
                    continue
                    
                text = ocr_data["text"][i].strip()
                if not text:
                    continue
                
                # Get bounding box
                x = ocr_data["left"][i]
                y = ocr_data["top"][i]
                w = ocr_data["width"][i]
                h = ocr_data["height"][i]
                
                # Create text element
                element = UIElement(
                    element_id=self._generate_element_id("text"),
                    element_type="text",
                    bbox=(x, y, w, h),
                    text=text,
                    confidence=float(conf) / 100.0,
                    attributes={
                        "block_num": ocr_data["block_num"][i],
                        "par_num": ocr_data["par_num"][i],
                        "line_num": ocr_data["line_num"][i],
                        "word_num": ocr_data["word_num"][i]
                    }
                )
                elements.append(element)
        except Exception as e:
            logger.error(f"Text extraction error: {e}")
        
        return elements
    
    def detect_ui_containers(self, image: np.ndarray) -> List[UIElement]:
        """Detect UI containers like panels, sections, etc."""
        containers = []
        
        try:
            # Convert image to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive thresholding
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Find contours
            contours, _ = cv2.findContours(
                binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            # Filter contours by size and shape
            for contour in contours:
                # Skip small contours
                area = cv2.contourArea(contour)
                if area < 5000:  # Minimum container size
                    continue
                
                # Get bounding box
                x, y, w, h = cv2.boundingRect(contour)
                
                # Skip if taking up most of the screen (likely background)
                image_area = image.shape[0] * image.shape[1]
                if (w * h) > (0.9 * image_area):
                    continue
                
                # Create container element
                element = UIElement(
                    element_id=self._generate_element_id("container"),
                    element_type="container",
                    bbox=(x, y, w, h),
                    confidence=min(1.0, area / 10000),  # Size-based confidence
                    attributes={
                        "area": area,
                        "contour_points": len(contour)
                    }
                )
                containers.append(element)
                
        except Exception as e:
            logger.error(f"Container detection error: {e}")
        
        return containers
    
    def detect_buttons(self, image: np.ndarray) -> List[UIElement]:
        """Detect button-like UI elements"""
        buttons = []
        
        try:
            # Convert image to grayscale
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            
            # Apply Gaussian blur to reduce noise
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            
            # Detect edges
            edges = cv2.Canny(blurred, 50, 150)
            
            # Dilate the edges to connect nearby edges
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            dilated = cv2.dilate(edges, kernel, iterations=2)
            
            # Find contours
            contours, _ = cv2.findContours(
                dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            # Filter contours that could be buttons
            for contour in contours:
                # Skip very small contours
                area = cv2.contourArea(contour)
                if area < 500 or area > 50000:  # Size constraints
                    continue
                
                # Get bounding box
                x, y, w, h = cv2.boundingRect(contour)
                
                # Check aspect ratio (buttons are usually wider than tall, but not extremely so)
                aspect_ratio = float(w) / h if h > 0 else 0
                if aspect_ratio < 0.5 or aspect_ratio > 5:
                    continue
                
                # Calculate approximation of contour to check if it's rectangular
                epsilon = 0.02 * cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, epsilon, True)
                
                # Calculate confidence based on shape and size
                confidence = 0.5  # Base confidence
                
                # Higher confidence for rectangular shapes
                if len(approx) == 4:
                    confidence += 0.3
                
                # Check for uniform color inside (common for buttons)
                mask = np.zeros_like(gray)
                cv2.drawContours(mask, [contour], 0, 255, -1)
                mean, stddev = cv2.meanStdDev(gray, mask=mask)
                
                # If color is uniform (low standard deviation), increase confidence
                if stddev[0][0] < 30:
                    confidence += 0.1
                
                # Create button element
                element = UIElement(
                    element_id=self._generate_element_id("button"),
                    element_type="button",
                    bbox=(x, y, w, h),
                    confidence=min(confidence, 1.0),
                    attributes={
                        "area": area,
                        "aspect_ratio": aspect_ratio,
                        "corners": len(approx),
                        "color_stddev": float(stddev[0][0])
                    }
                )
                buttons.append(element)
                
        except Exception as e:
            logger.error(f"Button detection error: {e}")
        
        return buttons
    
    def build_hierarchy(self, elements: List[UIElement]) -> Tuple[Dict[str, UIElement], List[str]]:
        """
        Build parent-child relationships between elements
        Returns: dict of elements by ID and list of root element IDs
        """
        # Sort elements by area (largest first)
        sorted_elements = sorted(elements, key=lambda e: e.area, reverse=True)
        
        # Map of element ID to element
        element_map = {e.element_id: e for e in sorted_elements}
        
        # Root elements (no parent)
        root_element_ids = []
        
        # For each element (smaller ones)
        for i, element in enumerate(sorted_elements):
            # Check if already has a parent
            if element.parent_id:
                continue
                
            parent_found = False
            
            # Look for potential parent (among larger elements)
            for j in range(i):
                potential_parent = sorted_elements[j]
                
                # Skip if same element
                if potential_parent.element_id == element.element_id:
                    continue
                
                # Check if potential_parent contains this element
                if potential_parent.contains_element(element):
                    # Set parent-child relationship
                    element.parent_id = potential_parent.element_id
                    potential_parent.children.append(element.element_id)
                    parent_found = True
                    break
            
            # If no parent found, it's a root element
            if not parent_found:
                root_element_ids.append(element.element_id)
        
        return element_map, root_element_ids
    
    def process_screenshot(self, screenshot: Union[np.ndarray, Image.Image]) -> Dict[str, Any]:
        """
        Process a screenshot to extract UI elements and build hierarchy
        Returns a dict with elements and hierarchy information
        """
        # Convert PIL Image to numpy array if needed
        if isinstance(screenshot, Image.Image):
            cv_image = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        else:
            cv_image = screenshot
        
        # Reset element counter
        self.element_counter = 0
        
        # Extract different types of elements
        text_elements = self.extract_text_elements(cv_image)
        container_elements = self.detect_ui_containers(cv_image)
        button_elements = self.detect_buttons(cv_image)
        
        # Combine all elements
        all_elements = text_elements + container_elements + button_elements
        
        # Build hierarchy
        element_map, root_element_ids = self.build_hierarchy(all_elements)
        
        # Save results to cache
        self.last_elements = element_map
        self.root_elements = root_element_ids
        
        # Prepare response
        result = {
            "elements": {id: element.to_dict() for id, element in element_map.items()},
            "root_elements": root_element_ids,
            "element_count": len(all_elements),
            "element_types": {
                "text": len(text_elements),
                "container": len(container_elements),
                "button": len(button_elements)
            }
        }
        
        return result
    
    def find_element_by_text(self, text: str, exact_match: bool = False) -> Optional[UIElement]:
        """Find an element by its text content"""
        if not self.last_elements:
            logger.warning("No elements available - process a screenshot first")
            return None
        
        for element_id, element in self.last_elements.items():
            if element.text:
                if exact_match and element.text == text:
                    return element
                elif not exact_match and text.lower() in element.text.lower():
                    return element
        
        return None
    
    def find_clickable_at_position(self, x: int, y: int) -> Optional[UIElement]:
        """Find the smallest clickable element at the given position"""
        if not self.last_elements:
            logger.warning("No elements available - process a screenshot first")
            return None
        
        # Find all elements containing this point
        candidates = []
        for element_id, element in self.last_elements.items():
            if element.contains_point(x, y):
                candidates.append(element)
        
        # No elements found
        if not candidates:
            return None
            
        # Return the smallest element (most specific)
        return min(candidates, key=lambda e: e.area)
    
    def find_element_by_type(self, element_type: str) -> List[UIElement]:
        """Find all elements of the specified type"""
        if not self.last_elements:
            logger.warning("No elements available - process a screenshot first")
            return []
        
        return [element for element in self.last_elements.values() 
                if element.element_type == element_type]

# Function to create a JSON-serializable version of UI element data
def serialize_ui_elements(ui_data: Dict[str, Any]) -> str:
    """Convert UI element data to JSON string"""
    try:
        return json.dumps(ui_data, indent=2)
    except Exception as e:
        logger.error(f"Error serializing UI data: {e}")
        return "{}"
