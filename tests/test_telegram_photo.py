import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from src.bot.telegram_bot import FactoryTelegramBot
from src.config import config
from src.ocr.mock_engine import MockOCREngine
from src.pipeline import ProductionOCRPipeline
from src.storage.database import DatabaseManager
from src.storage.sheets import GoogleSheetsExporter


def test_repeated_photo_reuses_ocr_and_reads_current_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "telegram_allowed_users", [])
    engine = Mock(wraps=MockOCREngine(), spec=MockOCREngine)
    pipeline = ProductionOCRPipeline(engine, DatabaseManager(tmp_path / "test.db"), GoogleSheetsExporter())
    bot = FactoryTelegramBot(pipeline)
    telegram_file = SimpleNamespace(download_as_bytearray=AsyncMock(return_value=bytearray(b"photo")))
    photo = SimpleNamespace(file_unique_id="same-photo", get_file=AsyncMock(return_value=telegram_file))
    message = SimpleNamespace(photo=[photo], message_id=42, reply_text=AsyncMock())
    update = SimpleNamespace(message=message, effective_user=SimpleNamespace(id=1), effective_chat=SimpleNamespace(id=2))
    context = SimpleNamespace(user_data={})

    async def send_twice():
        await bot.handle_photo(update, context)
        pipeline.db.update_field("KP26101851", "warna", "Koreksi operator")
        await bot.handle_photo(update, context)

    asyncio.run(send_twice())
    photo.get_file.assert_awaited_once()
    engine.extract_blocks.assert_called_once()
    assert "Hasil ini berbeda dari draf tersimpan" in message.reply_text.await_args.args[0]
    assert pipeline.db.get_document("KP26101851")["warna"] == "Koreksi operator"
