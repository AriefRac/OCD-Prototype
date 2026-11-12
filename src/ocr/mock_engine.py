from pathlib import Path
from typing import Any, List, Optional, Union

from src.models.document import BoundingBox, OCRTextBlock
from src.ocr.base import BaseOCREngine


class MockOCREngine(BaseOCREngine):
    """Simulates OCR text detection for development, unit testing, and POC setup before real samples exist."""

    def __init__(self, custom_blocks: Optional[List[OCRTextBlock]] = None):
        self.custom_blocks = custom_blocks

    def extract_blocks(self, image: Union[Any, Path, str, bytes]) -> List[OCRTextBlock]:
        if self.custom_blocks:
            return self.custom_blocks

        # Default synthetic document blocks mimicking README.md sample
        return [
            # Header
            OCRTextBlock("SURAT PERINTAH PRODUKSI", BoundingBox(150, 40, 500, 70), 0.99),
            # Row 1: No Dokumen
            OCRTextBlock("NO. DOKUMEN:", BoundingBox(50, 100, 200, 125), 0.98),
            OCRTextBlock("KP26101851", BoundingBox(220, 100, 380, 125), 0.97),
            # Row 2: Langganan
            OCRTextBlock("LANGGANAN:", BoundingBox(50, 140, 180, 165), 0.96),
            OCRTextBlock("PT AYUNAN BULAN INTERNATIONAL", BoundingBox(220, 140, 580, 165), 0.95),
            # Row 3: ID Kain
            OCRTextBlock("ID KAIN:", BoundingBox(50, 180, 150, 205), 0.97),
            OCRTextBlock("1214", BoundingBox(220, 180, 300, 205), 0.99),
            # Row 4: Lot Kain Mentah
            OCRTextBlock("LOT KAIN MENTAH:", BoundingBox(50, 220, 210, 245), 0.95),
            OCRTextBlock("PP22", BoundingBox(220, 220, 310, 245), 0.96),
            # Row 5: ID Kain Jadi
            OCRTextBlock("ID KAIN JADI:", BoundingBox(50, 260, 190, 285), 0.97),
            OCRTextBlock("1214/61WRCRSF", BoundingBox(220, 260, 420, 285), 0.94),
            # Row 6: Warna
            OCRTextBlock("WARNA:", BoundingBox(50, 300, 150, 325), 0.98),
            OCRTextBlock("43 OLIVE BROWN (BR512833)", BoundingBox(220, 300, 560, 325), 0.96),
            # Row 7: Panjang
            OCRTextBlock("PANJANG:", BoundingBox(50, 340, 160, 365), 0.98),
            OCRTextBlock("3,029.00 yards", BoundingBox(220, 340, 400, 365), 0.97),
        ]

