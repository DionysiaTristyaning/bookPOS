import copy
import os
import unittest
from datetime import date

os.environ["AUTH_REQUIRED"] = "0"
os.environ.setdefault("JWT_SECRET", "rahasia-untuk-uji")

import api.app as m

m.is_live_db = lambda: False

BUKU_ASLI = copy.deepcopy(m._in_memory_books)


class UjiCheckout(unittest.TestCase):
    def setUp(self):
        m._in_memory_books[:] = copy.deepcopy(BUKU_ASLI)
        m._in_memory_transactions[:] = []
        m.TARIF_PAJAK = 0
        self.client = m.app.test_client()

    def stok(self, book_id):
        return next(b for b in m._in_memory_books if b["id"] == book_id)["stok"]

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