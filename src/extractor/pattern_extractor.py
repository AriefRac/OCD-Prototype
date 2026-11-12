import re
from typing import Dict, List, Optional, Tuple
from src.models.document import (
    BoundingBox,
    ExtractedField,
    OCRTextBlock,
    ProductionDocument,
)


class FieldDefinitions:
    """Configures labels, regex patterns, and validation rules for the 7 production fields."""

    # Field aliases and label variations (sorted longer to shorter to avoid prefix collisions)
    LABELS: Dict[str, List[str]] = {
        "no_dokumen": [
            "NOMOR DOKUMEN", "DOCUMENT NO", "NO. DOKUMEN", "NO DOKUMEN",
            "NO.DOKUMEN", "DOC NO", "NO. DOK", "NO DOK",
        ],
        "id_kain": [
            "ARTIKEL KAIN", "FABRIC ID", "KODE KAIN", "ID FABRIC", "ID KAIN",
        ],
        "lot_kain_mentah": [
            "LOT KAIN MENTAH", "LOT GREIGE", "LOT MENTAH", "LOT BAHAN", "LOT KAIN", "LOT RAW",
        ],
        "id_kain_jadi": [
            "FINISHED FABRIC", "KODE KAIN JADI", "ID KAIN JADI", "KAIN JADI", "ID FINISH",
        ],
        "langganan": [
            "PELANGGAN", "LANGGANAN", "CUSTOMER", "PEMBELI", "KEPADA", "BUYER",
        ],
        "warna": [
            "CORAK / WARNA", "COLOUR", "WARNA", "COLOR",
        ],
        "panjang": [
            "JUMLAH YARDS", "QUANTITY", "PANJANG", "LENGTH", "JUMLAH", "QTY",
        ],
    }

    # Regex patterns for direct content matching or fallback
    REGEX_PATTERNS: Dict[str, re.Pattern] = {
        "no_dokumen": re.compile(r"\b(KP[0-9A-Z]{6,10}|[A-Z]{2}[0-9A-Z]{6,10})\b", re.IGNORECASE),
        "id_kain_jadi": re.compile(r"\b([0-9A-Z]{2,8}/[0-9A-Z]{3,12})\b", re.IGNORECASE),
        "panjang": re.compile(r"\b([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]+)?\s*(?:yards?|yd|m|meter)?)\b", re.IGNORECASE),
    }


