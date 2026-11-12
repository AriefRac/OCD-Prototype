import io
import logging
from pathlib import Path
from typing import Optional, Tuple, Union
import numpy as np

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Preprocesses document images to optimize OCR text recognition accuracy."""

    def __init__(self, debug_dir: Optional[Path] = None):
        self.debug_dir = debug_dir
        if self.debug_dir:
            self.debug_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_image(image_input: Union[str, Path, bytes, np.ndarray]) -> np.ndarray:
        """Loads an image into a standard BGR numpy array."""
        if isinstance(image_input, np.ndarray):
            return image_input

        try:
            import cv2
            if isinstance(image_input, (str, Path)):
                img = cv2.imread(str(image_input))
                if img is None:
                    raise ValueError(f"Could not read image file at {image_input}")
                return img
            elif isinstance(image_input, bytes):
                nparr = np.frombuffer(image_input, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is None:
                    raise ValueError("Could not decode image from bytes.")
                return img
        except ImportError:
            # Fallback using PIL
            from PIL import Image
            if isinstance(image_input, (str, Path)):
                pil_img = Image.open(image_input).convert("RGB")
            else:
                pil_img = Image.open(io.BytesIO(image_input)).convert("RGB")
            # Convert RGB to BGR for cv2 convention
            arr = np.array(pil_img)
            return arr[:, :, ::-1].copy()

        raise TypeError(f"Unsupported image input type: {type(image_input)}")

    def deskew(self, image: np.ndarray) -> np.ndarray:
        """Detects document skew angle and rotates it upright."""
        try:
            import cv2
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            # Invert colors so text is white
            thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

            # Find coordinates of all white pixels
            coords = np.column_stack(np.where(thresh > 0))
            if len(coords) < 100:
                return image

            angle = cv2.minAreaRect(coords)[-1]
            # Standardize angle to [-45, 45] range
            if angle < -45:
                angle = -(90 + angle)
            elif angle > 45:
                angle = 90 - angle

            # Only correct if angle is noticeable (> 0.5 degrees)
            if abs(angle) > 0.5:
                (h, w) = image.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                rotated = cv2.warpAffine(
                    image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
                )
                logger.debug("Deskewed image by %.2f degrees", angle)
                return rotated
        except Exception as e:
            logger.warning("Deskew failed (%s), returning original image.", e)

        return image

    def enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """Applies adaptive histogram equalization (CLAHE) to handle uneven lighting."""
        try:
            import cv2
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)
        except Exception as e:
            logger.warning("Contrast enhancement failed (%s), returning original.", e)
            return image

    def remove_noise(self, image: np.ndarray) -> np.ndarray:
        """Bilateral filter smoothens noise while keeping text edges crisp."""
        try:
            import cv2
            return cv2.bilateralFilter(image, d=9, sigmaColor=75, sigmaSpace=75)
        except Exception as e:
            logger.warning("Denoising failed (%s), returning original.", e)
            return image

    def process(self, image_input: Union[str, Path, bytes, np.ndarray]) -> np.ndarray:
        """Complete preprocessing pipeline."""
        img = self.load_image(image_input)
        img = self.deskew(img)
        img = self.enhance_contrast(img)
        img = self.remove_noise(img)
        return img

