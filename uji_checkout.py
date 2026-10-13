import copy
import os
import unittest
from datetime import date

os.environ["AUTH_REQUIRED"] = "0"
os.environ.setdefault("JWT_SECRET", "rahasia-untuk-uji")

import api.app as m

MOCK_BOOKS_INIT = [
    {
        "id": "book-1",
        "judul": "Laskar Pelangi",
        "pengarang": "Andrea Hirata",
        "penerbit": "Bentang Pustaka",
        "tahun_terbit": 2005,
        "kategori": "Fiksi",
        "isbn": "9786020000001",
        "harga_beli": 60000,
        "harga_jual": 85000,
        "stok": 24,
        "aktif": True,
    },
    {
        "id": "book-7",
        "judul": "Habis Gelap Terbitlah Terang",
        "pengarang": "R.A. Kartini",
        "penerbit": "Balai Pustaka",
        "tahun_terbit": 1922,
        "kategori": "Sejarah",
        "isbn": "9786020000007",
        "harga_beli": 35000,
        "harga_jual": 50000,
        "stok": 0,
        "aktif": True,
    },
    {
        "id": "book-8",
        "judul": "Arsip Arsip Lama",
        "pengarang": "Anonim",
        "penerbit": "Arsip Nasional",
        "tahun_terbit": 1950,
        "kategori": "Arsip",
        "isbn": "9786020000008",
        "harga_beli": 10000,
        "harga_jual": 15000,
        "stok": 5,
        "aktif": False,
    },
]


class UpdateResult:
    def __init__(self, count):
        self.modified_count = count


class InsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class MockCollection:
    def __init__(self, data=None):
        self.docs = copy.deepcopy(data or [])

    def find_one(self, filt):
        for doc in self.docs:
            match = True
            for k, v in filt.items():
                if isinstance(v, dict):
                    if "$gte" in v and doc.get(k, 0) < v["$gte"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                return copy.deepcopy(doc)
        return None

    def update_one(self, filt, update):
        for doc in self.docs:
            match = True
            for k, v in filt.items():
                if isinstance(v, dict):
                    if "$gte" in v and doc.get(k, 0) < v["$gte"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                if "$inc" in update:
                    for ik, iv in update["$inc"].items():
                        doc[ik] = doc.get(ik, 0) + iv
                if "$set" in update:
                    for sk, sv in update["$set"].items():
                        doc[sk] = sv
                return UpdateResult(1)
        return UpdateResult(0)

    def insert_one(self, doc):
        new_id = f"mock-id-{len(self.docs)+1}"
        self.docs.append(copy.deepcopy(doc))
        return InsertResult(new_id)

    def find(self, filt=None):
        return [copy.deepcopy(d) for d in self.docs]


class MockDB:
    def __init__(self):
        self.books = MockCollection(MOCK_BOOKS_INIT)
        self.transactions = MockCollection([])


mock_db_instance = MockDB()
m.is_live_db = lambda: True
m.get_db = lambda: mock_db_instance


class UjiCheckout(unittest.TestCase):
    def setUp(self):
        mock_db_instance.books = MockCollection(MOCK_BOOKS_INIT)
        mock_db_instance.transactions = MockCollection([])
        m.TARIF_PAJAK = 0
        self.client = m.app.test_client()

    def stok(self, book_id):
        b = mock_db_instance.books.find_one({"id": book_id})
        return b["stok"] if b else None

    def kirim(self, items, tunai=1000000, metode="tunai"):
        return self.client.post("/api/checkout", json={
            "items": items,
            "tunai_diterima": tunai,
            "metode_pembayaran": metode,
        })

    def test_sukses_dan_kembalian(self):
        res = self.kirim([{"id": "book-1", "qty": 2}], tunai=200000)
        self.assertEqual(res.status_code, 201)
        tx = res.get_json()["transaction"]
        self.assertEqual(tx["total"], 170000)
        self.assertEqual(tx["kembalian"], 30000)
        self.assertEqual(self.stok("book-1"), 22)

    def test_harga_dari_klien_diabaikan(self):
        res = self.kirim([{"id": "book-1", "qty": 1, "harga_jual": 1}])
        self.assertEqual(res.get_json()["transaction"]["total"], 85000)

    def test_item_ganda_digabung(self):
        res = self.kirim([{"id": "book-1", "qty": 1}, {"id": "book-1", "qty": 2}])
        items = res.get_json()["transaction"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["qty"], 3)

    def test_stok_kurang_ditolak(self):
        res = self.kirim([{"id": "book-7", "qty": 1}])
        self.assertEqual(res.status_code, 400)

    def test_buku_nonaktif_ditolak(self):
        res = self.kirim([{"id": "book-8", "qty": 1}])
        self.assertEqual(res.status_code, 400)

    def test_tunai_kurang_stok_tetap(self):
        res = self.kirim([{"id": "book-1", "qty": 1}], tunai=1000)
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.stok("book-1"), 24)

    def test_kartu_nominal_kurang_ditolak(self):
        res = self.kirim([{"id": "book-1", "qty": 1}], tunai=1000, metode="kartu")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.stok("book-1"), 24)

    def test_qris_nominal_kurang_ditolak(self):
        res = self.kirim([{"id": "book-1", "qty": 1}], tunai=50000, metode="qris")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.stok("book-1"), 24)

    def test_kartu_uang_pas_berhasil(self):
        res = self.kirim([{"id": "book-1", "qty": 1}], tunai=85000, metode="kartu")
        self.assertEqual(res.status_code, 201)
        tx = res.get_json()["transaction"]
        self.assertEqual(tx["total"], 85000)
        self.assertEqual(tx["kembalian"], 0)

    def test_tunai_string_nominal_kurang_ditolak(self):
        res = self.kirim([{"id": "book-1", "qty": 1}], tunai="50.000", metode="tunai")
        self.assertEqual(res.status_code, 400)
        self.assertIn("kurang", res.get_json()["error"])

    def test_keranjang_kosong(self):
        self.assertEqual(self.kirim([]).status_code, 400)

    def test_pajak_dihitung_server(self):
        m.TARIF_PAJAK = 0.11
        tx = self.kirim([{"id": "book-1", "qty": 1}]).get_json()["transaction"]
        self.assertEqual(tx["pajak"], 9350)
        self.assertEqual(tx["total"], 94350)

    def test_rollback_jika_simpan_gagal(self):
        asli = m._simpan_transaksi

        def rusak(doc):
            raise RuntimeError("simulasi gagal")

        m._simpan_transaksi = rusak
        try:
            res = self.kirim([{"id": "book-1", "qty": 2}])
        finally:
            m._simpan_transaksi = asli
        self.assertEqual(res.status_code, 500)
        self.assertEqual(self.stok("book-1"), 24)

    def test_rangkum_transaksi(self):
        hari = date(2026, 10, 11)
        transaksi = [{
            "created_at": "2026-10-11T10:00:00+07:00",
            "metode_pembayaran": "tunai",
            "subtotal": 170000,
            "pajak": 0,
            "total": 170000,
            "kasir_nama": "kasir01",
            "no_faktur": "INV-1",
            "items": [{
                "isbn": "9786020000001",
                "judul": "Laskar Pelangi",
                "qty": 2,
                "subtotal": 170000,
            }],
        }]
        hasil = m.rangkum_transaksi(transaksi, hari, hari)
        self.assertEqual(hasil["ringkasan"]["total"], 170000)
        self.assertEqual(hasil["ringkasan"]["buku_terjual"], 2)
        self.assertEqual(hasil["terlaris"][0]["judul"], "Laskar Pelangi")


if __name__ == "__main__":
    unittest.main(verbosity=2)