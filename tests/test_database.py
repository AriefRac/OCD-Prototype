import pytest
from pathlib import Path
import tempfile
from src.models.document import DocumentStatus, ProductionDocument
from src.storage.database import DatabaseManager


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_path = Path(f.name)
    db = DatabaseManager(temp_path)
    yield db
    if temp_path.exists():
        temp_path.unlink()


def test_save_draft_and_duplicate_detection(temp_db):
    doc = ProductionDocument(
        no_dokumen="KP26101851",
        id_kain="1214",
        lot_kain_mentah="PP22",
        id_kain_jadi="1214/61WRCRSF",
        langganan="PT AYUNAN BULAN INTERNATIONAL",
        warna="43 OLIVE BROWN",
        panjang="3,029.00 yards",
    )

    assert not temp_db.is_duplicate("KP26101851")

    doc_id = temp_db.save_draft(doc, operator_notes="Test initial entry")
    assert doc_id > 0
    assert temp_db.is_duplicate("KP26101851")


def test_update_field(temp_db):
    doc = ProductionDocument(
        no_dokumen="KP1001",
        id_kain="9999",
        langganan="PT ABC",
    )
    temp_db.save_draft(doc)

    # Correct id_kain
    updated = temp_db.update_field("KP1001", "id_kain", "1214", operator_id="test_user")
    assert updated is True

    record = temp_db.get_document("KP1001")
    assert record["id_kain"] == "1214"


def test_update_status(temp_db):
    doc = ProductionDocument(no_dokumen="KP1002")
    temp_db.save_draft(doc)

    temp_db.update_status("KP1002", DocumentStatus.APPROVED, operator_id="admin")
    record = temp_db.get_document("KP1002")
    assert record["status"] == DocumentStatus.APPROVED.value

