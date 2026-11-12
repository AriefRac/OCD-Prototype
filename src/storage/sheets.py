from datetime import datetime
import logging
from pathlib import Path
from typing import List, Optional

from src.models.document import ProductionDocument

logger = logging.getLogger(__name__)

COLUMNS: List[str] = [
    "no_dokumen",
    "id_kain",
    "lot_kain_mentah",
    "id_kain_jadi",
    "langganan",
    "warna",
    "panjang",
    "waktu_ekspor",
]


class GoogleSheetsExporter:
    """Exports validated document records to Google Sheets via gspread or Apps Script Webhook."""

    def __init__(
        self,
        credentials_file: Optional[Path] = None,
        spreadsheet_id: Optional[str] = None,
        sheet_name: str = "Dokumen_Produksi",
        webhook_url: Optional[str] = None,
    ):
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.sheet_name = sheet_name
        self.webhook_url = webhook_url
        self._client = None
        self._worksheet = None
        self._is_ready = False

        self._init_connection()

    def _init_connection(self):
        """Initializes gspread client or webhook mode."""
        if self.webhook_url:
            self._is_ready = True
            logger.info("Google Sheets exporter initialized in Webhook mode: %s", self.webhook_url)
            return

        if not self.credentials_file or not self.credentials_file.exists():
            logger.warning("Google credentials file not found. Running Sheets in Dry-Run / Mock mode.")
            return

        if not self.spreadsheet_id:
            logger.warning("Google Sheets spreadsheet_id not set. Running Sheets in Dry-Run / Mock mode.")
            return

        try:
            import gspread
            from google.oauth2.service_account import Credentials

            scopes = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(str(self.credentials_file), scopes=scopes)
            self._client = gspread.authorize(creds)
            spreadsheet = self._client.open_by_key(self.spreadsheet_id)

            try:
                self._worksheet = spreadsheet.worksheet(self.sheet_name)
            except gspread.WorksheetNotFound:
                self._worksheet = spreadsheet.add_worksheet(title=self.sheet_name, rows=1000, cols=len(COLUMNS))
                self._worksheet.append_row(COLUMNS)

            # Ensure headers exist
            existing_headers = self._worksheet.row_values(1)
            if not existing_headers:
                self._worksheet.append_row(COLUMNS)

            self._is_ready = True
            logger.info("Successfully connected to Google Sheets via gspread: %s", self.sheet_name)

        except ImportError:
            logger.warning("gspread or google-auth not installed. Running Sheets in Dry-Run / Mock mode.")
        except Exception as e:
            logger.error("Failed to connect to Google Sheets: %s. Falling back to Dry-Run mode.", e)

    @property
    def is_live(self) -> bool:
        return self._is_ready

    def export_document(self, doc: ProductionDocument) -> bool:
        """Appends or updates one row of the 7 production fields directly in Google Sheets."""
        row_values = [
            f"'{doc.no_dokumen}",  # Prepend single quote to force string type in Sheets
            f"'{doc.id_kain}",
            doc.lot_kain_mentah,
            f"'{doc.id_kain_jadi}",
            doc.langganan,
            doc.warna,
            doc.panjang,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ]

        # Mode Webhook (Apps Script Web App)
        if self.webhook_url:
            import json
            import urllib.request
            try:
                payload = {
                    "sheet_name": self.sheet_name,
                    "no_dokumen": doc.no_dokumen,
                    "row": row_values,
                }
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    self.webhook_url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    logger.info("Exported document %s directly to Google Sheets via Webhook.", doc.no_dokumen)
                    return True
            except Exception as e:
                logger.error("Error sending to Google Sheets Webhook: %s", e)
                return False

        if not self._is_ready or not self._worksheet:
            logger.info("[Dry-Run Google Sheets Direct Sync] Row: %s", row_values)
            return True

        try:
            # Check if document already exists to update row instead of duplicating
            cell = None
            try:
                cell = self._worksheet.find(doc.no_dokumen)
            except Exception:
                pass

            if cell and cell.col == 1:
                row_idx = cell.row
                range_name = f"A{row_idx}:H{row_idx}"
                self._worksheet.update([row_values], range_name, value_input_option="USER_ENTERED")
                logger.info("Updated existing row %d for %s directly in Google Sheets.", row_idx, doc.no_dokumen)
            else:
                # value_input_option='USER_ENTERED' with single quote forces string preserve
                self._worksheet.append_row(row_values, value_input_option="USER_ENTERED")
                logger.info("Exported document %s directly to Google Sheets.", doc.no_dokumen)
            return True
        except Exception as e:
            logger.error("Error syncing directly to Google Sheets: %s", e)
            return False

