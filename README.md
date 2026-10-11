# 📚 BookPOS - Point of Sale & Book Inventory Management System

Aplikasi web Kasir (Point of Sale) dan Manajemen Inventaris Buku yang disesuaikan penuh dengan **Dokumen Desain Skema MongoDB (Modul A: Master Data)** pada [`SkemaUserDanBuku.md`](./SkemaUserDanBuku.md).

---

## 🛠️ Tech Stack

- **Frontend:** [Webix JavaScript UI Framework](https://webix.com/) (Loaded via CDN, tanpa Node.js/NPM)
- **Backend:** Flask (Python 3.12)
- **Database:** MongoDB Atlas (via `pymongo` + `certifi`)
- **Deployment:** Vercel (Serverless Functions untuk Flask, Static Hosting untuk Webix)

---

## 📁 Struktur Proyek (Vercel Monorepo)

```
BookPOS/
├── api/                    # Backend (Flask Serverless Functions)
│   ├── app.py              # Main API routes, business rules & static server
│   └── database.py         # MongoDB Atlas connection, indexes & serialization
├── public/                 # Frontend (Webix)
│   ├── index.html          # POS / UI Kasir
│   ├── master.html         # UI Master Data Buku, Kategori & Pegawai
│   └── style.css           # Styling kustom, badge status & cetak struk thermal
├── .env                    # String MONGO_URI
├── requirements.txt        # Flask, pymongo[srv], python-dotenv, flask-cors
├── vercel.json             # Konfigurasi routing Vercel
├── SkemaUserDanBuku.md     # Spesifikasi desain skema dokumen MongoDB
└── README.md               # Dokumentasi
```

---

## 📋 Implementasi Skema MongoDB Sesuai `SkemaUserDanBuku.md`

### 1. Koleksi `books`
- **Field Kamus Data:** `isbn` (unik, ISBN-13 tanpa tanda hubung), `judul`, `penulis`, `penerbit`, `kategori_id` (ObjectId rujukan ke `categories`), `harga_beli` (integer Rupiah), `harga_jual` (integer Rupiah), `stok` (integer), `aktif` (boolean, soft delete), `created_at`, `updated_at`.
- **Soft Delete:** Penghapusan buku mengubah `aktif: false` sehingga riwayat transaksi tetap terjaga. UI menampilkan peringatan jika `stok > 0`. Buku nonaktif dapat diaktifkan kembali.
- **Validasi ISBN Unik:** Format ISBN dinormalisasi di server (menghapus tanda hubung/spasi). Menambah buku baru dengan ISBN yang pernah dinonaktifkan akan menampilkan notifikasi opsi reaktivasi (HTTP 409 `can_restore`).
- **Integritas Stok:** Stok **tidak ditimpa** saat edit data buku; penyesuaian stok dilakukan via modul penyesuaian tersendiri, dan pengurangan stok terjadi atomik saat transaksi kasir.

### 2. Koleksi `categories`
- **Field Kamus Data:** `nama`, `slug` (unik, huruf kecil, tanpa spasi).
- **Data Awal (Seeded):** Fiksi, Non-Fiksi, Pelajaran, Komik.
- **Proteksi Hapus Kategori:** Kategori **dilarang dihapus** selama masih dirujuk oleh buku apa pun (baik buku aktif maupun nonaktif) untuk mencegah rujukan yatim.

### 3. Koleksi `users`
- **Field Kamus Data:** `username` (unik, huruf kecil), `password_hash` (dihash dengan Werkzeug security, tidak pernah dikirim balik oleh API), `nama`, `role` (`admin` / `kasir`), `aktif` (boolean), `created_at`, `updated_at`.
- **Pegawai Dinonaktifkan (Bukan Dihapus):** Pegawai yang keluar dinonaktifkan (`aktif: false`), agar riwayat transaksi tetap valid.
- **Akun Bawaan (Seeded):**
  - **Admin:** Username: `admin` | Password: `admin123`
  - **Kasir:** Username: `kasir01` | Password: `kasir123`

---

## 🚀 Panduan Menjalankan Lokal

1. **Konfigurasi MongoDB Atlas** pada [`.env`](file:///.env):
   ```env
   MONGO_URI=mongodb+srv://<username>:<password>@cluster0.mongodb.net/bookpos?retryWrites=true&w=majority
   ```
   > *Catatan:* Jika `MONGO_URI` belum diisi, aplikasi otomatis berjalan dalam **Demo Mode (In-Memory)** sehingga seluruh alur POS kasir, master buku, kategori, pegawai, dan cetak struk dapat langsung dicoba tanpa hambatan!

2. **Jalankan Server Flask:**
   ```bash
   python api/app.py
   ```

3. **Buka Browser:**
   - **Kasir (POS):** [http://127.0.0.1:5000/](http://127.0.0.1:5000/)
   - **Master Data Buku & Inventaris:** [http://127.0.0.1:5000/master.html](http://127.0.0.1:5000/master.html)
   - **Status API:** [http://127.0.0.1:5000/api/health](http://127.0.0.1:5000/api/health)

---

## ☁️ Deployment ke Vercel

Cukup jalankan Vercel CLI:
```bash
vercel
```
Tambahkan environment variable `MONGO_URI` di Vercel Dashboard (**Project Settings > Environment Variables**).
