# BookPOS - Point of Sale & Book Inventory Management System

BookPOS adalah aplikasi web terintegrasi untuk pengelolaan transaksi kasir (Point of Sale) dan manajemen inventaris buku toko. Sistem ini dirancang dengan arsitektur modern berbasis serverless Python dan framework UI Webix yang ringan, terhubung langsung ke basis data dokumen MongoDB Atlas.

---

## 📌 Deskripsi & Spesifikasi Sistem

Sistem ini ditujukan untuk operasional toko buku dengan fokus pada kecepatan pemindaian barcode, keakuratan stok inventaris, serta pemeliharaan integritas riwayat transaksi penjualan.

### 1. Spesifikasi Modul Kasir (Point of Sale)
- **Pemindaian Barcode / ISBN:** Mendukung input cepat melalui barcode scanner atau pencarian manual dengan normalisasi format ISBN-13 (menghapus spasi dan tanda hubung otomatis).
- **Keranjang Belanja Real-time:** Pengaturan kuantitas interaktif (`+` / `-`), kalkulasi subtotal otomatis, serta validasi batas ketersediaan stok fisik.
- **Opsi Pembayaran Multimetode:** Mendukung transaksi Tunai (dengan kalkulasi uang kembalian dan pilihan pecahan cepat), Kartu Debit/Kredit, dan QRIS.
- **Struk Thermal Siap Cetak:** Tampilan pratinjau struk penjualan standar toko buku yang dioptimalkan untuk mesin pencetak thermal (80mm/standard printer) menggunakan aturan `@media print`.
- **Riwayat Penjualan:** Penelusuran arsip transaksi dan pencetakan ulang struk berdasarkan nomor faktur (`no_faktur`).

### 2. Spesifikasi Modul Master Data & Inventaris
- **Katalog Buku:** Manajemen data judul, penulis, penerbit, nomor ISBN unik, harga beli, harga jual, dan margin keuntungan.
- **Integritas & Penyesuaian Stok:** Nilai stok dilindungi agar tidak tertimpa saat pengeditan informasi buku. Penambahan (restok) atau pengurangan (rusak/retur) dilakukan melalui alur penyesuaian stok terpisah, serta pemotongan stok secara atomik saat checkout kasir.
- **Mekanisme Soft Delete:** Penonaktifan buku menggunakan flag status (`aktif: false`) untuk memastikan data buku yang pernah terjual tetap utuh pada arsip transaksi dan laporan masa lalu.
- **Manajemen Kategori:** Relasi buku ke kategori berbasis ID (`kategori_id`), dengan perlindungan penghapusan jika kategori masih dirujuk oleh dokumen buku.
- **Manajemen Pegawai:** Pengelolaan akun staf dengan pemisahan peran (*Admin* dan *Kasir*) serta enkripsi hash password satu arah.

---

## 🛠️ Spesifikasi Teknologi (Tech Stack)

| Lapisan | Teknologi | Keterangan |
|---|---|---|
| **Frontend** | Webix UI Framework | Dimuat melalui CDN tanpa dependensi build Node.js / NPM |
| **Styling** | Vanilla CSS | Kustomisasi tema, tipografi Plus Jakarta Sans, dan tata cetak struk |
| **Backend** | Python 3 / Flask | Arsitektur REST API modular dan kompatibel Serverless WSGI |
| **Database** | MongoDB Atlas | Basis data dokumen NoSQL menggunakan driver `pymongo` |
| **Hosting / Runtime** | Vercel | Serverless Functions (`@vercel/python`) dan Static Hosting (`@vercel/static`) |

---

## 🗄️ Spesifikasi Skema Dokumen Basis Data

Sistem menggunakan 4 koleksi MongoDB utama:

1. **`books`**
   * Menyimpan katalog judul dan jumlah eksemplar fisik.
   * Field: `isbn` (unik), `judul`, `penulis`, `penerbit`, `kategori_id` (ObjectId), `harga_beli` (integer Rupiah), `harga_jual` (integer Rupiah), `stok` (integer), `aktif` (boolean), `created_at`, `updated_at`.
   * Indeks: `isbn` (unique), `judul`, `kategori_id`, `aktif`.

2. **`categories`**
   * Mengelompokkan klasifikasi buku toko.
   * Field: `nama`, `slug` (unik).
   * Proteksi: Dilarang dihapus apabila masih dirujuk oleh dokumen buku (aktif maupun nonaktif).

3. **`users`**
   * Mengelola data staf operasional dan hak akses.
   * Field: `username` (unik), `password_hash`, `nama`, `role` (`admin` / `kasir`), `aktif` (boolean), `created_at`, `updated_at`.
   * Kebijakan: Staf yang tidak aktif dinonaktifkan (`aktif: false`), bukan dihapus fisik.

4. **`transactions`**
   * Mencatat faktur penjualan kasir yang bersifat permanen (*immutable*).
   * Field: `no_faktur` (unik), `items` (rincian buku, jumlah, harga jual, subtotal), `total`, `metode_pembayaran`, `tunai_diterima`, `kembalian`, `kasir_nama`, `created_at`.

---

## 📁 Struktur Direktori Proyek

```
BookPOS/
├── api/
│   ├── __init__.py         # Package identifier
│   ├── app.py              # Endpoint API, logika bisnis & perutean lokal
│   └── database.py         # Konfigurasi koneksi MongoDB Atlas & serialisasi
├── public/
│   ├── index.html          # Antarmuka Kasir / Point of Sale
│   ├── master.html         # Antarmuka Master Data Buku, Kategori & Pegawai
│   └── style.css           # Desain visual, badge status & stylesheet cetak
├── .env.example            # Template konfigurasi variabel lingkungan
├── requirements.txt        # Dependensi pustaka Python
├── vercel.json             # Konfigurasi perutean monorepo Vercel
├── SkemaUserDanBuku.md     # Dokumen kamus data Modul A (Master Data)
└── README.md               # Spesifikasi dan keterangan aplikasi
```
