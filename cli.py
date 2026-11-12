import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.config import config
from src.models.document import DocumentStatus
from src.ocr.factory import get_ocr_engine
from src.pipeline import ProductionOCRPipeline
from src.storage.database import DatabaseManager
from src.utils.synthetic_generator import create_synthetic_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("cli")


def cmd_generate_sample(args):
    out = Path(args.output) if args.output else config.samples_dir / "sample_synthetic_1.jpg"
    created = create_synthetic_document(
        output_path=out,
        rotate_angle=args.rotate or 0.0,
    )
    print(f"\n[+] Dokumen sampel sintetis berhasil dibuat di: {created}")


def cmd_process(args):
    img_path = Path(args.image)
    if not img_path.exists():
        print(f"[-] File tidak ditemukan: {img_path}")
        sys.exit(1)

    ocr_engine = get_ocr_engine(args.engine or config.ocr_engine)
    pipeline = ProductionOCRPipeline(ocr_engine=ocr_engine)

    if not args.json:
        print(f"\n[*] Memproses gambar '{img_path.name}' menggunakan engine '{args.engine or config.ocr_engine}'...")
    result = pipeline.process_image(img_path)

    if args.json:
        contract_data = result.to_contract_dict(source_file=img_path.name)
        print(json.dumps(contract_data, indent=2, ensure_ascii=False))
    else:
        print("\n" + "=" * 50)
        print("HASIL EKSTRAKSI 7 FIELD:")
        print("=" * 50)
        for k, v in result.document.to_dict().items():
            conf = result.fields.get(k).confidence if k in result.fields else 0.0
            print(f"  • {k.ljust(18)}: {v}  (conf: {conf:.2f})")

        if result.document.parsed_panjang_numeric is not None:
            print(f"  • [parsed_panjang]  : {result.document.parsed_panjang_numeric} {result.document.parsed_panjang_unit}")

        if result.warnings:
            print("\n[!] PERINGATAN VALIDASI:")
            for w in result.warnings:
                print(f"  - {w}")

    if args.save:
        doc_id = pipeline.save_pending_draft(result, operator_notes="Processed via CLI")
        if not args.json:
            print(f"\n[+] Draft berhasil disimpan ke SQLite dengan ID #{doc_id}")


def cmd_list(args):
    db = DatabaseManager(config.database_path)
    status_filter = DocumentStatus(args.status) if args.status else None
    docs = db.list_documents(status=status_filter, limit=args.limit)

    print("\n" + "=" * 80)
    print(f"DAFTAR DOKUMEN TERSIMPAN ({len(docs)} dokumen):")
    print("=" * 80)
    if not docs:
        print("  (Belum ada data dokumen di database)")
        return

    for d in docs:
        print(
            f"ID: {d['id']:<3} | No: {d['no_dokumen']:<12} | Status: {d['status']:<14} | "
            f"Kain: {d['id_kain']:<6} | Langganan: {d['langganan'][:25]}"
        )


def cmd_confirm(args):
    pipeline = ProductionOCRPipeline()
    success = pipeline.confirm_and_export(args.no_dokumen, operator_id="cli_operator")
    if success:
        print(f"\n[+] Dokumen {args.no_dokumen} berhasil dikonfirmasi dan diekspor!")
    else:
        print(f"\n[-] Konfirmasi/ekspor dokumen {args.no_dokumen} gagal atau berjalan dalam mode simulasi.")


def cmd_run_server(args):
    import uvicorn
    print(f"[+] Menjalankan Local AI REST API Server di http://{args.host}:{args.port}...")
    uvicorn.run("src.api_server:app", host=args.host, port=args.port, reload=args.reload)


def cmd_run_bot(args):
    if not config.telegram_bot_token:
        print("[-] TELEGRAM_BOT_TOKEN belum diisi di file .env!")
        sys.exit(1)

    from src.bot.telegram_bot import FactoryTelegramBot

    pipeline = ProductionOCRPipeline()
    bot = FactoryTelegramBot(pipeline)
    app = bot.build_application(config.telegram_bot_token)
    if args.webhook:
        base_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
        secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
        if not base_url.startswith("https://") or not secret:
            sys.exit("Mode webhook memerlukan RENDER_EXTERNAL_URL (HTTPS) dan TELEGRAM_WEBHOOK_SECRET.")
        app.run_webhook(
            listen="0.0.0.0", port=int(os.getenv("PORT", "10000")),
            url_path="telegram", webhook_url=f"{base_url}/telegram",
            secret_token=secret, max_connections=1,
        )
        return
    print("[+] Menjalankan Bot Telegram (polling mode)... Tekan Ctrl+C untuk berhenti.")
    app.run_polling()


def main():
    parser = argparse.ArgumentParser(description="OCR Dokumen Produksi Pabrik - CLI Infrastructure Tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # generate-sample
    p_gen = subparsers.add_parser("generate-sample", help="Buat gambar contoh dokumen sintetis untuk pengujian")
    p_gen.add_argument("--output", "-o", help="Path tujuan penyimpanan gambar")
    p_gen.add_argument("--rotate", "-r", type=float, default=0.0, help="Sudut rotasi simulasi kemiringan")
    p_gen.set_defaults(func=cmd_generate_sample)

    # process
    p_proc = subparsers.add_parser("process", help="Proses foto dokumen dengan pipeline OCR")
    p_proc.add_argument("image", help="Path ke file gambar dokumen")
    p_proc.add_argument("--engine", "-e", choices=["mock", "tesseract", "paddleocr", "rapidocr"], help="Pilih OCR engine")
    p_proc.add_argument("--save", "-s", action="store_true", help="Simpan draft ke database SQLite")
    p_proc.add_argument("--json", "-j", action="store_true", help="Output JSON sesuai kontrak POC README")
    p_proc.set_defaults(func=cmd_process)

    # list-docs
    p_list = subparsers.add_parser("list-docs", help="Lihat daftar dokumen di database")
    p_list.add_argument("--status", choices=[s.value for s in DocumentStatus], help="Filter status")
    p_list.add_argument("--limit", type=int, default=20, help="Batas jumlah baris")
    p_list.set_defaults(func=cmd_list)

    # confirm
    p_conf = subparsers.add_parser("confirm", help="Konfirmasi dan ekspor dokumen ke Google Sheets")
    p_conf.add_argument("no_dokumen", help="Nomor dokumen yang akan dikonfirmasi")
    p_conf.set_defaults(func=cmd_confirm)

    # run-bot
    p_bot = subparsers.add_parser("run-bot", help="Jalankan antarmuka bot Telegram")
    p_bot.add_argument("--webhook", action="store_true", help="Terima update lewat HTTPS publik Render")
    p_bot.set_defaults(func=cmd_run_bot)

    # run-server
    p_srv = subparsers.add_parser("run-server", help="Jalankan Local AI REST API Server")
    p_srv.add_argument("--host", default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    p_srv.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    p_srv.add_argument("--reload", action="store_true", help="Auto reload on code change")
    p_srv.set_defaults(func=cmd_run_server)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

