import logging
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.config import config
from src.models.document import DocumentStatus, ProductionDocument
from src.pipeline import ProductionOCRPipeline
from src.storage.database import DatabaseManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api_server")

app = FastAPI(
    title="OCR Kartu Proses Produksi API",
    description="Local AI Server for Textile Factory Slip OCR & Google Sheets / AppSheet Sync",
    version="1.0.0",
)

# Enable CORS for web clients / AppSheet webhooks
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline = ProductionOCRPipeline()
db = DatabaseManager(config.database_path)


class SyncRequest(BaseModel):
    no_dokumen: str
    id_kain: Optional[str] = ""
    lot_kain_mentah: Optional[str] = ""
    id_kain_jadi: Optional[str] = ""
    langganan: Optional[str] = ""
    warna: Optional[str] = ""
    panjang: Optional[str] = ""


@app.get("/")
def index():
    return {
        "status": "online",
        "service": "AI OCR Production Server",
        "engine": config.ocr_engine,
        "database": config.database_path,
        "spreadsheet_id": config.google_sheets_spreadsheet_id,
        "sheets_live": pipeline.sheets.is_live,
    }


@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "ocr_engine": config.ocr_engine,
        "database_connected": True,
        "sheets_connected": pipeline.sheets.is_live,
    }


@app.post("/api/scan")
async def scan_document(
    file: UploadFile = File(...),
    auto_save: bool = Query(False, description="Auto save draft to SQLite"),
    auto_sync_sheets: bool = Query(False, description="Directly sync to Google Sheets"),
):
    """Scan an image file of a production card and extract 7 fields."""
    try:
        contents = await file.read()
        result = pipeline.process_image(contents)

        doc_dict = result.document.to_dict()
        confidences = {k: v.confidence for k, v in result.fields.items()}

        saved_id = None
        sheets_synced = False

        if auto_save:
            saved_id = pipeline.save_pending_draft(result, operator_notes="Uploaded via REST API")

        if auto_sync_sheets and result.document.no_dokumen:
            sheets_synced = pipeline.confirm_and_export(result.document.no_dokumen, operator_id="api_client")

        return {
            "status": "success",
            "filename": file.filename,
            "fields": doc_dict,
            "confidences": confidences,
            "warnings": result.warnings,
            "needs_review": result.document.needs_review,
            "saved_draft_id": saved_id,
            "sheets_synced": sheets_synced,
        }
    except Exception as e:
        logger.exception("Error processing image via API: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/sync-sheets")
def sync_to_sheets(payload: SyncRequest):
    """Directly insert or update a document in Google Sheets and database."""
    doc = ProductionDocument(
        no_dokumen=payload.no_dokumen,
        id_kain=payload.id_kain or "",
        lot_kain_mentah=payload.lot_kain_mentah or "",
        id_kain_jadi=payload.id_kain_jadi or "",
        langganan=payload.langganan or "",
        warna=payload.warna or "",
        panjang=payload.panjang or "",
        status=DocumentStatus.CONFIRMED,
    )
    db.upsert_document(doc)
    sheets_success = pipeline.sheets.update_or_append_document(doc)
    return {
        "status": "success",
        "no_dokumen": payload.no_dokumen,
        "sheets_synced": sheets_success,
    }


@app.get("/api/documents")
def get_documents(limit: int = 50):
    """Retrieve list of scanned documents from local SQLite database."""
    return {"documents": db.list_documents(limit=limit)}