class DocumentExtractor:
    """Extracts the 7 required fields from OCR text blocks using spatial heuristics and pattern matching."""

    def __init__(self):
        self.field_defs = FieldDefinitions

    @staticmethod
    def _clean_text(text: str) -> str:
        return " ".join(text.strip().split())

    def _find_inline_value(self, block_text: str, label: str) -> Optional[str]:
        """Extracts value if the label and value are inside the same OCR text block (e.g. 'ID KAIN: 1214')."""
        escaped_label = re.escape(label)
        pattern = r"(?:^|[\s\(\[\{]|\b)" + escaped_label + r"(?:[:\-=\s]+|$)"
        match = re.search(pattern, block_text, re.IGNORECASE)
        if match:
            remainder = block_text[match.end():].strip()
            remainder = re.sub(r"^[:\-=\s]+", "", remainder).strip()
            if remainder:
                return remainder
        return None

    def _check_ambiguity(self, field_name: str, value: str) -> Tuple[bool, List[str]]:
        """Identifies visually ambiguous OCR characters like O/0, I/1, S/5 in alphanumeric codes."""
        warnings = []
        is_ambiguous = False

        if field_name in ("no_dokumen", "id_kain", "lot_kain_mentah", "id_kain_jadi"):
            if "O" in value and any(c.isdigit() for c in value):
                warnings.append("Mengandung karakter 'O' kapital; periksa apakah seharusnya angka '0'.")
                is_ambiguous = True
            if "I" in value and any(c.isdigit() for c in value):
                warnings.append("Mengandung karakter 'I' kapital; periksa apakah seharusnya angka '1'.")
                is_ambiguous = True
            if "l" in value:  # lowercase L
                warnings.append("Mengandung karakter 'l' kecil; periksa apakah seharusnya angka '1' atau 'I'.")
                is_ambiguous = True
            if "S" in value and any(c.isdigit() for c in value):
                warnings.append("Mengandung karakter 'S' kapital; periksa apakah seharusnya angka '5'.")
                is_ambiguous = True

        return is_ambiguous, warnings

    def extract(self, blocks: List[OCRTextBlock]) -> Tuple[ProductionDocument, Dict[str, ExtractedField], List[str]]:
        """Processes OCR blocks and returns ProductionDocument, field details, and warnings."""
        extracted_fields: Dict[str, ExtractedField] = {}
        all_warnings: List[str] = []

        available_blocks = list(blocks)

        for field_name, label_variants in self.field_defs.LABELS.items():
            matched_value = ""
            confidence = 0.0
            matched_block = None

            # Strategy 1: Check if label exists and value is in same block
            for b in available_blocks:
                # Prevent id_kain from matching id_kain_jadi
                if field_name == "id_kain" and re.search(r"\b(JADI|FINISH)\b", b.text, re.IGNORECASE):
                    continue

                # If the block is exclusively a label (e.g. "LOT KAIN MENTAH:"), don't treat sub-words as values
                clean_b_text = re.sub(r"[:\-=\s]+$", "", b.text.upper()).strip()
                if clean_b_text in label_variants:
                    continue

                for label in label_variants:
                    val = self._find_inline_value(b.text, label)
                    if val:
                        matched_value = val
                        confidence = b.confidence
                        matched_block = b
                        break
                if matched_value:
                    break

            # Strategy 2: Label in one block, value in adjacent block (to the right or directly below)
            if not matched_value:
                for label_block in available_blocks:
                    lbl_text_upper = label_block.text.upper().strip()
                    clean_lbl = re.sub(r"[:\-=\s]+$", "", lbl_text_upper).strip()

                    # Prevent id_kain from matching id_kain_jadi
                    if field_name == "id_kain" and any(k in clean_lbl for k in ["JADI", "FINISH"]):
                        continue

                    # Check if this block is essentially the label
                    is_label_block = any(clean_lbl == variant for variant in label_variants)
                    if not is_label_block:
                        continue

                    # Search candidate value blocks to the right
                    candidates_right = [
                        candidate for candidate in available_blocks
                        if candidate != label_block and candidate.bbox.is_to_right_of(label_block.bbox)
                    ]
                    if candidates_right:
                        candidates_right.sort(key=lambda c: c.bbox.horizontal_distance(label_block.bbox))
                        chosen = candidates_right[0]
                        matched_value = chosen.text.strip()
                        confidence = chosen.confidence
                        matched_block = chosen
                        break

                    # Search candidate value blocks below (table cell layout)
                    candidates_below = [
                        candidate for candidate in available_blocks
                        if candidate != label_block and candidate.bbox.is_below(label_block.bbox)
                    ]
                    if candidates_below:
                        candidates_below.sort(key=lambda c: c.bbox.vertical_distance(label_block.bbox))
                        chosen = candidates_below[0]
                        matched_value = chosen.text.strip()
                        confidence = chosen.confidence
                        matched_block = chosen
                        break

            # Strategy 3: Regex pattern fallback if still not found
            if not matched_value and field_name in self.field_defs.REGEX_PATTERNS:
                regex = self.field_defs.REGEX_PATTERNS[field_name]
                for b in available_blocks:
                    match = regex.search(b.text)
                    if match:
                        matched_value = match.group(1).strip()
                        confidence = b.confidence * 0.9
                        matched_block = b
                        break

            # Clean matched value
            cleaned_val = self._clean_text(matched_value)
            cleaned_val = re.sub(r"^[:\-=\s]+", "", cleaned_val).strip()
            cleaned_val = re.sub(r"[:\-=\s]+$", "", cleaned_val).strip()

            is_ambiguous, amb_warnings = self._check_ambiguity(field_name, cleaned_val)
            all_warnings.extend(amb_warnings)

            extracted_fields[field_name] = ExtractedField(
                name=field_name,
                value=cleaned_val,
                raw_text=matched_block.text if matched_block else "",
                confidence=confidence,
                is_ambiguous=is_ambiguous,
                warnings=amb_warnings,
            )

        # Assemble ProductionDocument
        doc = ProductionDocument(
            no_dokumen=extracted_fields["no_dokumen"].value,
            id_kain=extracted_fields["id_kain"].value,
            lot_kain_mentah=extracted_fields["lot_kain_mentah"].value,
            id_kain_jadi=extracted_fields["id_kain_jadi"].value,
            langganan=extracted_fields["langganan"].value,
            warna=extracted_fields["warna"].value,
            panjang=extracted_fields["panjang"].value,
        )

        missing = doc.validate_completeness()
        if missing:
            all_warnings.append(f"Field kosong/belum terdeteksi: {', '.join(missing)}")

        return doc, extracted_fields, all_warnings

