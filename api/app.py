import os
import sys
import re
import uuid
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from flask import Flask, request, jsonify, send_from_directory, Blueprint
from flask_cors import CORS
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, timezone
import jwt

# Ensure project root is in sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
API_DIR = os.path.dirname(__file__)
if API_DIR not in sys.path:
    sys.path.insert(0, API_DIR)

try:
    from api.database import (
        get_db,
        get_connection_status,
        serialize_doc,
        serialize_docs,
        normalize_isbn,
        slugify
    )
except ImportError:
    from database import (
        get_db,
        get_connection_status,
        serialize_doc,
        serialize_docs,
        normalize_isbn,
        slugify
    )

app = Flask(__name__)
CORS(app)

# ----------------- IN-MEMORY FALLBACK STORE -----------------
# Digunakan saat MongoDB Atlas belum dikonfigurasi / offline untuk testing langsung
_in_memory_categories = [
    {"id": "cat-1", "nama": "Fiksi", "slug": "fiksi"},
    {"id": "cat-2", "nama": "Non-Fiksi", "slug": "non-fiksi"},
    {"id": "cat-3", "nama": "Pelajaran", "slug": "pelajaran"},
    {"id": "cat-4", "nama": "Komik", "slug": "komik"}
]

_in_memory_users = [
    {
        "id": "usr-1",
        "username": "admin",
        "password_hash": generate_password_hash("admin123"),
        "nama": "Administrator",
        "role": "admin",
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    },
    {
        "id": "usr-2",
        "username": "kasir01",
        "password_hash": generate_password_hash("kasir123"),
        "nama": "Budi Santoso",
        "role": "kasir",
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
]

_in_memory_books = [
    {
        "id": "book-1",
        "isbn": "9786020000001",
        "judul": "Laskar Pelangi",
        "penulis": "Andrea Hirata",
        "penerbit": "Bentang Pustaka",
        "kategori_id": "cat-1",
        "harga_beli": 60000,
        "harga_jual": 85000,
        "stok": 24,
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    },
    {
        "id": "book-2",
        "isbn": "9789799731234",
        "judul": "Bumi Manusia",
        "penulis": "Pramoedya Ananta Toer",
        "penerbit": "Hasta Mitra",
        "kategori_id": "cat-1",
        "harga_beli": 75000,
        "harga_jual": 105000,
        "stok": 15,
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    },
    {
        "id": "book-3",
        "isbn": "9786020385914",
        "judul": "Filosofi Teras",
        "penulis": "Henry Manampiring",
        "penerbit": "Penerbit Buku Kompas",
        "kategori_id": "cat-2",
        "harga_beli": 70000,
        "harga_jual": 98000,
        "stok": 18,
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    },
    {
        "id": "book-4",
        "isbn": "9786020633176",
        "judul": "Atomic Habits (Edisi Indonesia)",
        "penulis": "James Clear",
        "penerbit": "Gramedia Pustaka Utama",
        "kategori_id": "cat-2",
        "harga_beli": 85000,
        "harga_jual": 118000,
        "stok": 30,
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    },
    {
        "id": "book-5",
        "isbn": "9786024246945",
        "judul": "Laut Bercerita",
        "penulis": "Leila S. Chudori",
        "penerbit": "KPG",
        "kategori_id": "cat-1",
        "harga_beli": 72000,
        "harga_jual": 100000,
        "stok": 4,
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    },
    {
        "id": "book-6",
        "isbn": "9786020478123",
        "judul": "Detektif Conan Vol 100",
        "penulis": "Gosho Aoyama",
        "penerbit": "Elex Media Komputindo",
        "kategori_id": "cat-4",
        "harga_beli": 25000,
        "harga_jual": 35000,
        "stok": 2,
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    },
    {
        "id": "book-7",
        "isbn": "9786022987654",
        "judul": "Matematika SMA Kelas 12",
        "penulis": "Sukino",
        "penerbit": "Erlangga",
        "kategori_id": "cat-3",
        "harga_beli": 55000,
        "harga_jual": 78000,
        "stok": 0,
        "aktif": True,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    },
    {
        "id": "book-8",
        "isbn": "9786020000099",
        "judul": "Buku Arsip Terhapus (Contoh Nonaktif)",
        "penulis": "Penulis Nonaktif",
        "penerbit": "Pustaka Lama",
        "kategori_id": "cat-1",
        "harga_beli": 30000,
        "harga_jual": 45000,
        "stok": 5,
        "aktif": False,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }
]

_in_memory_transactions = []

# Blueprint API
api_bp = Blueprint("api_bp", __name__)

JWT_SECRET = os.getenv("JWT_SECRET", "bookpos-default-jwt-secret-key-change-in-prod")

def get_auth_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        return jwt.decode(header[7:], JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None

def create_token(user):
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=int(os.getenv("JWT_EXPIRES_HOURS", "8"))),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def check_auth(*roles):
    """Mengembalikan None kalau boleh, atau respons error kalau ditolak."""
    if os.getenv("AUTH_REQUIRED") != "1":
        return None  # saklar mati: perilaku lama
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return jsonify({"error": "Login diperlukan"}), 401
    try:
        payload = jwt.decode(header[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return jsonify({"error": "Token tidak valid atau kedaluwarsa"}), 401
    if roles and payload.get("role") not in roles:
        return jsonify({"error": "Akses ditolak"}), 403
    return None

def is_live_db():
    status = get_connection_status()
    return status.get("connected", False)

def parse_int_safe(val, default=0):
    """Sanitasi integer rupiah: menangani int, float, atau string dengan titik ribuan."""
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        return int(val)
    cleaned = re.sub(r"[^\d]", "", str(val).strip())
    return int(cleaned) if cleaned else default

# ----------------- KATEGORI MAPPING HELPER -----------------
def get_categories_map():
    if is_live_db():
        db = get_db()
        cats = list(db.categories.find())
        return {str(c["_id"]): c["nama"] for c in cats}
    else:
        return {c["id"]: c["nama"] for c in _in_memory_categories}

# ----------------- CENTRALIZED BOOK QUERY HELPER -----------------
# Sesuai Aturan 68: "Semua daftar dan pencarian menyaring aktif: true secara default.
# Filter ini ditulis di satu fungsi pengambil data, tidak disalin per endpoint."
def query_books(search="", kategori_id="", status="aktif", stock_status=""):
    cat_map = get_categories_map()
    
    if is_live_db():
        db = get_db()
        query = {}
        
        # Filter status aktif (default: aktif: True)
        if status == "aktif":
            query["aktif"] = True
        elif status == "nonaktif":
            query["aktif"] = False
        # status == "semua" -> tidak memfilter field aktif
        
        if search:
            norm_s = normalize_isbn(search)
            regex_pat = re.compile(re.escape(search), re.IGNORECASE)
            search_conditions = [
                {"judul": {"$regex": regex_pat}},
                {"penulis": {"$regex": regex_pat}},
                {"penerbit": {"$regex": regex_pat}}
            ]
            if norm_s:
                search_conditions.append({"isbn": {"$regex": re.compile(re.escape(norm_s))}})
            query["$or"] = search_conditions
            
        if kategori_id and kategori_id != "all":
            try:
                query["kategori_id"] = ObjectId(kategori_id)
            except Exception:
                query["kategori_id"] = kategori_id
                
        if stock_status == "low":
            query["stok"] = {"$gt": 0, "$lte": 5}
        elif stock_status == "out":
            query["stok"] = 0
        elif stock_status == "in":
            query["stok"] = {"$gt": 0}

        docs = list(db.books.find(query).sort("judul", 1))
        serialized = serialize_docs(docs)
        for b in serialized:
            b["kategori_nama"] = cat_map.get(str(b.get("kategori_id")), "Kategori Tidak Diketahui")
        return serialized
    else:
        # Fallback In-Memory
        results = list(_in_memory_books)
        if status == "aktif":
            results = [b for b in results if b.get("aktif") is True]
        elif status == "nonaktif":
            results = [b for b in results if b.get("aktif") is False]
            
        if search:
            s_lower = search.lower()
            norm_s = normalize_isbn(search)
            results = [
                b for b in results
                if s_lower in b.get("judul", "").lower()
                or s_lower in b.get("penulis", "").lower()
                or s_lower in b.get("penerbit", "").lower()
                or (norm_s and norm_s in b.get("isbn", ""))
            ]
            
        if kategori_id and kategori_id != "all":
            results = [b for b in results if str(b.get("kategori_id")) == str(kategori_id)]
            
        if stock_status == "low":
            results = [b for b in results if 0 < b.get("stok", 0) <= 5]
        elif stock_status == "out":
            results = [b for b in results if b.get("stok", 0) == 0]
        elif stock_status == "in":
            results = [b for b in results if b.get("stok", 0) > 0]
            
        results.sort(key=lambda x: x.get("judul", ""))
        for b in results:
            b["kategori_nama"] = cat_map.get(str(b.get("kategori_id")), "Kategori Tidak Diketahui")
        return results

# ----------------- HEALTH CHECK -----------------
@api_bp.route("/health", methods=["GET"])
def health():
    status = get_connection_status()
    db = get_db() if status["connected"] else None
    book_count = 0
    if db is not None:
        try:
            book_count = db.books.count_documents({"aktif": True})
        except Exception:
            book_count = 0
    else:
        book_count = len([b for b in _in_memory_books if b.get("aktif") is True])

    return jsonify({
        "status": "ok",
        "database_connected": status["connected"],
        "database_mode": "MongoDB Atlas" if status["connected"] else "In-Memory Demo Fallback",
        "database_name": status.get("database"),
        "error": status.get("error"),
        "total_buku_aktif": book_count,
        "timestamp": datetime.now().isoformat()
    })

# ----------------- SEED DATA -----------------
@api_bp.route("/seed", methods=["POST"])
def seed_data():
    if is_live_db():
        db = get_db()
        
        # 1. Seed Categories (Fiksi, Non-Fiksi, Pelajaran, Komik)
        default_categories = [
            {"nama": "Fiksi", "slug": "fiksi"},
            {"nama": "Non-Fiksi", "slug": "non-fiksi"},
            {"nama": "Pelajaran", "slug": "pelajaran"},
            {"nama": "Komik", "slug": "komik"}
        ]
        cat_ids = {}
        for c in default_categories:
            existing = db.categories.find_one({"slug": c["slug"]})
            if not existing:
                res = db.categories.insert_one(c)
                cat_ids[c["slug"]] = res.inserted_id
            else:
                cat_ids[c["slug"]] = existing["_id"]

        # 2. Seed Users (admin, kasir01)
        default_users = [
            {
                "username": "admin",
                "password_hash": generate_password_hash("admin123"),
                "nama": "Administrator Toko",
                "role": "admin",
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "username": "kasir01",
                "password_hash": generate_password_hash("kasir123"),
                "nama": "Budi Santoso",
                "role": "kasir",
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        ]
        for u in default_users:
            if not db.users.find_one({"username": u["username"]}):
                db.users.insert_one(u)

        # 3. Seed Books
        sample_books = [
            {
                "isbn": "9786020000001",
                "judul": "Laskar Pelangi",
                "penulis": "Andrea Hirata",
                "penerbit": "Bentang Pustaka",
                "kategori_id": cat_ids.get("fiksi"),
                "harga_beli": 60000,
                "harga_jual": 85000,
                "stok": 24,
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "isbn": "9789799731234",
                "judul": "Bumi Manusia",
                "penulis": "Pramoedya Ananta Toer",
                "penerbit": "Hasta Mitra",
                "kategori_id": cat_ids.get("fiksi"),
                "harga_beli": 75000,
                "harga_jual": 105000,
                "stok": 15,
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "isbn": "9786020385914",
                "judul": "Filosofi Teras",
                "penulis": "Henry Manampiring",
                "penerbit": "Penerbit Buku Kompas",
                "kategori_id": cat_ids.get("non-fiksi"),
                "harga_beli": 70000,
                "harga_jual": 98000,
                "stok": 18,
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "isbn": "9786020633176",
                "judul": "Atomic Habits (Edisi Indonesia)",
                "penulis": "James Clear",
                "penerbit": "Gramedia Pustaka Utama",
                "kategori_id": cat_ids.get("non-fiksi"),
                "harga_beli": 85000,
                "harga_jual": 118000,
                "stok": 30,
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "isbn": "9786024246945",
                "judul": "Laut Bercerita",
                "penulis": "Leila S. Chudori",
                "penerbit": "KPG",
                "kategori_id": cat_ids.get("fiksi"),
                "harga_beli": 72000,
                "harga_jual": 100000,
                "stok": 4,
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "isbn": "9786020478123",
                "judul": "Detektif Conan Vol 100",
                "penulis": "Gosho Aoyama",
                "penerbit": "Elex Media Komputindo",
                "kategori_id": cat_ids.get("komik"),
                "harga_beli": 25000,
                "harga_jual": 35000,
                "stok": 2,
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            },
            {
                "isbn": "9786022987654",
                "judul": "Matematika SMA Kelas 12",
                "penulis": "Sukino",
                "penerbit": "Erlangga",
                "kategori_id": cat_ids.get("pelajaran"),
                "harga_beli": 55000,
                "harga_jual": 78000,
                "stok": 0,
                "aktif": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
        ]
        inserted = 0
        for b in sample_books:
            if not db.books.find_one({"isbn": b["isbn"]}):
                db.books.insert_one(b)
                inserted += 1

        return jsonify({"success": True, "message": f"Berhasil seed {inserted} buku dan master kategori/user ke MongoDB Atlas."})
    else:
        return jsonify({"success": True, "message": "Demo data siap dalam memori."})

# ----------------- KOLEKSI: CATEGORIES -----------------
@api_bp.route("/categories", methods=["GET"])
def get_categories():
    denied = check_auth()
    if denied:
        return denied

    if is_live_db():
        db = get_db()
        cats = list(db.categories.find().sort("nama", 1))
        # Tambahkan jumlah buku per kategori
        serialized = serialize_docs(cats)
        for c in serialized:
            try:
                oid = ObjectId(c["id"])
                c["total_buku"] = db.books.count_documents({"kategori_id": oid})
            except Exception:
                c["total_buku"] = 0
        return jsonify(serialized)
    else:
        res = []
        for c in _in_memory_categories:
            c_copy = dict(c)
            c_copy["total_buku"] = len([b for b in _in_memory_books if b.get("kategori_id") == c["id"]])
            res.append(c_copy)
        return jsonify(res)

@api_bp.route("/categories", methods=["POST"])
def create_category():
    denied = check_auth("admin")
    if denied:
        return denied

    data = request.get_json() or {}
    nama = str(data.get("nama", "")).strip()
    if not nama:
        return jsonify({"error": "Nama kategori wajib diisi"}), 400

    slug = slugify(data.get("slug") or nama)
    if not slug:
        return jsonify({"error": "Slug tidak valid"}), 400

    new_cat = {"nama": nama, "slug": slug}

    if is_live_db():
        db = get_db()
        if db.categories.find_one({"slug": slug}):
            return jsonify({"error": f"Kategori dengan slug '{slug}' sudah ada"}), 400
        res = db.categories.insert_one(new_cat)
        new_cat["id"] = str(res.inserted_id)
        if "_id" in new_cat:
            del new_cat["_id"]
        return jsonify(new_cat), 201
    else:
        if any(c["slug"] == slug for c in _in_memory_categories):
            return jsonify({"error": f"Kategori dengan slug '{slug}' sudah ada"}), 400
        new_cat["id"] = f"cat-{len(_in_memory_categories) + 1}"
        _in_memory_categories.append(new_cat)
        return jsonify(new_cat), 201

@api_bp.route("/categories/<cat_id>", methods=["PUT"])
def update_category(cat_id):
    denied = check_auth("admin")
    if denied:
        return denied
        
    data = request.get_json() or {}
    nama = str(data.get("nama", "")).strip()
    if not nama:
        return jsonify({"error": "Nama kategori wajib diisi"}), 400

    slug = slugify(data.get("slug") or nama)

    if is_live_db():
        db = get_db()
        try:
            oid = ObjectId(cat_id)
        except Exception:
            return jsonify({"error": "ID kategori tidak valid"}), 400

        dup = db.categories.find_one({"slug": slug, "_id": {"$ne": oid}})
        if dup:
            return jsonify({"error": f"Slug '{slug}' sudah digunakan oleh kategori lain"}), 400

        res = db.categories.update_one({"_id": oid}, {"$set": {"nama": nama, "slug": slug}})
        if res.matched_count == 0:
            return jsonify({"error": "Kategori tidak ditemukan"}), 404
        updated = db.categories.find_one({"_id": oid})
        return jsonify(serialize_doc(updated))
    else:
        cat = next((c for c in _in_memory_categories if c["id"] == cat_id), None)
        if not cat:
            return jsonify({"error": "Kategori tidak ditemukan"}), 404
        if any(c["slug"] == slug and c["id"] != cat_id for c in _in_memory_categories):
            return jsonify({"error": f"Slug '{slug}' sudah digunakan oleh kategori lain"}), 400
        cat["nama"] = nama
        cat["slug"] = slug
        return jsonify(cat)

@api_bp.route("/categories/<cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    # Sesuai Aturan 93: "Kategori dilarang dihapus selama masih dirujuk oleh buku,
    # termasuk buku nonaktif."
    denied = check_auth("admin")
    if denied:
        return denied

    if is_live_db():
        db = get_db()
        try:
            oid = ObjectId(cat_id)
        except Exception:
            return jsonify({"error": "ID kategori tidak valid"}), 400

        referenced_count = db.books.count_documents({"kategori_id": oid})
        if referenced_count > 0:
            return jsonify({
                "error": f"Kategori dilarang dihapus karena masih dirujuk oleh {referenced_count} buku (termasuk buku nonaktif)."
            }), 400

        res = db.categories.delete_one({"_id": oid})
        if res.deleted_count == 0:
            return jsonify({"error": "Kategori tidak ditemukan"}), 404
        return jsonify({"success": True, "message": "Kategori berhasil dihapus"})
    else:
        referenced_count = len([b for b in _in_memory_books if b.get("kategori_id") == cat_id])
        if referenced_count > 0:
            return jsonify({
                "error": f"Kategori dilarang dihapus karena masih dirujuk oleh {referenced_count} buku (termasuk buku nonaktif)."
            }), 400

        global _in_memory_categories
        initial_len = len(_in_memory_categories)
        _in_memory_categories = [c for c in _in_memory_categories if c["id"] != cat_id]
        if len(_in_memory_categories) == initial_len:
            return jsonify({"error": "Kategori tidak ditemukan"}), 404
        return jsonify({"success": True, "message": "Kategori berhasil dihapus"})

# ----------------- KOLEKSI: BOOKS -----------------
@api_bp.route("/books", methods=["GET"])
def get_books():
    denied = check_auth()
    if denied:
        return denied

    search = request.args.get("search", "").strip()
    kategori_id = request.args.get("kategori_id", "").strip()
    status = request.args.get("status", "aktif").strip()  # "aktif", "nonaktif", "semua"
    stock_status = request.args.get("stock_status", "").strip()

    books = query_books(search=search, kategori_id=kategori_id, status=status, stock_status=stock_status)
    return jsonify(books)

@api_bp.route("/books/<book_id>", methods=["GET"])
def get_book_by_id(book_id):
    denied = check_auth()
    if denied:
        return denied
    
    cat_map = get_categories_map()
    if is_live_db():
        db = get_db()
        try:
            doc = db.books.find_one({"_id": ObjectId(book_id)})
            if not doc:
                return jsonify({"error": "Buku tidak ditemukan"}), 404
            doc = serialize_doc(doc)
            doc["kategori_nama"] = cat_map.get(str(doc.get("kategori_id")), "Kategori Tidak Diketahui")
            return jsonify(doc)
        except Exception:
            return jsonify({"error": "ID buku tidak valid"}), 400
    else:
        book = next((b for b in _in_memory_books if b["id"] == book_id), None)
        if not book:
            return jsonify({"error": "Buku tidak ditemukan"}), 404
        b_copy = dict(book)
        b_copy["kategori_nama"] = cat_map.get(str(b_copy.get("kategori_id")), "Kategori Tidak Diketahui")
        return jsonify(b_copy)

@api_bp.route("/books", methods=["POST"])
def create_book():
    denied = check_auth("admin")
    if denied:
        return denied
    data = request.get_json() or {}
    
    # Normalisasi format ISBN di server (Aturan 13 & 52: ISBN-13 tanpa tanda hubung)
    raw_isbn = str(data.get("isbn", "")).strip()
    isbn = normalize_isbn(raw_isbn)
    judul = str(data.get("judul", "")).strip()
    penulis = str(data.get("penulis", "")).strip()
    penerbit = str(data.get("penerbit", "")).strip()
    kategori_id = str(data.get("kategori_id", "")).strip()

    if not isbn:
        return jsonify({"error": "ISBN wajib diisi"}), 400
    if not judul:
        return jsonify({"error": "Judul buku wajib diisi"}), 400
    if not penulis:
        return jsonify({"error": "Penulis buku wajib diisi"}), 400
    if not kategori_id:
        return jsonify({"error": "Kategori wajib dipilih"}), 400

    # Harga integer rupiah tanpa desimal (Aturan 18, 19, 54)
    try:
        harga_beli = parse_int_safe(data.get("harga_beli", 0))
        harga_jual = parse_int_safe(data.get("harga_jual", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Harga beli dan harga jual harus berupa bilangan bulat (integer Rupiah)"}), 400

    try:
        stok = parse_int_safe(data.get("stok", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Stok harus berupa bilangan bulat (minimal 0)"}), 400

    if harga_beli < 0 or harga_jual < 0:
        return jsonify({"error": "Harga beli dan harga jual minimal 0"}), 400
    if stok < 0:
        return jsonify({"error": "Stok minimal 0"}), 400

    now = datetime.now()

    if is_live_db():
        db = get_db()
        # Verifikasi kategori_id valid
        try:
            cat_oid = ObjectId(kategori_id)
            if not db.categories.find_one({"_id": cat_oid}):
                return jsonify({"error": "Kategori yang dipilih tidak ditemukan"}), 400
        except Exception:
            return jsonify({"error": "Kategori ID tidak valid"}), 400

        # Cek keunikan ISBN (termasuk buku nonaktif - Aturan 13 & 67)
        existing = db.books.find_one({"isbn": isbn})
        if existing:
            if not existing.get("aktif", True):
                return jsonify({
                    "error": f"Buku dengan ISBN '{isbn}' pernah dihapus/dinonaktifkan ('{existing.get('judul')}').",
                    "can_restore": True,
                    "existing_id": str(existing["_id"]),
                    "existing_judul": existing.get("judul")
                }), 409
            else:
                return jsonify({"error": f"Buku dengan ISBN '{isbn}' sudah ada di database."}), 400

        new_doc = {
            "isbn": isbn,
            "judul": judul,
            "penulis": penulis,
            "penerbit": penerbit,
            "kategori_id": cat_oid,
            "harga_beli": harga_beli,
            "harga_jual": harga_jual,
            "stok": stok,
            "aktif": True,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        res = db.books.insert_one(new_doc)
        new_doc["id"] = str(res.inserted_id)
        if "_id" in new_doc:
            del new_doc["_id"]
        new_doc["kategori_id"] = str(new_doc["kategori_id"])
        return jsonify(new_doc), 201

    else:
        # Fallback In-Memory
        existing = next((b for b in _in_memory_books if b["isbn"] == isbn), None)
        if existing:
            if not existing.get("aktif", True):
                return jsonify({
                    "error": f"Buku dengan ISBN '{isbn}' pernah dihapus/dinonaktifkan ('{existing.get('judul')}').",
                    "can_restore": True,
                    "existing_id": existing["id"],
                    "existing_judul": existing.get("judul")
                }), 409
            else:
                return jsonify({"error": f"Buku dengan ISBN '{isbn}' sudah ada di database."}), 400

        new_doc = {
            "id": f"book-{len(_in_memory_books) + 1}",
            "isbn": isbn,
            "judul": judul,
            "penulis": penulis,
            "penerbit": penerbit,
            "kategori_id": kategori_id,
            "harga_beli": harga_beli,
            "harga_jual": harga_jual,
            "stok": stok,
            "aktif": True,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat()
        }
        _in_memory_books.append(new_doc)
        return jsonify(new_doc), 201

@api_bp.route("/books/<book_id>", methods=["PUT"])
def update_book(book_id):
    denied = check_auth("admin")
    if denied:
        return denied
        
    data = request.get_json() or {}

    raw_isbn = str(data.get("isbn", "")).strip()
    isbn = normalize_isbn(raw_isbn)
    judul = str(data.get("judul", "")).strip()
    penulis = str(data.get("penulis", "")).strip()
    penerbit = str(data.get("penerbit", "")).strip()
    kategori_id = str(data.get("kategori_id", "")).strip()

    if not isbn:
        return jsonify({"error": "ISBN wajib diisi"}), 400
    if not judul:
        return jsonify({"error": "Judul buku wajib diisi"}), 400
    if not penulis:
        return jsonify({"error": "Penulis buku wajib diisi"}), 400
    if not kategori_id:
        return jsonify({"error": "Kategori wajib dipilih"}), 400

    try:
        harga_beli = parse_int_safe(data.get("harga_beli", 0))
        harga_jual = parse_int_safe(data.get("harga_jual", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Harga beli dan harga jual harus berupa bilangan bulat (integer Rupiah)"}), 400

    if harga_beli < 0 or harga_jual < 0:
        return jsonify({"error": "Harga beli dan harga jual minimal 0"}), 400

    now = datetime.now()

    # PENTING: Sesuai Aturan 70: "stok tidak boleh ditimpa oleh edit data buku."
    # Field stok sengaja tidak dimasukkan ke dalam update_fields!
    update_fields = {
        "isbn": isbn,
        "judul": judul,
        "penulis": penulis,
        "penerbit": penerbit,
        "harga_beli": harga_beli,
        "harga_jual": harga_jual,
        "updated_at": now.isoformat()
    }

    if is_live_db():
        db = get_db()
        try:
            oid = ObjectId(book_id)
        except Exception:
            return jsonify({"error": "ID buku tidak valid"}), 400

        try:
            cat_oid = ObjectId(kategori_id)
            if not db.categories.find_one({"_id": cat_oid}):
                return jsonify({"error": "Kategori tidak ditemukan"}), 400
            update_fields["kategori_id"] = cat_oid
        except Exception:
            return jsonify({"error": "Kategori ID tidak valid"}), 400

        # Cek tabrakan ISBN dengan buku lain
        dup = db.books.find_one({"isbn": isbn, "_id": {"$ne": oid}})
        if dup:
            return jsonify({"error": f"ISBN '{isbn}' sudah digunakan oleh buku lain ({dup.get('judul')})"}), 400

        res = db.books.update_one({"_id": oid}, {"$set": update_fields})
        if res.matched_count == 0:
            return jsonify({"error": "Buku tidak ditemukan"}), 404

        updated = db.books.find_one({"_id": oid})
        return jsonify(serialize_doc(updated))
    else:
        book = next((b for b in _in_memory_books if b["id"] == book_id), None)
        if not book:
            return jsonify({"error": "Buku tidak ditemukan"}), 404
        if any(b["isbn"] == isbn and b["id"] != book_id for b in _in_memory_books):
            return jsonify({"error": f"ISBN '{isbn}' sudah digunakan oleh buku lain"}), 400

        update_fields["kategori_id"] = kategori_id
        book.update(update_fields)
        return jsonify(book)

# SOFT DELETE BUKU (Aturan 21, 58-68)
@api_bp.route("/books/<book_id>", methods=["DELETE"])
def soft_delete_book(book_id):
    denied = check_auth("admin")
    if denied:
        return denied

    now = datetime.now()
    if is_live_db():
        db = get_db()
        try:
            oid = ObjectId(book_id)
        except Exception:
            return jsonify({"error": "ID buku tidak valid"}), 400

        book = db.books.find_one({"_id": oid})
        if not book:
            return jsonify({"error": "Buku tidak ditemukan"}), 404

        # Ubah aktif menjadi False (Soft Delete)
        db.books.update_one(
            {"_id": oid},
            {"$set": {"aktif": False, "updated_at": now.isoformat()}}
        )
        return jsonify({
            "success": True,
            "message": f"Buku '{book.get('judul')}' berhasil dinonaktifkan (soft delete). Riwayat transaksi tetap terjaga."
        })
    else:
        book = next((b for b in _in_memory_books if b["id"] == book_id), None)
        if not book:
            return jsonify({"error": "Buku tidak ditemukan"}), 404
        book["aktif"] = False
        book["updated_at"] = now.isoformat()
        return jsonify({
            "success": True,
            "message": f"Buku '{book.get('judul')}' berhasil dinonaktifkan (soft delete). Riwayat transaksi tetap terjaga."
        })

# AKTIFKAN KEMBALI BUKU (Aturan 67)
@api_bp.route("/books/<book_id>/restore", methods=["POST"])
def restore_book(book_id):
    denied = check_auth("admin")
    if denied:
        return denied

    now = datetime.now()
    if is_live_db():
        db = get_db()
        try:
            oid = ObjectId(book_id)
        except Exception:
            return jsonify({"error": "ID buku tidak valid"}), 400

        res = db.books.update_one(
            {"_id": oid},
            {"$set": {"aktif": True, "updated_at": now.isoformat()}}
        )
        if res.matched_count == 0:
            return jsonify({"error": "Buku tidak ditemukan"}), 404
        updated = db.books.find_one({"_id": oid})
        return jsonify(serialize_doc(updated))
    else:
        book = next((b for b in _in_memory_books if b["id"] == book_id), None)
        if not book:
            return jsonify({"error": "Buku tidak ditemukan"}), 404
        book["aktif"] = True
        book["updated_at"] = now.isoformat()
        return jsonify(book)

# PENYESUAIAN STOK MANUAL
@api_bp.route("/books/adjust-stock", methods=["POST"])
def adjust_stock():
    denied = check_auth("admin")
    if denied:
        return denied

    data = request.get_json() or {}
    book_id = data.get("id")
    try:
        delta = int(data.get("delta", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Delta stok harus bilangan bulat"}), 400

    alasan = str(data.get("alasan", "Penyesuaian")).strip()

    if not book_id:
        return jsonify({"error": "ID Buku wajib diisi"}), 400
    if delta == 0:
        return jsonify({"error": "Delta stok tidak boleh 0"}), 400

    now = datetime.now()

    if is_live_db():
        db = get_db()
        try:
            oid = ObjectId(book_id)
        except Exception:
            return jsonify({"error": "ID Buku tidak valid"}), 400

        book = db.books.find_one({"_id": oid})
        if not book:
            return jsonify({"error": "Buku tidak ditemukan"}), 404

        new_stock = book.get("stok", 0) + delta
        if new_stock < 0:
            return jsonify({"error": f"Stok tidak boleh kurang dari 0. Stok saat ini: {book.get('stok', 0)}"}), 400

        db.books.update_one(
            {"_id": oid},
            {"$set": {"stok": new_stock, "updated_at": now.isoformat()}}
        )
        updated = db.books.find_one({"_id": oid})
        return jsonify(serialize_doc(updated))
    else:
        book = next((b for b in _in_memory_books if b["id"] == book_id), None)
        if not book:
            return jsonify({"error": "Buku tidak ditemukan"}), 404
        new_stock = book.get("stok", 0) + delta
        if new_stock < 0:
            return jsonify({"error": f"Stok tidak boleh kurang dari 0. Stok saat ini: {book.get('stok', 0)}"}), 400
        book["stok"] = new_stock
        book["updated_at"] = now.isoformat()
        return jsonify(book)

# ----------------- KOLEKSI: USERS & AUTH -----------------
@api_bp.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Username dan password wajib diisi"}), 400

    if is_live_db():
        db = get_db()
        user = db.users.find_one({"username": username})
        if not user:
            return jsonify({"error": "Username atau password salah"}), 401
        if not user.get("aktif", True):
            return jsonify({"error": "Akun ini telah dinonaktifkan. Silakan hubungi Admin."}), 403
        if not check_password_hash(user.get("password_hash", ""), password):
            return jsonify({"error": "Username atau password salah"}), 401

        user_data = serialize_doc(user, hide_password=True)
        return jsonify({"success": True, "user": user_data, "token": create_token(user_data)})
    else:
        user = next((u for u in _in_memory_users if u["username"] == username), None)
        if not user:
            return jsonify({"error": "Username atau password salah"}), 401
        if not user.get("aktif", True):
            return jsonify({"error": "Akun ini telah dinonaktifkan. Silakan hubungi Admin."}), 403
        if not check_password_hash(user.get("password_hash", ""), password):
            return jsonify({"error": "Username atau password salah"}), 401

        user_data = dict(user)
        del user_data["password_hash"]
        return jsonify({"success": True, "user": user_data, "token": create_token(user_data)})

@api_bp.route("/users", methods=["GET"])
def get_users():
    denied = check_auth("admin")
    if denied:
        return denied

    if is_live_db():
        db = get_db()
        users = list(db.users.find().sort("nama", 1))
        return jsonify(serialize_docs(users, hide_password=True))
    else:
        res = []
        for u in _in_memory_users:
            u_copy = dict(u)
            del u_copy["password_hash"]
            res.append(u_copy)
        return jsonify(res)

@api_bp.route("/users", methods=["POST"])
def create_user():
    denied = check_auth("admin")
    if denied:
        return denied

    data = request.get_json() or {}
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", "")).strip()
    nama = str(data.get("nama", "")).strip()
    role = str(data.get("role", "kasir")).strip().lower()

    if not username:
        return jsonify({"error": "Username wajib diisi"}), 400
    if not password or len(password) < 6:
        return jsonify({"error": "Password minimal 6 karakter"}), 400
    if not nama:
        return jsonify({"error": "Nama pegawai wajib diisi"}), 400
    if role not in ["admin", "kasir"]:
        return jsonify({"error": "Role harus 'admin' atau 'kasir'"}), 400

    now = datetime.now()
    user_doc = {
        "username": username,
        "password_hash": generate_password_hash(password),
        "nama": nama,
        "role": role,
        "aktif": True,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat()
    }

    if is_live_db():
        db = get_db()
        if db.users.find_one({"username": username}):
            return jsonify({"error": f"Username '{username}' sudah digunakan"}), 400
        res = db.users.insert_one(user_doc)
        user_doc["id"] = str(res.inserted_id)
        if "_id" in user_doc:
            del user_doc["_id"]
        del user_doc["password_hash"]
        return jsonify(user_doc), 201
    else:
        if any(u["username"] == username for u in _in_memory_users):
            return jsonify({"error": f"Username '{username}' sudah digunakan"}), 400
        user_doc["id"] = f"usr-{len(_in_memory_users) + 1}"
        _in_memory_users.append(user_doc)
        resp = dict(user_doc)
        del resp["password_hash"]
        return jsonify(resp), 201

@api_bp.route("/users/<user_id>/toggle-active", methods=["POST"])
def toggle_user_active(user_id):
    denied = check_auth("admin")
    if denied:
        return denied
        
    current_user = get_auth_user()
    now = datetime.now()
    if is_live_db():
        db = get_db()
        try:
            oid = ObjectId(user_id)
        except Exception:
            return jsonify({"error": "ID User tidak valid"}), 400
        user = db.users.find_one({"_id": oid})
        if not user:
            return jsonify({"error": "User tidak ditemukan"}), 404
        if current_user and (str(current_user.get("sub")) == str(user["_id"]) or current_user.get("username") == user.get("username")):
            return jsonify({"error": "Anda tidak dapat menonaktifkan akun sendiri"}), 400

        new_status = not user.get("aktif", True)
        db.users.update_one(
            {"_id": oid},
            {"$set": {"aktif": new_status, "updated_at": now.isoformat()}}
        )
        updated = db.users.find_one({"_id": oid})
        return jsonify(serialize_doc(updated, hide_password=True))
    else:
        user = next((u for u in _in_memory_users if u["id"] == user_id), None)
        if not user:
            return jsonify({"error": "User tidak ditemukan"}), 404
        if current_user and (str(current_user.get("sub")) == str(user["id"]) or current_user.get("username") == user.get("username")):
            return jsonify({"error": "Anda tidak dapat menonaktifkan akun sendiri"}), 400

        user["aktif"] = not user.get("aktif", True)
        user["updated_at"] = now.isoformat()
        resp = dict(user)
        del resp["password_hash"]
        return jsonify(resp)

# ----------------- POS TRANSAKSI & CHECKOUT -----------------
WIB = timezone(timedelta(hours=7))
TARIF_PAJAK = float(os.getenv("TARIF_PAJAK", "0"))


def format_rupiah(angka):
    return "Rp " + f"{int(angka):,}".replace(",", ".")


def get_auth_user():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        return jwt.decode(header[7:], os.environ["JWT_SECRET"], algorithms=["HS256"])
    except Exception:
        return None


def hitung_pajak(subtotal):
    tarif = Decimal(str(TARIF_PAJAK))
    return int((Decimal(subtotal) * tarif).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def gabung_keranjang(items):
    if not items or not isinstance(items, list):
        return None, "Keranjang belanja kosong."
    gabungan = {}
    for it in items:
        try:
            qty = int(it.get("qty", 1))
        except (ValueError, TypeError, AttributeError):
            return None, "Jumlah item tidak valid."
        book_id = str(it.get("id", "")).strip()
        if qty <= 0 or not book_id:
            return None, f"Item keranjang tidak valid ({it.get('judul', 'Buku')})."
        gabungan[book_id] = gabungan.get(book_id, 0) + qty
    return gabungan, None


def _ambil_buku(book_id):
    if is_live_db():
        doc = get_db().books.find_one({"_id": ObjectId(book_id)})
        return serialize_doc(doc) if doc else None
    return next((b for b in _in_memory_books if b["id"] == book_id), None)


def _kurangi_stok(book_id, qty):
    waktu = datetime.now(WIB).isoformat()
    if is_live_db():
        hasil = get_db().books.update_one(
            {"_id": ObjectId(book_id), "aktif": True, "stok": {"$gte": qty}},
            {"$inc": {"stok": -qty}, "$set": {"updated_at": waktu}},
        )
        return hasil.modified_count == 1
    buku = next(b for b in _in_memory_books if b["id"] == book_id)
    if not buku.get("aktif", True) or buku["stok"] < qty:
        return False
    buku["stok"] -= qty
    buku["updated_at"] = waktu
    return True


def _kembalikan_stok(daftar):
    for v in daftar:
        if is_live_db():
            get_db().books.update_one(
                {"_id": ObjectId(v["buku_id"])},
                {"$inc": {"stok": v["qty"]}},
            )
        else:
            buku = next(b for b in _in_memory_books if b["id"] == v["buku_id"])
            buku["stok"] += v["qty"]


def _simpan_transaksi(doc):
    if is_live_db():
        hasil = get_db().transactions.insert_one(doc)
        doc["id"] = str(hasil.inserted_id)
        doc.pop("_id", None)
    else:
        doc["id"] = f"tx-{len(_in_memory_transactions) + 1}"
        _in_memory_transactions.insert(0, doc)


@api_bp.route("/config", methods=["GET"])
def get_config():
    return jsonify({"tarif_pajak": TARIF_PAJAK})


@api_bp.route("/checkout", methods=["POST"])
def checkout():
    denied = check_auth("admin", "kasir")
    if denied:
        return denied

    data = request.get_json() or {}
    metode = str(data.get("metode_pembayaran", "tunai")).lower()
    pengguna = get_auth_user()
    kasir_nama = pengguna["username"] if pengguna else str(data.get("kasir_nama", "Kasir 1")).strip()
    try:
        tunai_diterima = int(data.get("tunai_diterima", 0))
    except (ValueError, TypeError):
        tunai_diterima = 0

    gabungan, galat = gabung_keranjang(data.get("items"))
    if galat:
        return jsonify({"error": galat}), 400

    items = []
    subtotal = 0
    for book_id, qty in gabungan.items():
        try:
            buku = _ambil_buku(book_id)
        except Exception:
            return jsonify({"error": "ID buku tidak valid"}), 400
        if not buku:
            return jsonify({"error": "Buku tidak ditemukan"}), 404
        if not buku.get("aktif", True):
            return jsonify({"error": f"Buku '{buku.get('judul')}' berstatus nonaktif dan tidak dapat dijual."}), 400
        if buku.get("stok", 0) < qty:
            return jsonify({
                "error": f"Stok tidak mencukupi untuk '{buku['judul']}'. Tersedia: {buku.get('stok', 0)}, diminta: {qty}"
            }), 400
        harga = int(buku.get("harga_jual", 0))
        sub = harga * qty
        subtotal += sub
        items.append({
            "buku_id": book_id,
            "isbn": buku.get("isbn", ""),
            "judul": buku.get("judul", ""),
            "penulis": buku.get("penulis", ""),
            "harga_jual": harga,
            "qty": qty,
            "subtotal": sub,
        })

    pajak = hitung_pajak(subtotal)
    total = subtotal + pajak
    if metode == "tunai" and tunai_diterima < total:
        return jsonify({
            "error": f"Uang tunai ({format_rupiah(tunai_diterima)}) kurang dari total tagihan ({format_rupiah(total)})"
        }), 400
    kembalian = (tunai_diterima - total) if metode == "tunai" else 0

    dikurangi = []
    for v in items:
        if not _kurangi_stok(v["buku_id"], v["qty"]):
            _kembalikan_stok(dikurangi)
            return jsonify({
                "error": f"Stok '{v['judul']}' baru saja berubah dan tidak cukup. Muat ulang daftar buku lalu coba lagi."
            }), 409
        dikurangi.append(v)

    sekarang = datetime.now(WIB)
    tx_doc = {
        "no_faktur": f"INV-{sekarang.strftime('%Y%m%d%H%M')}-{str(uuid.uuid4())[:6].upper()}",
        "items": items,
        "subtotal": subtotal,
        "tarif_pajak": TARIF_PAJAK,
        "pajak": pajak,
        "total": total,
        "metode_pembayaran": metode,
        "tunai_diterima": tunai_diterima if metode == "tunai" else total,
        "kembalian": kembalian,
        "kasir_nama": kasir_nama,
        "created_at": sekarang.isoformat(),
    }
    try:
        _simpan_transaksi(tx_doc)
    except Exception as e:
        print(f"[Checkout] gagal menyimpan nota: {e}")
        _kembalikan_stok(dikurangi)
        return jsonify({"error": "Transaksi gagal disimpan, stok dikembalikan."}), 500

    return jsonify({
        "success": True,
        "message": "Transaksi berhasil disimpan!",
        "transaction": tx_doc,
    }), 201


@api_bp.route("/transactions", methods=["GET"])
def get_transactions():
    denied = check_auth()
    if denied:
        return denied

    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 200))
    except ValueError:
        limit = 50

    if is_live_db():
        docs = list(get_db().transactions.find().sort("created_at", -1).limit(limit))
        return jsonify(serialize_docs(docs))
    return jsonify(_in_memory_transactions[:limit])


@api_bp.route("/transactions/<invoice_or_id>", methods=["GET"])
def get_transaction_detail(invoice_or_id):
    denied = check_auth()
    if denied:
        return denied

    if is_live_db():
        query = {"no_faktur": invoice_or_id}
        try:
            query = {"$or": [{"no_faktur": invoice_or_id}, {"_id": ObjectId(invoice_or_id)}]}
        except Exception:
            pass
        doc = get_db().transactions.find_one(query)
        if not doc:
            return jsonify({"error": "Transaksi tidak ditemukan"}), 404
        return jsonify(serialize_doc(doc))

    tx = next(
        (t for t in _in_memory_transactions
         if t["no_faktur"] == invoice_or_id or t.get("id") == invoice_or_id),
        None,
    )
    if not tx:
        return jsonify({"error": "Transaksi tidak ditemukan"}), 404
    return jsonify(tx)


def _parse_tanggal(teks, default):
    try:
        return datetime.strptime(teks or "", "%Y-%m-%d").date()
    except ValueError:
        return default


def rangkum_transaksi(transaksi, dari, sampai):
    ringkasan = {"jumlah_transaksi": len(transaksi), "buku_terjual": 0, "omzet": 0, "pajak": 0, "total": 0}

    per_hari = {}
    hari = dari
    while hari <= sampai:
        per_hari[hari.isoformat()] = {"tanggal": hari.isoformat(), "jumlah": 0, "total": 0}
        hari += timedelta(days=1)

    per_metode = {}
    terlaris = {}

    for t in transaksi:
        total = int(t.get("total", 0))
        pajak = int(t.get("pajak", 0))
        subtotal = int(t.get("subtotal", total - pajak))
        items = t.get("items", [])

        ringkasan["total"] += total
        ringkasan["pajak"] += pajak
        ringkasan["omzet"] += subtotal
        ringkasan["buku_terjual"] += sum(int(i.get("qty", 0)) for i in items)

        tanggal = str(t.get("created_at", ""))[:10]
        if tanggal in per_hari:
            per_hari[tanggal]["jumlah"] += 1
            per_hari[tanggal]["total"] += total

        baris_metode = per_metode.setdefault(t.get("metode_pembayaran", "tunai"), {"jumlah": 0, "total": 0})
        baris_metode["jumlah"] += 1
        baris_metode["total"] += total

        for i in items:
            baris_buku = terlaris.setdefault(i.get("isbn", ""), {
                "isbn": i.get("isbn", ""),
                "judul": i.get("judul", ""),
                "qty": 0,
                "pendapatan": 0,
            })
            baris_buku["qty"] += int(i.get("qty", 0))
            baris_buku["pendapatan"] += int(i.get("subtotal", 0))

    terbaru = sorted(transaksi, key=lambda t: str(t.get("created_at", "")), reverse=True)[:10]

    return {
        "ringkasan": ringkasan,
        "per_hari": list(per_hari.values()),
        "per_metode": sorted(
            ({"metode": k, **v} for k, v in per_metode.items()),
            key=lambda x: -x["total"],
        ),
        "terlaris": sorted(terlaris.values(), key=lambda x: (-x["qty"], x["judul"]))[:5],
        "terbaru": [
            {k: t.get(k) for k in ("no_faktur", "created_at", "metode_pembayaran", "total", "kasir_nama")}
            for t in terbaru
        ],
    }


@api_bp.route("/reports/summary", methods=["GET"])
def report_summary():
    denied = check_auth("admin")
    if denied:
        return denied

    hari_ini = datetime.now(WIB).date()
    dari = _parse_tanggal(request.args.get("dari"), hari_ini - timedelta(days=6))
    sampai = _parse_tanggal(request.args.get("sampai"), hari_ini)
    if dari > sampai:
        return jsonify({"error": "Tanggal 'dari' tidak boleh setelah 'sampai'"}), 400
    if (sampai - dari).days > 366:
        return jsonify({"error": "Rentang laporan maksimal 1 tahun"}), 400

    batas_awal = dari.isoformat()
    batas_akhir = (sampai + timedelta(days=1)).isoformat()

    if is_live_db():
        dokumen = get_db().transactions.find({"created_at": {"$gte": batas_awal, "$lt": batas_akhir}})
        transaksi = serialize_docs(list(dokumen))
    else:
        transaksi = [
            t for t in _in_memory_transactions
            if batas_awal <= str(t.get("created_at", "")) < batas_akhir
        ]

    return jsonify(rangkum_transaksi(transaksi, dari, sampai))

# ----------------- STATISTIK & KPI -----------------
@api_bp.route("/stats", methods=["GET"])
def get_stats():
    denied = check_auth()
    if denied:
        return denied
    now_date = datetime.now(WIB).strftime("%Y-%m-%d")
    if is_live_db():
        db = get_db()
        books = list(db.books.find({"aktif": True}))
        total_buku = len(books)
        total_eksemplar = sum(b.get("stok", 0) for b in books)
        total_nilai_inventaris = sum(b.get("harga_jual", 0) * b.get("stok", 0) for b in books)
        low_stock = sum(1 for b in books if 0 < b.get("stok", 0) <= 5)
        out_of_stock = sum(1 for b in books if b.get("stok", 0) == 0)
        total_nonaktif = db.books.count_documents({"aktif": False})

        today_regex = re.compile(f"^{now_date}")
        today_txs = list(db.transactions.find({"created_at": {"$regex": today_regex}}))
        today_sales_count = len(today_txs)
        today_sales_amount = sum(t.get("total", 0) for t in today_txs)

        return jsonify({
            "total_buku": total_buku,
            "total_eksemplar": total_eksemplar,
            "total_nilai_inventaris": total_nilai_inventaris,
            "low_stock": low_stock,
            "out_of_stock": out_of_stock,
            "total_nonaktif": total_nonaktif,
            "today_sales_count": today_sales_count,
            "today_sales_amount": today_sales_amount
        })
    else:
        books = [b for b in _in_memory_books if b.get("aktif") is True]
        total_buku = len(books)
        total_eksemplar = sum(b.get("stok", 0) for b in books)
        total_nilai_inventaris = sum(b.get("harga_jual", 0) * b.get("stok", 0) for b in books)
        low_stock = sum(1 for b in books if 0 < b.get("stok", 0) <= 5)
        out_of_stock = sum(1 for b in books if b.get("stok", 0) == 0)
        total_nonaktif = len([b for b in _in_memory_books if b.get("aktif") is False])

        today_txs = [t for t in _in_memory_transactions if t.get("created_at", "").startswith(now_date)]
        today_sales_count = len(today_txs)
        today_sales_amount = sum(t.get("total", 0) for t in today_txs)

        return jsonify({
            "total_buku": total_buku,
            "total_eksemplar": total_eksemplar,
            "total_nilai_inventaris": total_nilai_inventaris,
            "low_stock": low_stock,
            "out_of_stock": out_of_stock,
            "total_nonaktif": total_nonaktif,
            "today_sales_count": today_sales_count,
            "today_sales_amount": today_sales_amount
        })

# Blueprint Registrations
app.register_blueprint(api_bp, url_prefix="/api")
app.register_blueprint(api_bp, url_prefix="", name="api_root")

# ----------------- LOCAL DEV STATIC SERVING -----------------
PUBLIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "public"))

@app.route("/")
def serve_index():
    if os.path.exists(os.path.join(PUBLIC_DIR, "index.html")):
        return send_from_directory(PUBLIC_DIR, "index.html")
    return jsonify({"message": "BookPOS API Running. Buka frontend via index.html atau master.html"})

@app.route("/master.html")
def serve_master():
    if os.path.exists(os.path.join(PUBLIC_DIR, "master.html")):
        return send_from_directory(PUBLIC_DIR, "master.html")
    return jsonify({"error": "master.html tidak ditemukan"}), 404

@app.route("/<path:filename>")
def serve_static(filename):
    file_path = os.path.join(PUBLIC_DIR, filename)
    if os.path.exists(file_path):
        return send_from_directory(PUBLIC_DIR, filename)
    return jsonify({"error": f"Path /{filename} tidak ditemukan"}), 404

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    port = int(os.getenv("PORT", 5000))
    print("\n==========================================")
    print(f" [BookPOS] Server Berjalan pada http://127.0.0.1:{port}")
    print(f" - Kasir / POS:       http://127.0.0.1:{port}/")
    print(f" - Master Data Buku:  http://127.0.0.1:{port}/master.html")
    print(f" - Cek Status API:    http://127.0.0.1:{port}/api/health")
    print("==========================================\n")
    app.run(host="0.0.0.0", port=port, debug=True)

