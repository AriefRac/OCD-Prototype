import logging
from pathlib import Path
from typing import List, Union
import numpy as np

from src.models.document import BoundingBox, OCRTextBlock
from src.ocr.base import BaseOCREngine
from src.ocr.rapidocr_engine import RapidOCREngine

logger = logging.getLogger(__name__)


class PaddleOCREngine(BaseOCREngine):
    """OCR engine using RapidOCR / PaddleOCR (high accuracy, rotation invariance)."""

    def __init__(self, use_angle_cls: bool = True, lang: str = "en"):
        self.use_angle_cls = use_angle_cls
        self.lang = lang
        self._rapid_engine = None
        self._paddle_ocr = None

    def _get_engine(self):
        # Prefer RapidOCR on Windows CPU to prevent PaddlePaddle 3.x oneDNN crash
        try:
            if self._rapid_engine is None:
                self._rapid_engine = RapidOCREngine()
            return ("rapid", self._rapid_engine)
        except Exception:
            pass

        if self._paddle_ocr is None:
            try:
                from paddleocr import PaddleOCR
                self._paddle_ocr = PaddleOCR(use_angle_cls=self.use_angle_cls, lang=self.lang)
            except ImportError:
                logger.error("Neither rapidocr_onnxruntime nor paddleocr is available.")
                raise
        return ("paddle", self._paddle_ocr)

    def extract_blocks(self, image: Union[np.ndarray, Path, str, bytes]) -> List[OCRTextBlock]:
        engine_type, engine = self._get_engine()
        if engine_type == "rapid":
            return engine.extract_blocks(image)

        img_input = image
        if isinstance(image, (Path, str)):
            img_input = str(image)
        elif isinstance(image, bytes):
            import cv2
            nparr = np.frombuffer(image, np.uint8)
            img_input = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        result = engine.ocr(img_input, cls=self.use_angle_cls)
        blocks: List[OCRTextBlock] = []

        if not result or not result[0]:
            return blocks

        for line in result[0]:
            points, (text, conf) = line
            xs = [int(p[0]) for p in points]
            ys = [int(p[1]) for p in points]
            bbox = BoundingBox(min(xs), min(ys), max(xs), max(ys))
            blocks.append(OCRTextBlock(text=text.strip(), bbox=bbox, confidence=float(conf)))

        return blocks
