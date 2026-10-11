# Desain Skema Dokumen MongoDB: Modul A (Master Data) dan Modul Transaksi

Database: `nanti namanya` | Koleksi: `books`, `categories`, `users`, `transactions`

## 1. Koleksi `books`

Satu dokumen = satu judul buku. Jumlah eksemplar disimpan di field `stok`, bukan satu dokumen per eksemplar.

### Kamus Data
| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| _id | ObjectId | otomatis | primary key internal, dibuat MongoDB |
| isbn | string | ya | unik (termasuk buku nonaktif); ISBN-13 tanpa tanda hubung |
| judul | string | ya | |
| penulis | string | ya | |
| penerbit | string | tidak | |
| kategori_id | ObjectId | ya | rujukan ke `categories._id` |
| harga_beli | integer | ya | rupiah, tanpa desimal, minimal 0 |
| harga_jual | integer | ya | rupiah, tanpa desimal, minimal 0 |
| stok | integer | ya | minimal 0 |
| aktif | boolean | ya | default `true`; `false` = dihapus (soft delete) |
| created_at | datetime | ya | diisi server saat dibuat |
| updated_at | datetime | ya | diisi server tiap perubahan |

### Contoh Struktur Dokumen
```json
{
  "_id": "665f1c2e8a1b2c3d4e5f6a01",
  "isbn": "9786020000001",
  "judul": "Laskar Pelangi",
  "penulis": "Andrea Hirata",
  "penerbit": "Bentang Pustaka",
  "kategori_id": "665f0a1b8a1b2c3d4e5f6a10",
  "harga_beli": 60000,
  "harga_jual": 85000,
  "stok": 24,
  "aktif": true,
  "created_at": "2026-10-11T09:00:00Z",
  "updated_at": "2026-10-11T09:00:00Z"
}
```

### Index
| Field | Jenis | Tujuan |
|---|---|---|
| isbn | unik | mencegah buku ganda, pencarian ISBN cepat |
| judul | biasa | pencarian dan pengurutan judul |
| kategori_id | biasa | filter per kategori |

### Keputusan

**ISBN wajib dan unik.** Dipakai kasir untuk pencarian dan pemindaian barcode. Format diseragamkan di server sebelum disimpan, supaya penulisan berbeda tidak lolos sebagai buku ganda. Keunikan dijaga oleh unique index di database, bukan hanya oleh pengecekan di kode.

**Harga integer.** Menghindari kesalahan pembulatan pada angka desimal.

**Kategori lewat id.** Nama kategori bisa diubah tanpa menyentuh ribuan dokumen buku.

**Soft delete untuk buku (`aktif`).**
Alasan:
1. Menjaga riwayat transaksi: struk dan laporan dapat merujuk ke buku yang pernah terjual, dan rujukannya tidak putus.
2. Bisa dibatalkan: penghapusan yang keliru dapat diaktifkan kembali.
3. Tidak bergantung pada desain penyimpanan struk di modul lain.
4. Konsisten dengan `users` (pegawai dinonaktifkan, bukan dihapus).

Aturan turunan:
- Buku dengan `stok` > 0 boleh dinonaktifkan; UI menampilkan peringatan sebelum konfirmasi.
- Buku nonaktif dapat diaktifkan kembali (tombol Aktifkan / filter "tampilkan yang dihapus"). ISBN tetap terpakai selama dokumen ada, sehingga menambah buku dengan ISBN nonaktif menampilkan pesan "Buku ini pernah dihapus, aktifkan kembali?".
- Semua daftar dan pencarian menyaring `aktif: true` secara default. Filter ini ditulis di satu fungsi pengambil data, tidak disalin per endpoint.

**`stok` tidak boleh ditimpa oleh edit data buku.** Pengurangan stok karena penjualan dilakukan secara atomik oleh modul transaksi.

## 2. Koleksi `categories`

### Kamus Data
| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| _id | ObjectId | otomatis | |
| nama | string | ya | |
| slug | string | ya | unik, huruf kecil, tanpa spasi |

### Contoh Struktur Dokumen
```json
{
  "_id": "665f0a1b8a1b2c3d4e5f6a10",
  "nama": "Fiksi",
  "slug": "fiksi"
}
```

Data awal: Fiksi, Non-Fiksi, Pelajaran, Komik.

### Keputusan
Kategori **dilarang dihapus** selama masih dirujuk oleh buku, termasuk buku nonaktif. Alasan: buku nonaktif tetap menyimpan `kategori_id`, dan menghapus kategorinya akan meninggalkan rujukan yatim. Penghapusan baru diizinkan kalau tidak ada satu pun buku (aktif maupun nonaktif) yang merujuknya.

