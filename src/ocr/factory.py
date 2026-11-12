from typing import Optional
from src.ocr.base import BaseOCREngine
from src.ocr.mock_engine import MockOCREngine
from src.ocr.tesseract_engine import TesseractEngine
from src.ocr.paddle_engine import PaddleOCREngine
from src.ocr.rapidocr_engine import RapidOCREngine


def get_ocr_engine(engine_name: Optional[str] = "rapidocr") -> BaseOCREngine:
    """Factory to instantiate the appropriate OCR engine."""
    engine = (engine_name or "rapidocr").lower()

    if engine in ("rapidocr", "rapid"):
        return RapidOCREngine()
    elif engine in ("paddleocr", "paddle"):
        return PaddleOCREngine()
    elif engine == "tesseract":
        return TesseractEngine()
    elif engine == "mock":
        return MockOCREngine()
    else:
        raise ValueError(
            f"Unknown OCR engine '{engine}'. Supported: 'rapidocr', 'paddleocr', 'tesseract', 'mock'"
        )
