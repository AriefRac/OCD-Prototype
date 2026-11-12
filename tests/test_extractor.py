from src.extractor.pattern_extractor import DocumentExtractor
from src.models.document import BoundingBox, OCRTextBlock


def test_extractor_spatial_matching():
    extractor = DocumentExtractor()

    blocks = [
        OCRTextBlock("SURAT JALAN / PRODUKSI", BoundingBox(100, 20, 400, 50), 0.99),
        # Label and adjacent value
        OCRTextBlock("NO. DOKUMEN:", BoundingBox(50, 100, 180, 120), 0.95),
        OCRTextBlock("KP26101851", BoundingBox(200, 100, 320, 120), 0.98),
        # Inline label + value
        OCRTextBlock("LANGGANAN: PT AYUNAN BULAN INTERNATIONAL", BoundingBox(50, 140, 500, 160), 0.97),
        # ID Kain
        OCRTextBlock("ID KAIN:", BoundingBox(50, 180, 140, 200), 0.96),
        OCRTextBlock("1214", BoundingBox(160, 180, 220, 200), 0.99),
        # Lot
        OCRTextBlock("LOT KAIN MENTAH:", BoundingBox(50, 220, 200, 240), 0.95),
        OCRTextBlock("PP22", BoundingBox(220, 220, 280, 240), 0.95),
        # ID Kain Jadi
        OCRTextBlock("ID KAIN JADI:", BoundingBox(50, 260, 180, 280), 0.95),
        OCRTextBlock("1214/61WRCRSF", BoundingBox(200, 260, 360, 280), 0.94),
        # Warna
        OCRTextBlock("WARNA:", BoundingBox(50, 300, 130, 320), 0.97),
        OCRTextBlock("43 OLIVE BROWN (BR512833)", BoundingBox(150, 300, 420, 320), 0.95),
        # Panjang
        OCRTextBlock("PANJANG:", BoundingBox(50, 340, 140, 360), 0.98),
        OCRTextBlock("3,029.00 yards", BoundingBox(160, 340, 300, 360), 0.97),
    ]

    doc, fields, warnings = extractor.extract(blocks)

    assert doc.no_dokumen == "KP26101851"
    assert doc.id_kain == "1214"
    assert doc.lot_kain_mentah == "PP22"
    assert doc.id_kain_jadi == "1214/61WRCRSF"
    assert "AYUNAN BULAN" in doc.langganan
    assert "OLIVE BROWN" in doc.warna
    assert doc.panjang == "3,029.00 yards"
    assert doc.parsed_panjang_numeric == 3029.0
    assert doc.parsed_panjang_unit == "yards"


def test_ambiguity_warning():
    extractor = DocumentExtractor()
    blocks = [
        OCRTextBlock("NO. DOKUMEN:", BoundingBox(50, 100, 180, 120), 0.95),
        # Has capital 'O' with digits
        OCRTextBlock("KP261O1851", BoundingBox(200, 100, 320, 120), 0.95),
    ]

    doc, fields, warnings = extractor.extract(blocks)
    assert any("O" in w for w in warnings)

