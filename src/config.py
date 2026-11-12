import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent


def load_env(env_path: Optional[Path] = None):
    """Load simple key=value pairs from .env without external dependencies."""
    if env_path is None:
        env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            # Strip inline comments and quotes
            v = v.split("#", 1)[0].strip()
            if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            os.environ.setdefault(k.strip(), v)


load_env()


@dataclass
class AppConfig:
    app_env: str = os.getenv("APP_ENV", "development")
    ocr_engine: str = os.getenv("OCR_ENGINE", "mock").lower()

    # Database
    database_path: Path = BASE_DIR / os.getenv("DATABASE_PATH", "data/production_docs.db")

    # Storage paths
    samples_dir: Path = BASE_DIR / os.getenv("SAMPLES_DIR", "data/samples")
    processed_dir: Path = BASE_DIR / os.getenv("PROCESSED_DIR", "data/processed")

    # Telegram
    telegram_bot_token: Optional[str] = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_allowed_users: List[int] = field(default_factory=lambda: [
        int(uid.strip())
        for uid in os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
        if uid.strip().isdigit()
    ])

    # Google Sheets
    google_sheets_credentials_file: Path = BASE_DIR / os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "service_account.json")
    google_sheets_spreadsheet_id: Optional[str] = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
    google_sheets_sheet_name: str = os.getenv("GOOGLE_SHEETS_SHEET_NAME", "Dokumen_Produksi")
    google_sheets_webhook_url: Optional[str] = os.getenv("GOOGLE_SHEETS_WEBHOOK_URL")
    auto_sync_sheets: bool = os.getenv("AUTO_SYNC_SHEETS", "true").lower() in ("true", "1", "yes")

    def ensure_directories(self):
        """Create necessary data directories."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.samples_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)


config = AppConfig()
config.ensure_directories()

