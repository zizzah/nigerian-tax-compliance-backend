"""
Image Preprocessing for OCR
Location: app/services/ocr/preprocessor.py

Enhances image quality before text extraction for better OCR results.

PDF Support:
    Requires pdf2image (pip install pdf2image) and poppler-utils on the system.
    On Render, add to render.yaml buildCommand:
        apt-get install -y poppler-utils && pip install -r requirements.txt

Fixed:
    - Prevents 90-degree rotations that destroy text readability
    - Supports PDF input via pdf2image conversion
    - Normalises PIL image mode to RGB before cv2 conversion (handles RGBA/P/L)
"""
import cv2
import numpy as np
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Preprocess images for optimal OCR results.

    Techniques applied (in order):
        1. Grayscale conversion
        2. Noise reduction (fastNlMeansDenoising)
        3. Contrast enhancement (CLAHE)
        4. Binarisation (adaptive Gaussian thresholding)
        5. Deskewing (skew angle clamped to ±45°)
        6. Border removal
    """

    def __init__(self, debug_mode: bool = False) -> None:
        """
        Args:
            debug_mode: If True, save intermediate images to output_dir at each stage.
        """
        self.debug_mode = debug_mode

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def preprocess(self, image_path: str, output_dir: Optional[str] = None) -> np.ndarray:
        """
        Run the full preprocessing pipeline.

        Args:
            image_path: Path to an image file or PDF.
            output_dir:  Optional directory for debug images (requires debug_mode=True).

        Returns:
            Preprocessed binary image as a numpy array (H×W, uint8).

        Raises:
            ValueError: If the file cannot be loaded or is empty.
            RuntimeError: If a required dependency (e.g. pdf2image) is missing.
        """
        try:
            img = self._load_image(image_path)

            logger.info("Preprocessing image: %s", Path(image_path).name)
            logger.info("Original size: %dx%d", img.shape[1], img.shape[0])

            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if self.debug_mode and output_dir:
                self._save_debug(gray, output_dir, "01_grayscale.jpg")

            denoised = cv2.fastNlMeansDenoising(gray, h=10)
            if self.debug_mode and output_dir:
                self._save_debug(denoised, output_dir, "02_denoised.jpg")

            contrast_enhanced = self._enhance_contrast(denoised)
            if self.debug_mode and output_dir:
                self._save_debug(contrast_enhanced, output_dir, "03_contrast.jpg")

            binary = cv2.adaptiveThreshold(
                contrast_enhanced,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                11,  # block size — must be odd
                2,   # C constant subtracted from mean
            )
            if self.debug_mode and output_dir:
                self._save_debug(binary, output_dir, "04_binary.jpg")

            deskewed = self._deskew(binary)
            if self.debug_mode and output_dir:
                self._save_debug(deskewed, output_dir, "05_deskewed.jpg")

            cropped = self._remove_borders(deskewed)
            if self.debug_mode and output_dir:
                self._save_debug(cropped, output_dir, "06_final.jpg")

            logger.info(
                "Preprocessing complete. Final size: %dx%d",
                cropped.shape[1],
                cropped.shape[0],
            )
            return cropped

        except Exception as e:
            logger.error("Preprocessing failed: %s", e)
            raise

    def resize_for_display(self, image: np.ndarray, max_width: int = 800) -> np.ndarray:
        """
        Downscale image to max_width while preserving aspect ratio.

        Args:
            image:     Input image (any number of channels).
            max_width: Target maximum width in pixels.

        Returns:
            Resized image, or the original if already within bounds.
        """
        height, width = image.shape[:2]
        if width <= max_width:
            return image

        ratio = max_width / width
        new_height = int(height * ratio)
        return cv2.resize(image, (max_width, new_height), interpolation=cv2.INTER_AREA)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_image(self, image_path: str) -> np.ndarray:
        """
        Load an image from disk.

        For PDFs, converts page 1 to a raster image via pdf2image at 300 DPI.
        For all other formats, delegates to cv2.imread.

        The PIL image is explicitly converted to RGB before the numpy/cv2
        conversion so that RGBA, palette (P), or greyscale (L) PDFs do not
        produce a shape mismatch in cv2.cvtColor downstream.

        Args:
            image_path: Absolute or relative path to the file.

        Returns:
            BGR image as a numpy array (H×W×3, uint8).

        Raises:
            RuntimeError: If pdf2image is not installed.
            ValueError:   If the PDF has no pages or the image file cannot be read.
        """
        path = Path(image_path)

        if path.suffix.lower() == ".pdf":
            try:
                from pdf2image import convert_from_path
            except ImportError:
                raise RuntimeError(
                    "pdf2image is not installed. "
                    "Add 'pdf2image' to requirements.txt and 'poppler-utils' to your build command."
                )

            pages = convert_from_path(image_path, dpi=300, first_page=1, last_page=1)
            if not pages:
                raise ValueError("PDF has no pages: %s" % image_path)

            # Normalise to RGB regardless of source mode (RGBA, P, L, etc.)
            pil_img = pages[0].convert("RGB")
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            logger.info(
                "Converted PDF page 1 to image (%dx%d)", img.shape[1], img.shape[0]
            )
            return img

        img = cv2.imread(image_path)
        if img is None:
            raise ValueError("Could not load image: %s" % image_path)
        return img

    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE (Contrast Limited Adaptive Histogram Equalization).

        Args:
            image: Greyscale image.

        Returns:
            Contrast-enhanced greyscale image.
        """
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        return clahe.apply(image)

    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """
        Correct small rotational skew using the minimum-area-rectangle method.

        Skips correction when:
        - No foreground pixels are found.
        - The detected angle exceeds ±45° (indicates a misdetection, not real skew).
        - The angle is under 0.5° (negligible; rotation would introduce more artefacts
          than it removes).

        Args:
            image: Binary image (output of thresholding).

        Returns:
            Deskewed image, or the original if correction was skipped.
        """
        try:
            coords = np.column_stack(np.where(image > 0))
            if len(coords) == 0:
                logger.warning("No foreground pixels found; skipping deskew.")
                return image

            angle = cv2.minAreaRect(coords)[-1]

            # cv2.minAreaRect returns angles in [-90, 0).
            # Normalise to the range that represents true skew.
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            if abs(angle) > 45:
                logger.info(
                    "Skipping deskew: detected angle %.2f° looks like a misdetection.", angle
                )
                return image

            if abs(angle) < 0.5:
                return image

            (h, w) = image.shape[:2]
            M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
            rotated = cv2.warpAffine(
                image,
                M,
                (w, h),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )
            logger.info("Deskewed by %.2f degrees.", angle)
            return rotated

        except Exception as e:
            logger.error("Deskewing failed: %s", e)
            return image

    def _remove_borders(self, image: np.ndarray) -> np.ndarray:
        """
        Crop away white (empty) borders around document content.

        A 2% margin is preserved on each side to avoid clipping edge characters.

        Args:
            image: Binary image (white text/content on white or black background).

        Returns:
            Cropped image, or the original if no content bounding box is found.
        """
        try:
            coords = cv2.findNonZero(cv2.bitwise_not(image))
            if coords is None:
                return image

            x, y, w, h = cv2.boundingRect(coords)

            margin_x = int(w * 0.02)
            margin_y = int(h * 0.02)

            x = max(0, x - margin_x)
            y = max(0, y - margin_y)
            w = min(image.shape[1] - x, w + 2 * margin_x)
            h = min(image.shape[0] - y, h + 2 * margin_y)

            return image[y : y + h, x : x + w]

        except Exception as e:
            logger.error("Border removal failed: %s", e)
            return image

    def _save_debug(self, image: np.ndarray, output_dir: str, filename: str) -> None:
        """
        Write an intermediate image to disk for pipeline inspection.

        Failures are logged but do not interrupt the main pipeline.
        """
        try:
            out = Path(output_dir)
            out.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(out / filename), image)
        except Exception as e:
            logger.error("Failed to save debug image %s: %s", filename, e)