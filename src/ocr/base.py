from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Union

from src.models.document import OCRTextBlock


class BaseOCREngine(ABC):
    """Abstract interface for all OCR engines (PaddleOCR, Tesseract, Mock)."""

    @abstractmethod
    def extract_blocks(self, image: Union[Any, Path, str, bytes]) -> List[OCRTextBlock]:
        """Detects and recognizes text in the image, returning list of OCRTextBlock."""
        pass


