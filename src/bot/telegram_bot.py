import asyncio
from collections import OrderedDict
import logging
from typing import Dict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
from src.models.document import DocumentStatus, OCRTextBlock, ProductionDocument
from src.pipeline import ProductionOCRPipeline

logger = logging.getLogger(__name__)


def format_document_summary(
    doc: ProductionDocument,
    warnings: list,
    is_duplicate: bool,
    review_prompt: str = "Sudah sesuai dengan foto? Pilih Kirim ke Sheets atau Koreksi Nilai.",
) -> str:
    labels = ("No. Dokumen", "ID Kain", "Lot Kain Mentah", "ID Kain Jadi", "Langganan", "Warna", "Panjang")
    values = (doc.no_dokumen, doc.id_kain, doc.lot_kain_mentah, doc.id_kain_jadi, doc.langganan, doc.warna, doc.panjang)
    lines = [f"{label}: {value or '(belum terbaca)'}" for label, value in zip(labels, values)]
    text = "Hasil pembacaan foto\n\n" + "\n".join(lines)
    if is_duplicate:
        text += "\n\nNomor ini sudah tersimpan."
    if warnings:
        text += "\n\nCatatan: " + "\n".join(warnings)
    if doc.no_dokumen:
        text += "\n\n" + review_prompt
    else:
        text += "\n\nKirim ulang foto dengan nomor dokumen yang terlihat jelas."
    return text


