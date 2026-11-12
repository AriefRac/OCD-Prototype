from pathlib import Path
import tempfile
from src.models.document import DocumentStatus
from src.ocr.mock_engine import MockOCREngine
from src.pipeline import ProductionOCRPipeline
from src.storage.database import DatabaseManager
from src.storage.sheets import GoogleSheetsExporter


def test_pipeline_end_to_end():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    db = DatabaseManager(db_path)
    sheets = GoogleSheetsExporter()  # Runs in dry-run mode
    mock_ocr = MockOCREngine()
    pipeline = ProductionOCRPipeline(ocr_engine=mock_ocr, db_manager=db, sheets_exporter=sheets)

    # 1. Process image
    result = pipeline.process_image("dummy_path.jpg")
    assert result.success is True
    assert result.document.no_dokumen == "KP26101851"
    assert result.is_duplicate is False

    # 2. Save draft
    doc_id = pipeline.save_pending_draft(result, operator_notes="Test Run")
    assert doc_id > 0

    # 3. Test duplicate check on second run
    result2 = pipeline.process_image("dummy_path.jpg")
    assert result2.is_duplicate is True
    assert not result2.success

    # 4. Confirm and export
    confirmed = pipeline.confirm_and_export("KP26101851", operator_id="admin")
    assert confirmed is True

    record = db.get_document("KP26101851")
    assert record["status"] in (DocumentStatus.EXPORTED.value, DocumentStatus.APPROVED.value)

    if db_path.exists():
        db_path.unlink()

