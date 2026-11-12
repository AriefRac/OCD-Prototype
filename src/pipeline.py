import logging
from pathlib import Path
from typing import Any, Optional, Union

from src.config import config
from src.extractor.pattern_extractor import DocumentExtractor
from src.models.document import DocumentStatus, ProcessingResult, ProductionDocument
from src.ocr.base import BaseOCREngine
from src.ocr.factory import get_ocr_engine
from src.preprocessing.image_processor import ImageProcessor
from src.storage.database import DatabaseManager
from src.storage.sheets import GoogleSheetsExporter

logger = logging.getLogger(__name__)


class ProductionOCRPipeline:
    """End-to-end pipeline: Preprocess -> OCR -> Extraction -> Validation & Deduplication."""

    def __init__(
        self,
        ocr_engine: Optional[BaseOCREngine] = None,
        db_manager: Optional[DatabaseManager] = None,
        sheets_exporter: Optional[GoogleSheetsExporter] = None,
    ):
        self.preprocessor = ImageProcessor()
        self.ocr_engine = ocr_engine or get_ocr_engine(config.ocr_engine)
        self.extractor = DocumentExtractor()
        self.db = db_manager or DatabaseManager(config.database_path)
        self.sheets = sheets_exporter or GoogleSheetsExporter(
            credentials_file=config.google_sheets_credentials_file,
            spreadsheet_id=config.google_sheets_spreadsheet_id,
            sheet_name=config.google_sheets_sheet_name,
            webhook_url=config.google_sheets_webhook_url,
        )

    def process_image(
        self,
        image_input: Union[str, Path, bytes, Any],
        skip_preprocessing: bool = False,
    ) -> ProcessingResult:
        """Runs image through the full pipeline."""
        # Step 1: Preprocessing
        if not skip_preprocessing and not isinstance(self.ocr_engine, type(get_ocr_engine("mock"))):
            preprocessed_img = self.preprocessor.process(image_input)
        else:
            preprocessed_img = image_input

        # Step 2: OCR Detection & Recognition
        blocks = self.ocr_engine.extract_blocks(preprocessed_img)

        # Step 3: Information Extraction
        doc, fields, warnings = self.extractor.extract(blocks)

        # Step 4: Duplicate Check in Database
        is_duplicate = False
        if doc.no_dokumen:
            is_duplicate = self.db.is_duplicate(doc.no_dokumen)
            if is_duplicate:
                warnings.append(f"PERINGATAN: Dokumen '{doc.no_dokumen}' sudah pernah tersimpan sebelumnya!")

        success = bool(doc.no_dokumen) and not is_duplicate

        return ProcessingResult(
            success=success,
            document=doc,
            fields=fields,
            warnings=warnings,
            is_duplicate=is_duplicate,
            raw_ocr_blocks=blocks,
        )

    def save_pending_draft(
        self,
        result: ProcessingResult,
        operator_notes: str = "",
        operator_id: Optional[str] = None,
    ) -> int:
        """Saves extracted data to SQLite database with status PENDING_REVIEW."""
        raw_data = {
            "blocks": [
                {
                    "text": b.text,
                    "confidence": b.confidence,
                    "bbox": [b.bbox.x1, b.bbox.y1, b.bbox.x2, b.bbox.y2],
                }
                for b in result.raw_ocr_blocks
            ]
        }
        return self.db.save_draft(
            doc=result.document,
            raw_ocr_data=raw_data,
            operator_notes=operator_notes,
            operator_id=operator_id,
        )

    def confirm_and_export(
        self,
        no_dokumen: str,
        operator_id: Optional[str] = None,
    ) -> bool:
        """Finalizes an approved document: marks as APPROVED and exports to Google Sheets."""
        doc_record = self.db.get_document(no_dokumen)
        if not doc_record:
            logger.error("Document %s not found in database.", no_dokumen)
            return False

        doc = ProductionDocument(
            no_dokumen=doc_record["no_dokumen"],
            id_kain=doc_record["id_kain"] or "",
            lot_kain_mentah=doc_record["lot_kain_mentah"] or "",
            id_kain_jadi=doc_record["id_kain_jadi"] or "",
            langganan=doc_record["langganan"] or "",
            warna=doc_record["warna"] or "",
            panjang=doc_record["panjang"] or "",
        )

        # Export to Google Sheets
        sheets_success = self.sheets.export_document(doc)

        if sheets_success:
            self.db.update_status(
                no_dokumen=no_dokumen,
                new_status=DocumentStatus.EXPORTED,
                operator_id=operator_id,
                notes="Successfully synced to Google Sheets",
            )
        else:
            self.db.update_status(
                no_dokumen=no_dokumen,
                new_status=DocumentStatus.APPROVED,
                operator_id=operator_id,
                notes="Approved by operator but Sheets export failed/mocked",
            )

        return sheets_success

