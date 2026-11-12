import logging
from pathlib import Path
from typing import List, Union
import numpy as np

from src.models.document import BoundingBox, OCRTextBlock
from src.ocr.base import BaseOCREngine

logger = logging.getLogger(__name__)


class RapidOCREngine(BaseOCREngine):
    """OCR engine using RapidOCR (ONNX runtime port of PaddleOCR, highly stable & CPU-optimized)."""

    def __init__(self):
        self._ocr = None

    def _get_ocr(self):
        if self._ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
            except ImportError:
                logger.error("rapidocr_onnxruntime is not installed. Run: pip install rapidocr_onnxruntime onnxruntime")
                raise
        return self._ocr

    def extract_blocks(self, image: Union[np.ndarray, Path, str, bytes]) -> List[OCRTextBlock]:
        ocr = self._get_ocr()

        img_input = image
        if isinstance(image, Path):
            img_input = str(image)
        elif isinstance(image, bytes):
            import cv2
            nparr = np.frombuffer(image, np.uint8)
            img_input = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result, elapse = ocr(img_input)
        blocks: List[OCRTextBlock] = []

        if not result:
            return blocks

        for item in result:
            points = item[0]
            text = item[1]
            conf = float(item[2]) if len(item) > 2 else 1.0

            xs = [int(p[0]) for p in points]
            ys = [int(p[1]) for p in points]
            bbox = BoundingBox(min(xs), min(ys), max(xs), max(ys))
            blocks.append(OCRTextBlock(text=str(text).strip(), bbox=bbox, confidence=conf))

        return blocks

