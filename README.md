# OCR Kartu Proses Produksi — Skema 1 (PaddleOCR)

> **Status:** spesifikasi POC Skema 1. Belum ada implementasi atau hasil pengujian OCR otomatis; integrasi Telegram dan Google Sheets adalah fase berikutnya.

**Pendekatan yang dipilih:** OpenCV + PaddleOCR + pencocokan label/posisi teks. **YOLO tidak digunakan pada baseline ini** dan hanya dievaluasi jika pencarian lokasi field terbukti menjadi masalah.

## 1. Latar belakang

Data pada dokumen produksi kertas saat ini perlu dipindahkan secara manual ke spreadsheet. Proyek ini bertujuan membaca foto dokumen menggunakan Optical Character Recognition (OCR), mengambil tujuh informasi yang dibutuhkan, lalu menyimpannya sebagai satu baris per dokumen setelah diperiksa operator.

## 2. Ruang lingkup

- Input: foto atau scan dokumen produksi.
- Data yang diambil **hanya tujuh field** yang sebelumnya ditandai warna hijau pada foto contoh.
- Penanda hijau hanyalah anotasi untuk menunjukkan field yang dipilih; penanda tersebut **tidak wajib ada** pada dokumen operasional.
- Berdasarkan lima foto yang dibahas, struktur tabel informasi utama **tampak relatif konsisten**, walaupun perspektif, rotasi, pencahayaan, skala, dan lipatan dokumen berbeda. Variasi layout lain tetap mungkin.
- Output awal: Google Sheets, satu dokumen per baris.
- Antarmuka yang direncanakan: bot Telegram; proses OCR menggunakan Python.
- Setiap hasil harus bisa ditinjau dan dikoreksi sebelum disimpan.

## 3. Field yang diekstraksi

| No. | Nama kolom spreadsheet | Contoh dari foto | Keterangan |
| --- | --- | --- | --- |
| 1 | `no_dokumen` | `KP26101851` | Identitas dokumen dan kunci pemeriksaan duplikasi |
| 2 | `id_kain` | `1214` | Simpan sebagai teks agar format kode terjaga |
| 3 | `lot_kain_mentah` | `PP22` | Kode lot bahan |
| 4 | `id_kain_jadi` | `1214/61WRCRSF` | Kode dengan garis miring |
| 5 | `langganan` | `PT AYUNAN BULAN INTERNATIONAL` | Nama pelanggan |
| 6 | `warna` | `43 OLIVE BROWN (BR512833)` | Nama dan kode warna |
| 7 | `panjang` | `3,029.00 yards` | Pertahankan nilai asli; angka dan satuan dapat dipisah pada tahap pengolahan |

Contoh nilai di atas adalah **transkripsi visual sementara**, bukan hasil akurasi mesin OCR yang sudah teruji.

## 4. Alur Skema 1

1. POC menerima satu path foto lokal sebagai input.
2. OpenCV melakukan perbaikan seperlunya: orientasi, koreksi perspektif, kontras, dan pengurangan noise. Simpan versi asli agar hasil dapat dibandingkan.
3. PaddleOCR mengembalikan teks, bounding box, dan confidence untuk setiap deteksi.
4. Modul ekstraksi menormalisasi variasi ejaan label seperti `No.`, `ID Kain`, `Lot Kain Mentah`, `ID Kain Jadi`, `Langganan`, `Warna`, dan `Panjang`.
5. Pencocokan menggunakan urutan baca, kedekatan posisi pada baris, kolom tabel, dan pola nilai. Jangan menggunakan koordinat pixel tetap sebagai satu-satunya aturan.
6. Sistem mengeluarkan JSON tujuh field, beserta confidence/indikator kebutuhan review dan hasil OCR mentah untuk debugging.
7. Setelah POC teruji, integrasikan bot Telegram untuk mengirim foto, meninjau hasil, mengoreksi, dan mengonfirmasi penyimpanan ke Google Sheets.

## 5. Stack teknologi (usulan)

| Komponen | Teknologi |
| --- | --- |
| Bahasa & pemrosesan | Python |
| Perbaikan gambar | OpenCV |
| OCR utama | PaddleOCR (pilihan Skema 1) |
| Bot (fase lanjutan) | Telegram Bot API |
| Penyimpanan data (fase lanjutan) | Google Sheets API |
| Log/duplikasi (opsional untuk POC) | SQLite |

## 6. Validasi dan penanganan kesalahan

- `no_dokumen` harus terbaca, tidak kosong, dan diperiksa terhadap dokumen yang sudah tersimpan.
- Jangan otomatis menebak karakter ambigu (`O/0`, `I/1`, `S/5`) tanpa memberi kesempatan koreksi.
- Jika ada field hilang atau OCR tidak yakin, tandai untuk pemeriksaan operator.
- Simpan kode seperti `id_kain` sebagai teks; jangan sampai spreadsheet mengubah formatnya.
- Normalisasi `panjang` secara hati-hati: contoh `3,029.00 yards` berarti 3029.00 dalam format angka contoh. Satuan harus tetap jelas.
- Hindari dua proses menyimpan nomor dokumen sama secara bersamaan; cek ulang duplikasi saat penyimpanan.
- Catat waktu, nomor dokumen, status, serta error seperlunya tanpa menyebarkan foto atau data sensitif.

## 7. Tantangan yang diketahui

