from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Tuple


class DocumentStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPORTED = "EXPORTED"


@dataclass
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2.0

    def is_to_right_of(self, other: "BoundingBox", y_tolerance: float = 20.0) -> bool:
        """Checks if this box is horizontally to the right of `other` on roughly the same line."""
        horizontal_ok = self.x1 >= (other.x2 - 5)
        vertical_overlap = abs(self.center_y - other.center_y) <= max(y_tolerance, other.height * 0.8)
        return horizontal_ok and vertical_overlap

    def is_below(self, other: "BoundingBox", x_tolerance: float = 50.0) -> bool:
        """Checks if this box is directly below `other` (e.g. table header/cell structure)."""
        vertical_ok = self.y1 >= (other.y2 - 5)
        horizontal_aligned = abs(self.center_x - other.center_x) <= max(x_tolerance, other.width * 0.7)
        return vertical_ok and horizontal_aligned

    def horizontal_distance(self, other: "BoundingBox") -> float:
        """Distance between the right edge of other and left edge of self."""
        return max(0.0, float(self.x1 - other.x2))

    def vertical_distance(self, other: "BoundingBox") -> float:
        """Distance between the bottom edge of other and top edge of self."""
        return max(0.0, float(self.y1 - other.y2))


@dataclass
class OCRTextBlock:
    text: str
    bbox: BoundingBox
    confidence: float = 1.0


@dataclass
class ExtractedField:
    name: str
    value: str
    raw_text: str = ""
    confidence: float = 1.0
    is_ambiguous: bool = False
    warnings: List[str] = field(default_factory=list)


@dataclass
class ProductionDocument:
    """Represents the 7 extracted fields defined in README.md."""
    no_dokumen: str = ""
    id_kain: str = ""
    lot_kain_mentah: str = ""
    id_kain_jadi: str = ""
    langganan: str = ""
    warna: str = ""
    panjang: str = ""

    parsed_panjang_numeric: Optional[float] = None
    parsed_panjang_unit: Optional[str] = None

    def __post_init__(self):
        # Always enforce string types to prevent spreadsheet auto-format corruption
        self.no_dokumen = str(self.no_dokumen).strip()
        self.id_kain = str(self.id_kain).strip()
        self.lot_kain_mentah = str(self.lot_kain_mentah).strip()
        self.id_kain_jadi = str(self.id_kain_jadi).strip()
        self.langganan = str(self.langganan).strip()
        self.warna = str(self.warna).strip()
        self.panjang = str(self.panjang).strip()

        if self.panjang and self.parsed_panjang_numeric is None:
            self._parse_panjang()

    def _parse_panjang(self):
        """Parse raw panjang string like '3,029.00 yards' or '2500 m'."""
        pattern = r"([0-9,]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)?"
        match = re.search(pattern, self.panjang)
        if match:
            num_str, unit = match.groups()
            cleaned_num = num_str.replace(",", "")
            try:
                self.parsed_panjang_numeric = float(cleaned_num)
            except ValueError:
                self.parsed_panjang_numeric = None
            self.parsed_panjang_unit = unit.lower() if unit else None

    def to_dict(self, null_for_empty: bool = False) -> Dict[str, Optional[str]]:
        """Returns the exact 7 columns for spreadsheet export or JSON contract."""
        data = {
            "no_dokumen": self.no_dokumen,
            "id_kain": self.id_kain,
            "lot_kain_mentah": self.lot_kain_mentah,
            "id_kain_jadi": self.id_kain_jadi,
            "langganan": self.langganan,
            "warna": self.warna,
            "panjang": self.panjang,
        }
        if null_for_empty:
            return {k: (v if v else None) for k, v in data.items()}
        return data

    def validate_completeness(self) -> List[str]:
        """Returns list of missing or empty required fields."""
        missing = []
        for key, val in self.to_dict().items():
            if not val:
                missing.append(key)
        return missing


@dataclass
class ProcessingResult:
    success: bool
    document: ProductionDocument
    fields: Dict[str, ExtractedField] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    is_duplicate: bool = False
    raw_ocr_blocks: List[OCRTextBlock] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        """Determines if operator review is recommended per README spec."""
        return len(self.warnings) > 0 or not self.success or self.is_duplicate

    def to_contract_dict(self, source_file: str = "") -> Dict[str, Any]:
        """Returns JSON schema matching README Section 8 output contract."""
        return {
            "source_file": source_file,
            "fields": self.document.to_dict(null_for_empty=True),
            "needs_review": self.needs_review,
            "warnings": self.warnings,
        }

