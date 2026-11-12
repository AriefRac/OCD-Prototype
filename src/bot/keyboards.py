from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.models.document import ProductionDocument


def get_review_keyboard(no_dokumen: str, already_synced: bool = False) -> InlineKeyboardMarkup:
    """Main confirmation buttons after OCR extraction."""
    action_label = "🔄 Kirim Ulang ke Sheets" if already_synced else "📊 Kirim Langsung ke Sheets"
    keyboard = [
        [
            InlineKeyboardButton(action_label, callback_data=f"approve_{no_dokumen}"),
            InlineKeyboardButton("✏️ Koreksi Nilai", callback_data=f"edit_menu_{no_dokumen}"),
        ],
        [
            InlineKeyboardButton("❌ Batalkan / Tolak", callback_data=f"reject_{no_dokumen}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_edit_fields_keyboard(no_dokumen: str) -> InlineKeyboardMarkup:
    """Sub-menu allowing operator to pick which field to correct."""
    keyboard = [
        [
            InlineKeyboardButton("1. No Dokumen", callback_data=f"edit_field_{no_dokumen}_no_dokumen"),
            InlineKeyboardButton("2. ID Kain", callback_data=f"edit_field_{no_dokumen}_id_kain"),
        ],
        [
            InlineKeyboardButton("3. Lot Kain Mentah", callback_data=f"edit_field_{no_dokumen}_lot_kain_mentah"),
            InlineKeyboardButton("4. ID Kain Jadi", callback_data=f"edit_field_{no_dokumen}_id_kain_jadi"),
        ],
        [
            InlineKeyboardButton("5. Langganan", callback_data=f"edit_field_{no_dokumen}_langganan"),
            InlineKeyboardButton("6. Warna", callback_data=f"edit_field_{no_dokumen}_warna"),
        ],
        [
            InlineKeyboardButton("7. Panjang", callback_data=f"edit_field_{no_dokumen}_panjang"),
        ],
        [
            InlineKeyboardButton("⬅️ Kembali ke Konfirmasi", callback_data=f"back_review_{no_dokumen}"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

