from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


def create_synthetic_document(
    output_path: Path,
    no_dokumen: str = "KP26101851",
    id_kain: str = "1214",
    lot_kain_mentah: str = "PP22",
    id_kain_jadi: str = "1214/61WRCRSF",
    langganan: str = "PT AYUNAN BULAN INTERNATIONAL",
    warna: str = "43 OLIVE BROWN (BR512833)",
    panjang: str = "3,029.00 yards",
    rotate_angle: float = 0.0,
) -> Path:
    """Generates a synthetic factory production document image for testing and benchmarking."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Canvas dimensions (A4 proportion roughly)
    width, height = 1200, 1600
    img = Image.new("RGB", (width, height), color=(250, 250, 248))
    draw = ImageDraw.Draw(img)

    # Basic fonts (default PIL fallback)
    try:
        font_title = ImageFont.truetype("arial.ttf", 36)
        font_header = ImageFont.truetype("arialbd.ttf", 24)
        font_text = ImageFont.truetype("arial.ttf", 22)
        font_bold = ImageFont.truetype("arialbd.ttf", 22)
    except IOError:
        font_title = ImageFont.load_default()
        font_header = ImageFont.load_default()
        font_text = ImageFont.load_default()
        font_bold = ImageFont.load_default()

    # Outer border / header
    draw.rectangle([(50, 50), (width - 50, height - 50)], outline=(40, 40, 40), width=3)
    draw.text((100, 80), "SURAT PERINTAH PRODUKSI KAIN", fill=(0, 0, 0), font=font_title)
    draw.line([(50, 150), (width - 50, 150)], fill=(40, 40, 40), width=2)

    # Info grid
    rows = [
        ("NO. DOKUMEN:", no_dokumen, True),
        ("LANGGANAN:", langganan, False),
        ("ID KAIN:", id_kain, True),
        ("LOT KAIN MENTAH:", lot_kain_mentah, False),
        ("ID KAIN JADI:", id_kain_jadi, True),
        ("WARNA:", warna, False),
        ("PANJANG:", panjang, True),
    ]

    start_y = 200
    row_height = 60

    for i, (label, val, highlight) in enumerate(rows):
        y = start_y + (i * row_height)

        # Draw green highlight annotation box if marked (mimicking README note)
        if highlight:
            draw.rectangle([(380, y - 5), (950, y + 35)], fill=(220, 255, 220))

        # Label
        draw.text((100, y), label, fill=(30, 30, 30), font=font_header)
        # Value
        draw.text((400, y), val, fill=(0, 0, 0), font=font_bold)
        # Row divider
        draw.line([(80, y + 45), (width - 80, y + 45)], fill=(200, 200, 200), width=1)

    # Add a mock table section below
    table_y = 700
    draw.rectangle([(80, table_y), (width - 80, table_y + 400)], outline=(80, 80, 80), width=2)
    draw.line([(80, table_y + 50), (width - 80, table_y + 50)], fill=(80, 80, 80), width=2)
    draw.text((100, table_y + 12), "RINCIAN GULUNGAN / PIECE", fill=(0, 0, 0), font=font_header)

    # Rotate if needed (to test deskew algorithm)
    if rotate_angle != 0.0:
        img = img.rotate(rotate_angle, expand=True, fillcolor=(255, 255, 255))

    img.save(output_path, "JPEG", quality=95)
    return output_path

