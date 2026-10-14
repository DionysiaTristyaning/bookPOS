# BookPOS - Point of Sale & Book Inventory Management System

BookPOS adalah aplikasi web kasir (Point of Sale) dan manajemen inventaris toko buku modern berbasis arsitektur **Python Flask (Serverless WSGI)** dan antarmuka **Webix UI Framework**, terhubung langsung ke basis data dokumen cloud **MongoDB Atlas**.

Aplikasi ini dirancang untuk operasional toko buku yang mengutamakan kecepatan transaksi kasir, pemindaian barcode/ISBN, keakuratan stok inventaris, serta integritas laporan arsip penjualan.

---

## 📌 Fitur & Modul Utama

### 1. Modul Kasir (Point of Sale - `index.html`)
- **Pencarian Cepat & Scan Barcode:** Mendukung pemindai barcode fisik maupun pencarian teks dengan normalisasi otomatis format ISBN-13 (menghilangkan spasi dan tanda hubung).
- **Keranjang Belanja Real-time:** Kontrol kuantitas instan (`+` / `−`), kalkulasi subtotal dinamis, serta validasi otomatis terhadap sisa stok buku fisik.
- **Multimetode Pembayaran:**
  - **💵 Tunai (Cash):** Input nominal, validasi uang kurang, kalkulasi uang kembalian otomatis, dan tombol pecahan cepat (Uang Pas, 50k, 100k, 200k, 500k, 1jt).
  - **💳 Kartu (Debit/Kredit):** Otomatis menyesuaikan nominal transaksi.
  - **📱 QRIS:** Dilengkapi **Pop-up Modal Barcode QRIS Statis** resmi. Saat QRIS dipilih, kolom nominal kasir disembunyikan secara bersih dan digantikan konfirmasi scan QR code pelanggan.
- **Struk Penjualan Thermal Siap Cetak:** Format nota kasir yang dioptimalkan untuk printer thermal (58mm/80mm) menggunakan aturan CSS `@media print`.
- **Riwayat Nota:** Akses cepat untuk melihat arsip transaksi sebelumnya dan mencetak ulang struk faktur.

### 2. Modul Master Data & Inventaris (`master.html`)
- **Katalog Buku Komprehensif:** Manajemen judul, pengarang, penerbit, nomor ISBN-13 unik, harga beli, harga jual, margin laba, serta stok eksemplar.
- **Penyesuaian Stok Terproteksi:** Stok dilindungi agar tidak tertimpa saat pengeditan metadata buku. Penambahan/pengurangan stok dilakukan melalui modal penyesuaian stok khusus (*Restok / Retur / Rusak*).
- **Mekanisme Soft Delete:** Penonaktifan buku menggunakan flag `aktif: false` sehingga buku yang pernah terjual tidak merusak riwayat transaksi dan laporan penjualan terdahulu. Buku nonaktif dapat dipulihkan kapan saja.
- **Manajemen Kategori:** Klasifikasi buku berbasis relasi ID (`kategori_id`), dilengkapi proteksi larangan menghapus kategori yang masih dirujuk oleh buku.
- **Manajemen Pegawai:** Pengelolaan staf toko dengan pemisahan peran (*Admin* dan *Kasir*), enkripsi hash password satu arah, dan status aktif.

### 3. Modul Laporan & Analitik Penjualan (`laporan.html`)
- **Ringkasan Indikator Kinerja (KPI):** Total Omzet, Total Buku Terjual, Jumlah Transaksi, dan Rata-rata Nilai Transaksi per Pelanggan (AOV).
- **Grafik Tren Penjualan Harian:** Visualisasi batang distribusi omzet per hari kerja (zona waktu WIB / UTC+7).
- **Peringkat Buku Terlaris (*Top Selling Books*):** Rekapitulasi judul buku dengan penjualan tertinggi.
- **Tabel Rincian Transaksi:** Filter rentang tanggal fleksibel (Hari ini, 7 hari terakhir, 30 hari terakhir, atau kustom).

### 4. Modul Autentikasi & Keamanan (`login.html`)
- **Autentikasi JWT (JSON Web Token):** Sesi login aman dengan token berbasis masa berlaku (*expiration*).
- **Kontrol Akses Berbasis Peran (*Role-Based Access Control*):**
  - **Admin:** Memiliki akses penuh ke seluruh menu (Kasir, Master Data, Laporan Penjualan, Kelola Pegawai).
  - **Kasir:** Terfokus pada modul operasional penjualan (Kasir/POS dan Riwayat Nota).
- **Indikator Live Database:** Deteksi status koneksi real-time ke MongoDB Atlas Cloud.

---

## 🛠️ Arsitektur & Spesifikasi Teknologi

| Komponen | Teknologi | Keterangan |
|---|---|---|
| **Backend API** | Python 3 / Flask | RESTful API modular, Blueprint `/api`, standar WSGI Serverless |
| **Database** | MongoDB Atlas (Cloud) | Basis data dokumen NoSQL menggunakan driver resmi `pymongo` |
| **Frontend Framework** | Webix UI Framework | Framework komponen UI modern berbasis CDN tanpa build tool berat |
| **Styling** | Vanilla CSS (CSS3) | Design system custom, Dark Glassmorphism, Responsive Grid |
| **Tipografi** | Inter & JetBrains Mono | Tipografi modern melalui Google Fonts |
| **Hosting & Deployment** | Vercel | Serverless Functions (`@vercel/python`) & Static Hosting (`@vercel/static`) |
| **Testing** | Python `unittest` | Suite uji regresi transaksi POS & integritas pengurangan stok |

---

## 🗄️ Spesifikasi Skema Database MongoDB

Sistem mengelola 4 koleksi MongoDB utama di database `bookpos`:

