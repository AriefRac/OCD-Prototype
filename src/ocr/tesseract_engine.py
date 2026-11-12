import logging
from pathlib import Path
from typing import List, Union
import numpy as np

from src.models.document import BoundingBox, OCRTextBlock
from src.ocr.base import BaseOCREngine

logger = logging.getLogger(__name__)


class TesseractEngine(BaseOCREngine):
    """OCR engine using Tesseract via pytesseract."""

    def __init__(self, tesseract_cmd: Union[str, Path] = "tesseract", lang: str = "eng+ind"):
        self.lang = lang
        self.tesseract_cmd = str(tesseract_cmd)

    def extract_blocks(self, image: Union[np.ndarray, Path, str, bytes]) -> List[OCRTextBlock]:
        try:
            import pytesseract
            from PIL import Image

            if self.tesseract_cmd != "tesseract":
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd

            if isinstance(image, np.ndarray):
                # OpenCV uses BGR, PIL expects RGB
                pil_img = Image.fromarray(image[:, :, ::-1] if len(image.shape) == 3 else image)
            elif isinstance(image, (str, Path)):
                pil_img = Image.open(image)
            elif isinstance(image, bytes):
                import io
                pil_img = Image.open(io.BytesIO(image))
            else:
                raise TypeError(f"Unsupported image type: {type(image)}")

            data = pytesseract.image_to_data(pil_img, lang=self.lang, output_type=pytesseract.Output.DICT)

            blocks: List[OCRTextBlock] = []
            n_boxes = len(data["text"])

            # Group words by line (block_num, par_num, line_num)
            lines_map = {}
            for i in range(n_boxes):
                text = data["text"][i].strip()
                conf = float(data["conf"][i])
                if not text or conf < 0:
                    continue

                line_key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
                x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]

                if line_key not in lines_map:
                    lines_map[line_key] = {
                        "words": [text],
                        "x1": x,
                        "y1": y,
                        "x2": x + w,
                        "y2": y + h,
                        "confidences": [conf / 100.0],
                    }
                else:
                    entry = lines_map[line_key]
                    entry["words"].append(text)
                    entry["x1"] = min(entry["x1"], x)
                    entry["y1"] = min(entry["y1"], y)
                    entry["x2"] = max(entry["x2"], x + w)
                    entry["y2"] = max(entry["y2"], y + h)
                    entry["confidences"].append(conf / 100.0)

            for entry in lines_map.values():
                combined_text = " ".join(entry["words"])
                avg_conf = sum(entry["confidences"]) / len(entry["confidences"])
                bbox = BoundingBox(entry["x1"], entry["y1"], entry["x2"], entry["y2"])
                blocks.append(OCRTextBlock(text=combined_text, bbox=bbox, confidence=avg_conf))

            return blocks

        except ImportError:
            logger.error("pytesseract is not installed. Please install pytesseract.")
            raise
        except Exception as e:
            logger.error("Tesseract extraction failed: %s", e)
            raise