## 3. Koleksi `users`

### Kamus Data
| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| _id | ObjectId | otomatis | |
| username | string | ya | unik, huruf kecil |
| password_hash | string | ya | hasil hashing; tidak pernah dikirim balik oleh API |
| nama | string | ya | nama pegawai |
| role | string | ya | `admin` atau `kasir` |
| aktif | boolean | ya | `false` = tidak bisa login |
| created_at | datetime | ya | |
| updated_at | datetime | ya | |

### Contoh Struktur Dokumen
```json
{
  "_id": "665f2d4f8a1b2c3d4e5f6b02",
  "username": "kasir01",
  "password_hash": "<hash, bukan password asli>",
  "nama": "Budi Santoso",
  "role": "kasir",
  "aktif": true,
  "created_at": "2026-10-11T09:00:00Z",
  "updated_at": "2026-10-11T09:00:00Z"
}
```

### Index
| Field | Jenis | Tujuan |
|---|---|---|
| username | unik | mencegah akun ganda, pencarian saat login |

### Keputusan
- Password disimpan sebagai hash, tidak pernah sebagai teks asli.
- Pegawai yang keluar dinonaktifkan (`aktif: false`), bukan dihapus, supaya riwayat transaksi tetap merujuk ke user yang valid.
- Tidak ada registrasi publik: akun dibuat oleh Admin. Admin pertama dibuat lewat script seed yang dijalankan sekali.

## 4. Koleksi `transactions`

Satu dokumen = satu nota penjualan. Dokumen tidak pernah diubah atau dihapus setelah dibuat, karena menjadi arsip penjualan.

### Kamus Data
| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| _id | ObjectId | otomatis | |
| no_faktur | string | ya | format `INV-YYYYMMDDHHMM-XXXXXX`, unik |
| items | array | ya | salinan data buku saat dijual (lihat di bawah) |
| subtotal | integer | ya | jumlah harga seluruh item, rupiah |
| tarif_pajak | number | ya | tarif saat transaksi, mis. `0.11`; `0` jika tanpa pajak |
| pajak | integer | ya | dibulatkan ke rupiah, dihitung server |
| total | integer | ya | `subtotal + pajak` |
| metode_pembayaran | string | ya | `tunai`, `qris`, atau `debit` |
| tunai_diterima | integer | ya | untuk non-tunai sama dengan `total` |
| kembalian | integer | ya | `0` untuk non-tunai |
| kasir_nama | string | ya | diambil dari token login |
| created_at | string | ya | ISO 8601 zona WIB (+07:00) |

Setiap elemen `items`:
| Field | Tipe | Keterangan |
|---|---|---|
| buku_id | string | rujukan ke `books._id` |
| isbn | string | salinan saat dijual |
| judul | string | salinan saat dijual |
| penulis | string | salinan saat dijual |
| harga_jual | integer | harga satuan saat dijual |
| qty | integer | minimal 1 |
| subtotal | integer | `harga_jual * qty` |

### Contoh Struktur Dokumen
```json
{
  "_id": "665f3e5a8a1b2c3d4e5f6c03",
  "no_faktur": "INV-202610112145-A1B2C3",
  "items": [
    {
      "buku_id": "665f1c2e8a1b2c3d4e5f6a01",
      "isbn": "9786020000001",
      "judul": "Laskar Pelangi",
      "penulis": "Andrea Hirata",
      "harga_jual": 85000,
      "qty": 2,
      "subtotal": 170000
    }
  ],
  "subtotal": 170000,
  "tarif_pajak": 0,
  "pajak": 0,
  "total": 170000,
  "metode_pembayaran": "tunai",
  "tunai_diterima": 200000,
  "kembalian": 30000,
  "kasir_nama": "kasir01",
  "created_at": "2026-10-11T21:45:00+07:00"
}
```

### Index (disarankan, dibuat manual di Atlas)
| Field | Jenis | Tujuan |
|---|---|---|
| no_faktur | unik | pencarian nota, mencegah nomor ganda |
| created_at | biasa | laporan per rentang tanggal dan urutan terbaru |

### Keputusan
- Harga selalu diambil dari koleksi `books` saat checkout, bukan dari klien.
- Item dengan buku yang sama digabung menjadi satu baris.
- Pajak, total, dan kembalian dihitung di server; angka dari klien tidak dipercaya.
- Stok dikurangi secara atomik (`stok >= qty`). Jika penyimpanan nota gagal, stok dikembalikan.
- Judul, penulis, dan harga disalin ke nota agar riwayat tetap benar walau buku kemudian diedit atau dinonaktifkan.
- `created_at` memakai zona WIB agar laporan harian sesuai hari kerja toko.