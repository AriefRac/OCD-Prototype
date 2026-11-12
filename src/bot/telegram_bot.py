import io
import logging
from typing import Dict
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.bot.keyboards import get_edit_fields_keyboard, get_review_keyboard
from src.config import config
from src.models.document import DocumentStatus, ProductionDocument
from src.pipeline import ProductionOCRPipeline

logger = logging.getLogger(__name__)


def format_document_summary(
    doc: ProductionDocument,
    warnings: list,
    is_duplicate: bool,
    sheets_status: str = "",
) -> str:
    """Formats 7 fields into a readable message for the Telegram operator."""
    dup_alert = "⚠️ **PERINGATAN: DOKUMEN DUPLIKAT DITEMUKAN!**\n\n" if is_duplicate else ""

    text = (
        f"{dup_alert}📄 **Hasil Scan OCR Dokumen Produksi:**\n\n"
        f"1️⃣ **No. Dokumen:** `{doc.no_dokumen or '[TIDAK TERBACA]'}`\n"
        f"2️⃣ **ID Kain:** `{doc.id_kain or '[KOSONG]'}`\n"
        f"3️⃣ **Lot Kain Mentah:** `{doc.lot_kain_mentah or '[KOSONG]'}`\n"
        f"4️⃣ **ID Kain Jadi:** `{doc.id_kain_jadi or '[KOSONG]'}`\n"
        f"5️⃣ **Langganan:** `{doc.langganan or '[KOSONG]'}`\n"
        f"6️⃣ **Warna:** `{doc.warna or '[KOSONG]'}`\n"
        f"7️⃣ **Panjang:** `{doc.panjang or '[KOSONG]'}`\n"
    )

    if sheets_status:
        text += f"\n📊 **Google Sheets:** {sheets_status}\n"

    if warnings:
        text += "\n⚠️ **Catatan / Peringatan Validasi:**\n"
        for w in warnings:
            text += f"• {w}\n"

    text += "\nTekan 'Koreksi Nilai' jika ada data yang perlu diperbaiki."
    return text


