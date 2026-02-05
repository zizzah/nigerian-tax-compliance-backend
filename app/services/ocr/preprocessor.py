"""
Image Preprocessing for OCR
Location: app/services/ocr/preprocessor.py

Enhances image quality before text extraction for better OCR results
"""
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Preprocess images for optimal OCR results
    
    Techniques applied:
    - Grayscale conversion
    - Noise reduction (denoising)
    - Contrast enhancement (CLAHE)
    - Deskewing (straighten rotated images)
    - Binarization (adaptive thresholding)
    - Border removal
    """
    
    def __init__(self, debug_mode: bool = False):
        """
        Initialize preprocessor
        
        Args:
            debug_mode: If True, save intermediate images for debugging
        """
        self.debug_mode = debug_mode
    
    def preprocess(self, image_path: str, output_dir: Optional[str] = None) -> np.ndarray:
        """
        Main preprocessing pipeline
        
        Args:
            image_path: Path to input image file
            output_dir: Optional directory to save debug images
            
        Returns:
            Preprocessed image as numpy array
        """
        try:
            # Load image
            img = cv2.imread(image_path)
            
            if img is None:
                raise ValueError(f"Could not load image: {image_path}")
            
            logger.info(f"Preprocessing image: {Path(image_path).name}")
            logger.info(f"Original size: {img.shape[1]}x{img.shape[0]}")
            
            # Step 1: Convert to grayscale
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if self.debug_mode and output_dir:
                self._save_debug(gray, output_dir, "01_grayscale.jpg")
            
            # Step 2: Denoise
            denoised = cv2.fastNlMeansDenoising(gray, h=10)
            if self.debug_mode and output_dir:
                self._save_debug(denoised, output_dir, "02_denoised.jpg")
            
            # Step 3: Enhance contrast
            contrast_enhanced = self._enhance_contrast(denoised)
            if self.debug_mode and output_dir:
                self._save_debug(contrast_enhanced, output_dir, "03_contrast.jpg")
            
            # Step 4: Adaptive thresholding (binarization)
            binary = cv2.adaptiveThreshold(
                contrast_enhanced,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,  # Block size
                2    # C constant
            )
            if self.debug_mode and output_dir:
                self._save_debug(binary, output_dir, "04_binary.jpg")
            
            # Step 5: Deskew (straighten image)
            deskewed = self._deskew(binary)
            if self.debug_mode and output_dir:
                self._save_debug(deskewed, output_dir, "05_deskewed.jpg")
            
            # Step 6: Remove borders
            cropped = self._remove_borders(deskewed)
            if self.debug_mode and output_dir:
                self._save_debug(cropped, output_dir, "06_final.jpg")
            
            logger.info(f"Preprocessing complete. Final size: {cropped.shape[1]}x{cropped.shape[0]}")
            
            return cropped
            
        except Exception as e:
            logger.error(f"Preprocessing failed: {e}")
            raise
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        Enhance image contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
        
        Args:
            image: Input grayscale image
            
        Returns:
            Contrast-enhanced image
        """
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(image)
    
    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """
        Straighten skewed/rotated image
        
        Uses minimum area rectangle to detect rotation angle
        
        Args:
            image: Input binary image
            
        Returns:
            Deskewed image
        """
        try:
            # Find all non-zero points (text)
            coords = np.column_stack(np.where(image > 0))
            
            if len(coords) == 0:
                logger.warning("No text detected for deskewing")
                return image
            
            # Get minimum area rectangle
            angle = cv2.minAreaRect(coords)[-1]
            
            # Normalize angle
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            
            # Only deskew if angle is significant (> 0.5 degrees)
            if abs(angle) < 0.5:
                return image
            
            # Rotate image
            (h, w) = image.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(
                image, M, (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE
            )
            
            logger.info(f"Deskewed image by {angle:.2f} degrees")
            
            return rotated
            
        except Exception as e:
            logger.error(f"Deskewing failed: {e}")
            return image
    
    def _remove_borders(self, image: np.ndarray) -> np.ndarray:
        """
        Remove white borders around image
        
        Args:
            image: Input binary image
            
        Returns:
            Cropped image without borders
        """
        try:
            # Find all non-zero points
            coords = cv2.findNonZero(cv2.bitwise_not(image))
            
            if coords is None:
                return image
            
            # Get bounding box
            x, y, w, h = cv2.boundingRect(coords)
            
            # Add small margin (2% of width/height)
            margin_x = int(w * 0.02)
            margin_y = int(h * 0.02)
            
            x = max(0, x - margin_x)
            y = max(0, y - margin_y)
            w = min(image.shape[1] - x, w + 2 * margin_x)
            h = min(image.shape[0] - y, h + 2 * margin_y)
            
            return image[y:y+h, x:x+w]
            
        except Exception as e:
            logger.error(f"Border removal failed: {e}")
            return image
    
    def _save_debug(self, image: np.ndarray, output_dir: str, filename: str):
        """Save debug image"""
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            output_path = Path(output_dir) / filename
            cv2.imwrite(str(output_path), image)
        except Exception as e:
            logger.error(f"Failed to save debug image: {e}")
    
    def resize_for_display(self, image: np.ndarray, max_width: int = 800) -> np.ndarray:
        """
        Resize image for display/preview while maintaining aspect ratio
        
        Args:
            image: Input image
            max_width: Maximum width in pixels
            
        Returns:
            Resized image
        """
        height, width = image.shape[:2]
        
        if width <= max_width:
            return image
        
        ratio = max_width / width
        new_height = int(height * ratio)
        
        resized = cv2.resize(image, (max_width, new_height), interpolation=cv2.INTER_AREA)
        
        return resized