1. **`books`**
   - Katalog inventaris toko buku.
   - Field: `isbn` (unik), `judul`, `penulis`, `penerbit`, `kategori_id` (ObjectId), `harga_beli` (integer Rupiah), `harga_jual` (integer Rupiah), `stok` (integer), `aktif` (boolean), `created_at` (ISO datetime), `updated_at` (ISO datetime).
   - Indeks: `isbn` (unique), `judul`, `kategori_id`, `aktif`.

2. **`categories`**
   - Klasifikasi kategori buku toko.
   - Field: `nama`, `slug` (unik).
   - Aturan: Dilarang dihapus apabila masih dirujuk oleh dokumen buku.

3. **`users`**
   - Akun staf kasir dan administrator.
   - Field: `username` (unik), `password_hash` (Werkzeug hash), `nama`, `role` (`admin` / `kasir`), `aktif` (boolean), `created_at`, `updated_at`.
   - Aturan: Pegawai nonaktif tidak dapat login; password tidak pernah dikirim dalam respons API.

4. **`transactions`**
   - Arsip nota transaksi penjualan permanen (*immutable*).
   - Field: `no_faktur` (unik, format `INV-YYYYMMDDHHMM-XXXXXX`), `items` (snapshot data buku saat dibeli: `buku_id`, `isbn`, `judul`, `penulis`, `harga_jual`, `qty`, `subtotal`), `subtotal`, `tarif_pajak`, `pajak`, `total`, `metode_pembayaran`, `tunai_diterima`, `kembalian`, `kasir_nama`, `created_at` (zona waktu WIB).

---

## 📁 Struktur File & Direktori

```
BookPOS/
├── api/
│   ├── __init__.py           # Package marker modul API
│   ├── app.py                # REST API endpoints, logika POS, autentikasi & static routing
│   └── database.py           # Inisialisasi koneksi MongoDB Atlas, failover URI & serialisasi
├── public/
│   ├── index.html            # Halaman Kasir / Point of Sale (Full screen + Pop-up QRIS)
│   ├── master.html           # Halaman Master Data Buku, Kategori & Pegawai
│   ├── laporan.html          # Halaman Laporan Penjualan, KPI & Analitik Omzet
│   ├── login.html            # Halaman Login Staf (Minimalis, Modern Glassmorphism)
│   ├── auth.js               # Handler sesi JWT localStorage & interceptor fetch API
│   ├── pos-helper.js         # Utilitas pemformatan mata uang Rupiah & audio feedback
│   ├── qris-statis.png       # Asset gambar barcode QRIS statis toko
│   └── style.css             # Shared CSS design system, tema POS, dan styling print struk
├── .env.example              # Contoh konfigurasi environment variable
├── .gitignore                # File exclusion Git (mengamankan file .env lokal)
├── requirements.txt          # Daftar dependensi pustaka Python
├── vercel.json               # Konfigurasi routing serverless Vercel
├── uji_checkout.py           # Test suite otomatis (14 unit tests modul transaksi)
├── SkemaUserDanBuku.md       # Dokumentasi rancangan skema database Modul A
└── README.md                 # Dokumentasi panduan teknis & spesifikasi sistem
```

---

## 🚀 Panduan Menjalankan Aplikasi

### 1. Persiapan Lingkungan Lokal
Pastikan Python 3.10+ sudah terinstal di komputer Anda.

```bash
# Clone repository
git clone https://github.com/unidentifiedmeteor/bookPOS.git
cd bookPOS

# Install dependensi Python
pip install -r requirements.txt
```

### 2. Konfigurasi Variabel Lingkungan (`.env`)
Salin file `.env.example` menjadi `.env`:

```env
# MongoDB Atlas Connection String
MONGO_URI=mongodb+srv://<username>:<password>@cluster0.mongodb.net/bookpos?retryWrites=true&w=majority

# Port Flask lokal
PORT=5000

# Kunci Rahasia JWT
JWT_SECRET=super-secret-key-change-me

# Saklar Autentikasi (1 = aktifkan proteksi login)
AUTH_REQUIRED=1

# Tarif Pajak POS (0 = nonaktif, 0.11 = PPN 11%)
TARIF_PAJAK=0
```

### 3. Menjalankan Server Lokal
```bash
python api/app.py
```
Akses aplikasi melalui browser:
- **Kasir / POS:** `http://127.0.0.1:5000/`
- **Master Data:** `http://127.0.0.1:5000/master.html`
- **Laporan Penjualan:** `http://127.0.0.1:5000/laporan.html`
- **Login:** `http://127.0.0.1:5000/login.html`

Akun bawaan (*default seed*):
- **Admin:** `admin` / `admin123`
- **Kasir:** `kasir01` / `kasir123`

### 4. Menjalankan Pengujian Otomatis (Unit Test)
```bash
python -m unittest -v uji_checkout.py
```
Seluruh 14 skenario uji (kalkulasi total, pengurangan stok atomik, proteksi uang kurang, rollback saat gagal, penggabungan item ganda, dan ringkasan transaksi) teruji lulus 100%.

---

## ☁️ Deployment ke Vercel

Aplikasi telah dikonfigurasi penuh untuk deploy ke **Vercel** melalui file [vercel.json](file:///d:/BookPOS/vercel.json):
1. Import repository ke akun Vercel Anda.
2. Tambahkan Environment Variable di Vercel Dashboard (**Settings > Environment Variables**):
   - Key: `MONGO_URI`
   - Value: `mongodb+srv://...` (URI MongoDB Atlas Anda)
3. Pastikan di konsol **MongoDB Atlas > Network Access**, IP telah mengizinkan `0.0.0.0/0` (Allow Access from Anywhere) agar serverless Vercel dapat terhubung.