class FactoryTelegramBot:
    """Telegram Bot interface for document upload, OCR review, correction, and syncing."""

    def __init__(self, pipeline: ProductionOCRPipeline):
        self.pipeline = pipeline
        self.pending_edits: Dict[int, Dict[str, str]] = {}  # user_id -> {no_dokumen, field_name}

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Selamat datang di **Bot OCR Dokumen Produksi Pabrik**.\n\n"
            "Kirimkan foto atau scan surat perintah / dokumen produksi untuk mengekstrak 7 data utama.\n"
            "Anda dapat meninjau dan mengoreksi data sebelum disimpan ke Google Sheets.\n\n"
            "Gunakan /help untuk bantuan, /list untuk melihat dokumen terakhir."
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📖 **Panduan Penggunaan:**\n\n"
            "1. Ambil foto dokumen produksi secara jelas (usahakan tidak terpotong).\n"
            "2. Kirim foto langsung ke chat ini.\n"
            "3. Sistem akan membaca 7 field: No Dokumen, ID Kain, Lot Mentah, ID Jadi, Langganan, Warna, dan Panjang.\n"
            "4. Tekan tombol 'Koreksi Nilai' bila ada teks yang salah terbaca.\n"
            "5. Tekan 'Konfirmasi & Simpan' untuk mencatat ke database & Google Sheets."
        )

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Receives a document photo and runs the OCR pipeline."""
        user = update.effective_user
        if config.telegram_allowed_users and user.id not in config.telegram_allowed_users:
            await update.message.reply_text("⛔ Anda tidak memiliki akses untuk menggunakan bot ini.")
            return

        status_msg = await update.message.reply_text("⏳ Mengunduh foto dan menjalankan pemrosesan OCR...")

        try:
            # Download highest resolution photo
            photo = update.message.photo[-1]
            file = await photo.get_file()
            photo_bytes = await file.download_as_bytearray()

            # Process through pipeline
            result = self.pipeline.process_image(bytes(photo_bytes))

            # Save draft in SQLite
            if result.document.no_dokumen:
                self.pipeline.save_pending_draft(
                    result=result,
                    operator_notes="Uploaded via Telegram",
                    operator_id=str(user.id),
                )

            # Langsung sinkron ke Google Sheets jika AUTO_SYNC_SHEETS aktif dan bukan duplikat
            sheets_status = ""
            already_synced = False
            if config.auto_sync_sheets and result.document.no_dokumen and not result.is_duplicate:
                self.pipeline.confirm_and_export(result.document.no_dokumen, operator_id=str(user.id))
                already_synced = True
                if self.pipeline.sheets.is_live:
                    sheets_status = "✅ Berhasil dikirim langsung ke Google Sheets (baris baru ditambahkan)!"
                else:
                    sheets_status = "ℹ️ Tersimpan di database lokal (Mode simulasi: isi GOOGLE_SHEETS_SPREADSHEET_ID di .env untuk live spreadsheet)."
            elif result.is_duplicate:
                sheets_status = "⚠️ Dokumen duplikat (tidak otomatis ditambahkan ke Sheets)."
            else:
                sheets_status = "⏳ Belum dikirim ke Sheets (tekan tombol di bawah untuk mengirim)."

            summary_text = format_document_summary(
                doc=result.document,
                warnings=result.warnings,
                is_duplicate=result.is_duplicate,
                sheets_status=sheets_status,
            )

            keyboard = get_review_keyboard(result.document.no_dokumen or "UNKNOWN", already_synced=already_synced)
            await status_msg.edit_text(summary_text, reply_markup=keyboard, parse_mode="Markdown")

        except Exception as e:
            logger.error("Error processing photo: %s", e)
            await status_msg.edit_text(f"❌ Terjadi kesalahan saat memproses gambar: {str(e)}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles operator button clicks."""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = update.effective_user.id

        if data.startswith("approve_"):
            no_dokumen = data.replace("approve_", "")
            self.pipeline.confirm_and_export(no_dokumen, operator_id=str(user_id))
            if self.pipeline.sheets.is_live:
                msg = f"✅ **Dokumen `{no_dokumen}` berhasil dikirim langsung ke Google Sheets!**"
            else:
                msg = f"✅ **Dokumen `{no_dokumen}` dikonfirmasi & disimpan!** (Mode simulasi lokal aktif)."
            await query.edit_message_text(msg, parse_mode="Markdown")

        elif data.startswith("edit_menu_"):
            no_dokumen = data.replace("edit_menu_", "")
            keyboard = get_edit_fields_keyboard(no_dokumen)
            await query.edit_message_text(
                f"Pilih field pada dokumen `{no_dokumen}` yang ingin Anda koreksi:",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

        elif data.startswith("edit_field_"):
            parts = data.split("_")
            no_dokumen = parts[2]
            field_name = "_".join(parts[3:])

            self.pending_edits[user_id] = {"no_dokumen": no_dokumen, "field_name": field_name}
            await query.edit_message_text(
                f"Ketik nilai baru untuk field **{field_name}** pada dokumen `{no_dokumen}`:",
                parse_mode="Markdown",
            )

        elif data.startswith("back_review_"):
            no_dokumen = data.replace("back_review_", "")
            doc_data = self.pipeline.db.get_document(no_dokumen)
            if doc_data:
                doc = ProductionDocument(
                    no_dokumen=doc_data["no_dokumen"],
                    id_kain=doc_data["id_kain"] or "",
                    lot_kain_mentah=doc_data["lot_kain_mentah"] or "",
                    id_kain_jadi=doc_data["id_kain_jadi"] or "",
                    langganan=doc_data["langganan"] or "",
                    warna=doc_data["warna"] or "",
                    panjang=doc_data["panjang"] or "",
                )
                summary = format_document_summary(doc, warnings=[], is_duplicate=False)
                keyboard = get_review_keyboard(no_dokumen, already_synced=True)
                await query.edit_message_text(summary, reply_markup=keyboard, parse_mode="Markdown")

        elif data.startswith("reject_"):
            no_dokumen = data.replace("reject_", "")
            self.pipeline.db.update_status(
                no_dokumen=no_dokumen,
                new_status=DocumentStatus.REJECTED,
                operator_id=str(user_id),
                notes="Rejected by operator in Telegram",
            )
            await query.edit_message_text(f"❌ Dokumen `{no_dokumen}` telah dibatalkan/ditolak.")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Catches operator replies when correcting a field."""
        user_id = update.effective_user.id
        if user_id in self.pending_edits:
            edit_info = self.pending_edits.pop(user_id)
            no_dokumen = edit_info["no_dokumen"]
            field_name = edit_info["field_name"]
            new_val = update.message.text.strip()

            self.pipeline.db.update_field(
                no_dokumen=no_dokumen,
                field_name=field_name,
                new_value=new_val,
                operator_id=str(user_id),
            )

            # Auto-update to Google Sheets directly as well!
            sheets_status = ""
            if config.auto_sync_sheets:
                self.pipeline.confirm_and_export(no_dokumen, operator_id=str(user_id))
                if self.pipeline.sheets.is_live:
                    sheets_status = "✅ Perubahan langsung diperbarui di Google Sheets!"
                else:
                    sheets_status = "ℹ️ Perubahan diperbarui di database lokal (mode simulasi)."

            # Retrieve updated document
            doc_data = self.pipeline.db.get_document(no_dokumen)
            doc = ProductionDocument(
                no_dokumen=doc_data["no_dokumen"],
                id_kain=doc_data["id_kain"] or "",
                lot_kain_mentah=doc_data["lot_kain_mentah"] or "",
                id_kain_jadi=doc_data["id_kain_jadi"] or "",
                langganan=doc_data["langganan"] or "",
                warna=doc_data["warna"] or "",
                panjang=doc_data["panjang"] or "",
            )
            summary = format_document_summary(doc, warnings=[], is_duplicate=False, sheets_status=sheets_status)
            keyboard = get_review_keyboard(no_dokumen, already_synced=True)
            await update.message.reply_text(
                f"✅ Field **{field_name}** berhasil diubah menjadi: `{new_val}`\n\n{summary}",
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

    def build_application(self, token: str) -> Application:
        """Assembles telegram application with all handlers."""
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        return app