class FactoryTelegramBot:
    """Telegram Bot interface for document upload, OCR review, correction, and syncing."""

    def __init__(self, pipeline: ProductionOCRPipeline):
        self.pipeline = pipeline
        self.recent_photos: OrderedDict[str, list[OCRTextBlock]] = OrderedDict()
        self.pending_edits: Dict[int, Dict[str, str]] = {}  # user_id -> {no_dokumen, field_name}

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "👋 Selamat datang di Bot OCR Dokumen Produksi Pabrik.\n\n"
            "Kirimkan foto atau scan surat perintah / dokumen produksi untuk mengekstrak 7 data utama.\n"
            "Anda dapat meninjau dan mengoreksi data sebelum disimpan ke Google Sheets.\n\n"
            "Gunakan /help untuk bantuan, /list untuk melihat dokumen terakhir."
        )

    async def greet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Halo! Bot OCR aktif. Silakan kirim foto dokumen produksi.")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📖 Panduan Penggunaan:\n\n"
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
            photo_key = photo.file_unique_id
            if photo_key in self.recent_photos:
                self.recent_photos.move_to_end(photo_key)
                result = self.pipeline.process_blocks(self.recent_photos[photo_key])
            else:
                file = await photo.get_file()
                photo_bytes = await file.download_as_bytearray()
                result = await asyncio.to_thread(self.pipeline.process_image, bytes(photo_bytes))
                if result.raw_ocr_blocks:
                    self.recent_photos[photo_key] = result.raw_ocr_blocks
                    if len(self.recent_photos) > 8:
                        self.recent_photos.popitem(last=False)

            # Save draft in SQLite
            if result.document.no_dokumen and not result.is_duplicate:
                self.pipeline.save_pending_draft(
                    result=result,
                    operator_notes="Uploaded via Telegram",
                    operator_id=str(user.id),
                )

            doc = result.document
            keyboard = get_review_keyboard(doc.no_dokumen) if doc.no_dokumen else None
            summary = format_document_summary(doc, result.warnings, result.is_duplicate)
            if result.is_duplicate:
                record = self.pipeline.db.get_document(doc.no_dokumen)
                if any(value != record[key] for key, value in doc.to_dict().items()):
                    # Only the latest unaccepted rescan per user is retained.
                    context.user_data["rescan"] = (update.effective_chat.id, update.message.message_id, result)
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("Pakai hasil foto ini", callback_data=f"rescan_{update.message.message_id}")],
                        [InlineKeyboardButton("Buka draf tersimpan", callback_data=f"back_review_{doc.no_dokumen}")],
                    ])
                    summary = format_document_summary(doc, result.warnings, True,
                        "Hasil ini berbeda dari draf tersimpan. Pilih data yang ingin diperiksa.")
            await update.message.reply_text(summary, reply_markup=keyboard, do_quote=True)
            await status_msg.edit_text("Pembacaan foto selesai.")

        except Exception as e:
            logger.error("Error processing photo: %s", e)
            await status_msg.edit_text(f"❌ Terjadi kesalahan saat memproses gambar: {str(e)}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handles operator button clicks."""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = update.effective_user.id

        if data.startswith("rescan_"):
            scan = context.user_data.get("rescan")
            if not scan or scan[:2] != (update.effective_chat.id, int(data.removeprefix("rescan_"))):
                await query.edit_message_text("Kirim ulang foto untuk melihat hasil pembacaan terbaru.")
                return
            result = scan[2]
            self.pipeline.save_pending_draft(result, operator_notes="Rescan confirmed via Telegram",
                                             operator_id=str(user_id), refresh=True)
            del context.user_data["rescan"]
            await query.edit_message_text(format_document_summary(result.document, [], False),
                                          reply_markup=get_review_keyboard(result.document.no_dokumen))
        elif data.startswith("approve_"):
            no_dokumen = data.replace("approve_", "")
            exported = await asyncio.to_thread(self.pipeline.confirm_and_export, no_dokumen, operator_id=str(user_id))
            if not exported:
                await query.edit_message_text(
                    "Pengiriman belum dikonfirmasi oleh Sheets. Periksa spreadsheet lalu coba kembali.",
                    reply_markup=get_review_keyboard(no_dokumen),
                )
                return
            if self.pipeline.sheets.is_live:
                msg = f"✅ Dokumen {no_dokumen} berhasil dikirim langsung ke Google Sheets!"
            else:
                msg = f"✅ Dokumen {no_dokumen} dikonfirmasi & disimpan! (Mode simulasi lokal aktif)."
            await query.edit_message_text(msg)

        elif data.startswith("edit_menu_"):
            no_dokumen = data.replace("edit_menu_", "")
            keyboard = get_edit_fields_keyboard(no_dokumen)
            await query.edit_message_text(
                f"Pilih field pada dokumen {no_dokumen} yang ingin Anda koreksi:",
                reply_markup=keyboard,
            )

        elif data.startswith("edit_field_"):
            parts = data.split("_")
            no_dokumen = parts[2]
            field_name = "_".join(parts[3:])

            self.pending_edits[user_id] = {"no_dokumen": no_dokumen, "field_name": field_name}
            await query.edit_message_text(
                f"Ketik nilai baru untuk field {field_name} pada dokumen {no_dokumen}:",
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
                keyboard = get_review_keyboard(no_dokumen)
                await query.edit_message_text(summary, reply_markup=keyboard)

        elif data.startswith("reject_"):
            no_dokumen = data.replace("reject_", "")
            self.pipeline.db.update_status(
                no_dokumen=no_dokumen,
                new_status=DocumentStatus.REJECTED,
                operator_id=str(user_id),
                notes="Rejected by operator in Telegram",
            )
            await query.edit_message_text(f"❌ Dokumen {no_dokumen} telah dibatalkan/ditolak.")

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
            summary = format_document_summary(doc, warnings=[], is_duplicate=False)
            keyboard = get_review_keyboard(no_dokumen)
            await update.message.reply_text(
                f"✅ Field {field_name} berhasil diubah menjadi: {new_val}\n\n{summary}",
                reply_markup=keyboard,
            )

        elif update.message.text.strip().casefold() in {"halo", "test"}:
            await self.greet(update, context)

    def build_application(self, token: str) -> Application:
        """Assembles telegram application with all handlers."""
        app = ApplicationBuilder().token(token).build()
        app.add_handler(CommandHandler("start", self.start_command))
        app.add_handler(CommandHandler("help", self.help_command))
        app.add_handler(CommandHandler(["halo", "test"], self.greet))
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))
        app.add_handler(CallbackQueryHandler(self.handle_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        return app

