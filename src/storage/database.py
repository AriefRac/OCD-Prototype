from contextlib import contextmanager
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.models.document import DocumentStatus, ProductionDocument


class DatabaseManager:
    """Manages SQLite operations for document persistence, deduplication, and audit trails."""

    def __init__(self, db_path: Union[str, Path]):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Documents table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    no_dokumen TEXT UNIQUE NOT NULL,
                    id_kain TEXT,
                    lot_kain_mentah TEXT,
                    id_kain_jadi TEXT,
                    langganan TEXT,
                    warna TEXT,
                    panjang TEXT,
                    panjang_numeric REAL,
                    panjang_unit TEXT,
                    status TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
                    raw_ocr_json TEXT,
                    operator_notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index for fast no_dokumen lookup
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_documents_no_dokumen 
                ON documents (no_dokumen)
            """)

            # Audit logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER,
                    no_dokumen TEXT,
                    action TEXT NOT NULL,
                    operator_id TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(document_id) REFERENCES documents(id)
                )
            """)
            conn.commit()

    def is_duplicate(self, no_dokumen: str) -> bool:
        """Check if a document number is already registered."""
        if not no_dokumen:
            return False
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM documents WHERE no_dokumen = ? LIMIT 1", (no_dokumen.strip(),))
            return cursor.fetchone() is not None

    def get_document(self, no_dokumen: str) -> Optional[Dict[str, Any]]:
        """Retrieve document record by no_dokumen."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM documents WHERE no_dokumen = ?", (no_dokumen.strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_draft(
        self,
        doc: ProductionDocument,
        raw_ocr_data: Optional[Dict[str, Any]] = None,
        operator_notes: str = "",
        operator_id: Optional[str] = None,
        refresh: bool = False,
    ) -> int:
        """Save newly extracted document as PENDING_REVIEW draft."""
        now = datetime.now(timezone.utc).isoformat()
        raw_json = json.dumps(raw_ocr_data) if raw_ocr_data else None

        on_conflict = ""
        if refresh:
            columns = [key for key in doc.to_dict() if key != "no_dokumen"]
            columns += ["panjang_numeric", "panjang_unit", "status", "raw_ocr_json", "operator_notes", "updated_at"]
            on_conflict = " ON CONFLICT(no_dokumen) DO UPDATE SET " + ", ".join(
                f"{key}=excluded.{key}" for key in columns
            )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO documents (
                    no_dokumen, id_kain, lot_kain_mentah, id_kain_jadi,
                    langganan, warna, panjang, panjang_numeric, panjang_unit,
                    status, raw_ocr_json, operator_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """ + on_conflict + " RETURNING id",
                (
                    doc.no_dokumen,
                    doc.id_kain,
                    doc.lot_kain_mentah,
                    doc.id_kain_jadi,
                    doc.langganan,
                    doc.warna,
                    doc.panjang,
                    doc.parsed_panjang_numeric,
                    doc.parsed_panjang_unit,
                    DocumentStatus.PENDING_REVIEW.value,
                    raw_json,
                    operator_notes,
                    now,
                    now,
                ),
            )
            doc_id = cursor.fetchone()[0]

            cursor.execute(
                """
                INSERT INTO audit_logs (document_id, no_dokumen, action, operator_id, details)
                VALUES (?, ?, ?, ?, ?)
                """,
                (doc_id, doc.no_dokumen, "RESCANNED_DRAFT" if refresh else "EXTRACTED_DRAFT",
                 operator_id or "system", operator_notes or "Initial draft saved"),
            )
            conn.commit()
            return doc_id

    def update_field(
        self,
        no_dokumen: str,
        field_name: str,
        new_value: str,
        operator_id: Optional[str] = None,
    ) -> bool:
        """Update a specific field of an existing document during operator review."""
        allowed_fields = {
            "id_kain", "lot_kain_mentah", "id_kain_jadi",
            "langganan", "warna", "panjang", "operator_notes"
        }
        if field_name not in allowed_fields:
            raise ValueError(f"Field {field_name} is not editable.")

        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE documents SET {field_name} = ?, updated_at = ? WHERE no_dokumen = ?",
                (new_value.strip(), now, no_dokumen.strip()),
            )
            if cursor.rowcount == 0:
                return False

            cursor.execute(
                """
                INSERT INTO audit_logs (no_dokumen, action, operator_id, details)
                VALUES (?, ?, ?, ?)
                """,
                (
                    no_dokumen,
                    "FIELD_EDITED",
                    operator_id or "operator",
                    f"Updated {field_name} to '{new_value}'",
                ),
            )
            conn.commit()
            return True

    def update_status(
        self,
        no_dokumen: str,
        new_status: DocumentStatus,
        operator_id: Optional[str] = None,
        notes: str = "",
    ) -> bool:
        """Change document status (e.g. APPROVED, REJECTED, EXPORTED)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE no_dokumen = ?",
                (new_status.value, now, no_dokumen.strip()),
            )
            if cursor.rowcount == 0:
                return False

            cursor.execute(
                """
                INSERT INTO audit_logs (no_dokumen, action, operator_id, details)
                VALUES (?, ?, ?, ?)
                """,
                (
                    no_dokumen,
                    f"STATUS_{new_status.value}",
                    operator_id or "system",
                    notes or f"Status changed to {new_status.value}",
                ),
            )
            conn.commit()
            return True

    def list_documents(self, status: Optional[DocumentStatus] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List documents with optional status filter."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if status:
                cursor.execute(
                    "SELECT * FROM documents WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status.value, limit),
                )
            else:
                cursor.execute("SELECT * FROM documents ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

