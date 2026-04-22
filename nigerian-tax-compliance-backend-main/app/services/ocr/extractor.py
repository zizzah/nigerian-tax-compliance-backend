"""
OCR Text Extraction using Tesseract
Location: app/services/ocr/extractor.py

Extracts text from preprocessed images
"""
import pytesseract
from PIL import Image
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class OCRExtractor:
    """
    Extract text from images using Tesseract OCR
    
    Configured for Nigerian business documents (English)
    """
    
    def __init__(self, tesseract_cmd: Optional[str] = None):
        """
        Initialize OCR extractor
        
        Args:
            tesseract_cmd: Optional path to tesseract executable
                          (needed on Windows)
        """
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        
        # Configuration optimized for receipts/invoices
        # OEM 3 = Default (LSTM only)
        # PSM 6 = Assume uniform block of text
        self.config = r'--oem 3 --psm 6'
    
    def extract_text(self, image: np.ndarray) -> str:
        """
        Extract raw text from preprocessed image
        
        Args:
            image: Preprocessed image as numpy array
            
        Returns:
            Extracted text as string
        """
        try:
            logger.info("Starting OCR text extraction...")
            
            # Convert numpy array to PIL Image if needed
            if isinstance(image, np.ndarray):
                pil_image = Image.fromarray(image)
            else:
                pil_image = image
            
            # Extract text
            text = pytesseract.image_to_string(
                pil_image,
                config=self.config,
                lang='eng'  # English for Nigerian documents
            )
            
            # Clean up text
            cleaned_text = self._clean_text(text)
            
            logger.info(f"OCR extracted {len(cleaned_text)} characters")
            logger.debug(f"Sample text: {cleaned_text[:200]}")
            
            return cleaned_text
            
        except Exception as e:
            logger.error(f"OCR extraction failed: {e}")
            raise
    
    def extract_data(self, image: np.ndarray) -> Dict:
        """
        Extract structured data with bounding boxes and confidence scores
        
        Useful for debugging and understanding OCR performance
        
        Args:
            image: Preprocessed image
            
        Returns:
            Dictionary with detailed OCR data
        """
        try:
            if isinstance(image, np.ndarray):
                pil_image = Image.fromarray(image)
            else:
                pil_image = image
            
            # Get detailed data
            data = pytesseract.image_to_data(
                pil_image,
                output_type=pytesseract.Output.DICT,
                config=self.config,
                lang='eng'
            )
            
            return data
            
        except Exception as e:
            logger.error(f"Data extraction failed: {e}")
            raise
    
    def get_confidence_score(self, image: np.ndarray) -> float:
        """
        Calculate average confidence score for OCR
        
        Args:
            image: Preprocessed image
            
        Returns:
            Confidence score from 0.0 to 1.0
        """
        try:
            data = self.extract_data(image)
            
            # Filter out invalid confidence scores (-1)
            confidences = [c for c in data['conf'] if c != -1]
            
            if not confidences:
                logger.warning("No valid confidence scores found")
                return 0.0
            
            # Calculate average
            avg_confidence = sum(confidences) / len(confidences)
            
            # Convert to 0-1 scale
            normalized = round(avg_confidence / 100, 2)
            
            logger.info(f"OCR confidence: {normalized:.2%}")
            
            return normalized
            
        except Exception as e:
            logger.error(f"Confidence calculation failed: {e}")
            return 0.0
    
    def extract_with_confidence(self, image: np.ndarray) -> tuple[str, float]:
        """
        Extract text and calculate confidence in one call
        
        Args:
            image: Preprocessed image
            
        Returns:
            Tuple of (extracted_text, confidence_score)
        """
        text = self.extract_text(image)
        confidence = self.get_confidence_score(image)
        
        return text, confidence
    
    def _clean_text(self, text: str) -> str:
        """
        Clean extracted text
        
        - Remove extra whitespace
        - Remove empty lines
        - Normalize line breaks
        
        Args:
            text: Raw OCR text
            
        Returns:
            Cleaned text
        """
        # Split into lines
        lines = text.split('\n')
        
        # Clean each line
        cleaned_lines = []
        for line in lines:
            # Strip whitespace
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Remove multiple spaces
            line = ' '.join(line.split())
            
            cleaned_lines.append(line)
        
        # Join back
        cleaned_text = '\n'.join(cleaned_lines)
        
        return cleaned_text
    
    def extract_numbers(self, text: str) -> List[str]:
        """
        Extract all numbers from text (useful for finding amounts)
        
        Args:
            text: Input text
            
        Returns:
            List of numeric strings found
        """
        import re
        
        # Pattern for numbers with optional commas and decimals
        pattern = r'\d{1,3}(?:,\d{3})*(?:\.\d{2})?'
        
        numbers = re.findall(pattern, text)
        
        return numbers
    
    def extract_dates(self, text: str) -> List[str]:
        """
        Extract potential dates from text
        
        Args:
            text: Input text
            
        Returns:
            List of potential date strings
        """
        import re
        
        # Common date patterns
        patterns = [
            r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}',  # DD/MM/YYYY or DD-MM-YYYY
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}',    # YYYY/MM/DD or YYYY-MM-DD
            r'\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}',  # DD Month YYYY
        ]
        
        dates = []
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        
        return dates