- Foto contoh sedikit miring, terlipat, dan bagian kanan/bawah terpotong.
- Tata letak bisa berubah: pendekatan posisi tetap tidak cukup andal.
- Field panjang dapat memiliki pemisah ribuan, desimal, serta satuan.
- Teks hasil cetak relatif jelas, tetapi akurasi aktual belum diukur.
- Penggunaan Telegram dan Google Sheets untuk data produksi perlu mendapat izin perusahaan terkait kerahasiaan dan kebijakan internal.

## 8. Struktur proyek yang direncanakan

```text
ocr-kartu-proses/
├── README.md
├── requirements.txt
├── samples/               # foto uji lokal, jangan commit data sensitif
├── outputs/               # JSON dan log hasil POC, abaikan dari git
├── src/
│   ├── preprocess.py      # normalisasi dan koreksi foto
│   ├── ocr_engine.py      # adapter PaddleOCR
│   ├── extract_fields.py  # matching label + nilai
│   ├── validate.py        # validasi 7 field
│   └── main.py            # CLI uji satu/banyak foto
└── tests/
    └── test_extract.py    # unit test parsing dan pola nilai
```

Struktur di atas adalah **rencana**, bukan daftar file kode yang sudah dibuat.

### Kontrak output POC

```json
{
  "source_file": "contoh_01.jpg",
  "fields": {
    "no_dokumen": "KP26101851",
    "id_kain": "1214",
    "lot_kain_mentah": "PP22",
    "id_kain_jadi": "1214/61WRCRSF",
    "langganan": "PT AYUNAN BULAN INTERNATIONAL",
    "warna": "43 OLIVE BROWN (BR512833)",
    "panjang": "3,029.00 yards"
  },
  "needs_review": true,
  "warnings": []
}
```

Contoh di atas adalah ilustrasi skema berdasarkan pembacaan visual, **bukan output program yang sudah dijalankan**. Nilai yang tidak dapat ditemukan harus `null`, bukan hasil tebakan.

## 9. Tahapan implementasi

### Fase 1 — POC OCR lokal

- Jalankan OCR pada kelima foto contoh.
- Ekstrak tujuh field dalam bentuk JSON/dictionary.
- Buat ground truth yang diperiksa manusia untuk 5 × 7 = **35 nilai**. Tandai karakter yang ambigu untuk diverifikasi dari foto asli.
- Bandingkan hasil otomatis dengan ground truth, field per field.
- Dokumentasikan kesalahan pembacaan dan pemetaan field.

### Fase 2 — Pengujian variasi dokumen

- Minta 5–10 contoh dokumen dengan variasi format dan kualitas foto (samarkan data sensitif bila perlu).
- Ukur akurasi **per field**, persentase dokumen yang seluruh tujuh field-nya benar, dan kebutuhan koreksi operator.
- Revisi aturan ekstraksi berdasarkan pola kesalahan.

### Fase 3 — Integrasi

- Buat bot Telegram yang menerima foto dan menampilkan tujuh hasil ekstraksi.
- Tambahkan alur koreksi dan konfirmasi.
- Hubungkan ke Google Sheets dengan proteksi input duplikat.

### Fase 4 — Pilot pabrik

- Uji dengan operator dan alur kerja asli setelah persetujuan perusahaan.
- Catat waktu proses per dokumen, kesalahan, dan penghematan waktu dibanding input manual.
- Putuskan kebutuhan hosting, kontrol akses, retensi foto, dan pemeliharaan.

## 10. Evaluasi dan kriteria keberhasilan POC

- Semua tujuh field dapat diwakili dalam output yang terstruktur.
- Hasil OCR ditinjau sebelum masuk spreadsheet.
- Nomor dokumen yang sama tidak menghasilkan baris ganda.
- Akurasi dan waktu proses **diukur**, bukan diasumsikan; target produksi ditentukan bersama pihak pabrik setelah melihat data pengujian.
- Laporkan `field_exact_match = jumlah field benar / jumlah field yang diverifikasi` dan `document_exact_match = jumlah dokumen dengan ketujuh field benar / jumlah dokumen uji`.
- Catat jenis kegagalan: label tidak ditemukan, salah lokasi pasangan, teks salah baca, atau foto tidak layak.
- Lima foto awal hanya untuk *smoke test*; hasilnya tidak cukup untuk menyatakan kesiapan produksi. Tambahkan sampel uji yang belum dipakai menyetel aturan.

## 11. Pertanyaan terbuka

1. Apakah perubahan antarformat hanya posisi tabel, atau juga nama label dan bentuk dokumennya?
2. Apakah koneksi internet dan penggunaan Telegram/Google Sheets diizinkan oleh pabrik?
3. Apakah panjang selalu menggunakan `yards`, atau bisa menggunakan satuan lain?
4. Apakah spreadsheet tujuan sudah memiliki template kolom yang wajib diikuti?
5. Berapa banyak dokumen diproses setiap hari dan siapa yang berwenang melakukan koreksi?

## 12. Langkah terdekat

Implementasikan CLI POC Skema 1 dan uji **tujuh field pada kelima foto secara lokal**. Kumpulkan sampel baru untuk pengujian di luar data pengembangan. YOLO menjadi opsi lanjutan hanya apabila evaluasi menunjukkan pendekatan berbasis label/posisi tidak memadai. Jangan menyatakan OCR sudah akurat atau aplikasi siap dipakai sebelum ada hasil pengujian terukur.
