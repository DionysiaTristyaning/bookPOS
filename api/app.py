import os
import sys
import re
import uuid
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

# Blueprint API
api_bp = Blueprint("api_bp", __name__)

JWT_SECRET = os.getenv("JWT_SECRET", "bookpos-default-jwt-secret-key-change-in-prod")
WIB = timezone(timedelta(hours=7))
TARIF_PAJAK = float(os.getenv("TARIF_PAJAK", "0"))

def is_live_db():
    status = get_connection_status()
    return status.get("connected", False)

def require_db():
    if not is_live_db() or get_db() is None:
        return jsonify({
            "error": "Basis data MongoDB Atlas belum terhubung. Pastikan MONGO_URI sudah dikonfigurasi di file .env atau pengaturan environment variables."
        }), 503
    return None

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
    """Mengembalikan None kalau diperbolehkan, atau respons JSON error jika ditolak."""
    if os.getenv("AUTH_REQUIRED") != "1":
        return None  # Mode dev / non-aktif
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

def parse_int_safe(val, default=0):
    """Sanitasi integer rupiah: menangani int, float, atau string dengan titik ribuan."""
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        return int(val)
    cleaned = re.sub(r"[^\d]", "", str(val).strip())
    return int(cleaned) if cleaned else default

def format_rupiah(angka):
    return "Rp " + f"{int(angka):,}".replace(",", ".")

def hitung_pajak(subtotal):
    tarif = Decimal(str(TARIF_PAJAK))
    return int((Decimal(subtotal) * tarif).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

# ----------------- KATEGORI MAPPING HELPER -----------------
def get_categories_map():
    if not is_live_db():
        return {}
    db = get_db()
    cats = list(db.categories.find())
    return {str(c["_id"]): c["nama"] for c in cats}

# ----------------- CENTRALIZED BOOK QUERY HELPER -----------------
def query_books(search="", kategori_id="", status="aktif", stock_status=""):
    if not is_live_db():
        return []
    
    db = get_db()
    cat_map = get_categories_map()
    query = {}
    
    # Filter status aktif (default: aktif: True)
    if status == "aktif":
        query["aktif"] = True
    elif status == "nonaktif":
        query["aktif"] = False
    
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

# ----------------- HEALTH CHECK -----------------
@api_bp.route("/health", methods=["GET"])
def health():
    status = get_connection_status()
    connected = status.get("connected", False)
    db = get_db() if connected else None
    book_count = 0
    if db is not None:
        try:
            book_count = db.books.count_documents({"aktif": True})
        except Exception:
            book_count = 0

    return jsonify({
        "status": "ok" if connected else "database_disconnected",
        "database_connected": connected,
        "database_name": status.get("database"),
        "error": status.get("error"),
        "total_buku_aktif": book_count,
        "timestamp": datetime.now().isoformat()
    })

# ----------------- SEED DATA -----------------
@api_bp.route("/seed", methods=["POST"])
def seed_data():
    db_err = require_db()
    if db_err:
        return db_err
    
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

# ----------------- KOLEKSI: CATEGORIES -----------------
@api_bp.route("/categories", methods=["GET"])
def get_categories():
    denied = check_auth()
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    db = get_db()
    cats = list(db.categories.find().sort("nama", 1))
    serialized = serialize_docs(cats)
    for c in serialized:
        try:
            oid = ObjectId(c["id"])
            c["total_buku"] = db.books.count_documents({"kategori_id": oid})
        except Exception:
            c["total_buku"] = 0
    return jsonify(serialized)

@api_bp.route("/categories", methods=["POST"])
def create_category():
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    data = request.get_json() or {}
    nama = str(data.get("nama", "")).strip()
    if not nama:
        return jsonify({"error": "Nama kategori wajib diisi"}), 400

    slug = slugify(data.get("slug") or nama)
    if not slug:
        return jsonify({"error": "Slug tidak valid"}), 400

    new_cat = {"nama": nama, "slug": slug}
    db = get_db()
    if db.categories.find_one({"slug": slug}):
        return jsonify({"error": f"Kategori dengan slug '{slug}' sudah ada"}), 400
    res = db.categories.insert_one(new_cat)
    new_cat["id"] = str(res.inserted_id)
    if "_id" in new_cat:
        del new_cat["_id"]
    return jsonify(new_cat), 201

@api_bp.route("/categories/<cat_id>", methods=["PUT"])
def update_category(cat_id):
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err
        
    data = request.get_json() or {}
    nama = str(data.get("nama", "")).strip()
    if not nama:
        return jsonify({"error": "Nama kategori wajib diisi"}), 400

    slug = slugify(data.get("slug") or nama)
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

@api_bp.route("/categories/<cat_id>", methods=["DELETE"])
def delete_category(cat_id):
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

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

# ----------------- KOLEKSI: BOOKS -----------------
@api_bp.route("/books", methods=["GET"])
def get_books():
    denied = check_auth()
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    search = request.args.get("search", "").strip()
    kategori_id = request.args.get("kategori_id", "").strip()
    status = request.args.get("status", "aktif").strip()
    stock_status = request.args.get("stock_status", "").strip()

    books = query_books(search=search, kategori_id=kategori_id, status=status, stock_status=stock_status)
    return jsonify(books)

@api_bp.route("/books/<book_id>", methods=["GET"])
def get_book_by_id(book_id):
    denied = check_auth()
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err
    
    cat_map = get_categories_map()
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

@api_bp.route("/books", methods=["POST"])
def create_book():
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

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

    try:
        stok = parse_int_safe(data.get("stok", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Stok harus berupa bilangan bulat (minimal 0)"}), 400

    if harga_beli < 0 or harga_jual < 0:
        return jsonify({"error": "Harga beli dan harga jual minimal 0"}), 400
    if stok < 0:
        return jsonify({"error": "Stok minimal 0"}), 400

    now = datetime.now()
    db = get_db()
    try:
        cat_oid = ObjectId(kategori_id)
        if not db.categories.find_one({"_id": cat_oid}):
            return jsonify({"error": "Kategori yang dipilih tidak ditemukan"}), 400
    except Exception:
        return jsonify({"error": "Kategori ID tidak valid"}), 400

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

@api_bp.route("/books/<book_id>", methods=["PUT"])
def update_book(book_id):
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err
        
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
    update_fields = {
        "isbn": isbn,
        "judul": judul,
        "penulis": penulis,
        "penerbit": penerbit,
        "harga_beli": harga_beli,
        "harga_jual": harga_jual,
        "updated_at": now.isoformat()
    }

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

    dup = db.books.find_one({"isbn": isbn, "_id": {"$ne": oid}})
    if dup:
        return jsonify({"error": f"ISBN '{isbn}' sudah digunakan oleh buku lain ({dup.get('judul')})"}), 400

    res = db.books.update_one({"_id": oid}, {"$set": update_fields})
    if res.matched_count == 0:
        return jsonify({"error": "Buku tidak ditemukan"}), 404

    updated = db.books.find_one({"_id": oid})
    return jsonify(serialize_doc(updated))

@api_bp.route("/books/<book_id>", methods=["DELETE"])
def soft_delete_book(book_id):
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    now = datetime.now()
    db = get_db()
    try:
        oid = ObjectId(book_id)
    except Exception:
        return jsonify({"error": "ID buku tidak valid"}), 400

    book = db.books.find_one({"_id": oid})
    if not book:
        return jsonify({"error": "Buku tidak ditemukan"}), 404

    db.books.update_one(
        {"_id": oid},
        {"$set": {"aktif": False, "updated_at": now.isoformat()}}
    )
    return jsonify({
        "success": True,
        "message": f"Buku '{book.get('judul')}' berhasil dinonaktifkan (soft delete). Riwayat transaksi tetap terjaga."
    })

@api_bp.route("/books/<book_id>/restore", methods=["POST"])
def restore_book(book_id):
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    now = datetime.now()
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

@api_bp.route("/books/adjust-stock", methods=["POST"])
def adjust_stock():
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    data = request.get_json() or {}
    book_id = data.get("id")
    try:
        delta = int(data.get("delta", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "Delta stok harus bilangan bulat"}), 400

    if not book_id:
        return jsonify({"error": "ID Buku wajib diisi"}), 400
    if delta == 0:
        return jsonify({"error": "Delta stok tidak boleh 0"}), 400

    now = datetime.now()
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

# ----------------- KOLEKSI: USERS & AUTH -----------------
@api_bp.route("/auth/login", methods=["POST"])
def login():
    data = request.get_json() or {}
    username = str(data.get("username", "")).strip().lower()
    password = str(data.get("password", "")).strip()

    if not username or not password:
        return jsonify({"error": "Username dan password wajib diisi"}), 400

    db_err = require_db()
    if db_err:
        return db_err

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

@api_bp.route("/users", methods=["GET"])
def get_users():
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    db = get_db()
    users = list(db.users.find().sort("nama", 1))
    return jsonify(serialize_docs(users, hide_password=True))

@api_bp.route("/users", methods=["POST"])
def create_user():
    denied = check_auth("admin")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

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

    db = get_db()
    if db.users.find_one({"username": username}):
        return jsonify({"error": f"Username '{username}' sudah digunakan"}), 400
    res = db.users.insert_one(user_doc)
    user_doc["id"] = str(res.inserted_id)
    if "_id" in user_doc:
        del user_doc["_id"]
    del user_doc["password_hash"]
    return jsonify(user_doc), 201

@api_bp.route("/users/<user_id>/toggle-active", methods=["POST"])
def toggle_user_active(user_id):
    denied = check_auth("admin")
    if denied:
        return denied
        
    db_err = require_db()
    if db_err:
        return db_err

    current_user = get_auth_user()
    now = datetime.now()
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

# ----------------- POS TRANSAKSI & CHECKOUT -----------------
def _ambil_buku(book_id):
    db = get_db()
    if db is None:
        return None
    doc = None
    try:
        doc = db.books.find_one({"_id": ObjectId(book_id)})
    except Exception:
        pass
    if not doc:
        doc = db.books.find_one({"id": str(book_id)})
    if not doc:
        doc = db.books.find_one({"_id": str(book_id)})
    return serialize_doc(doc) if doc else None

def _kurangi_stok(book_id, qty):
    waktu = datetime.now(WIB).isoformat()
    db = get_db()
    if db is None:
        return False
    # Coba update dengan id string terlebih dahulu
    for filter_key in ["id", "_id"]:
        hasil = db.books.update_one(
            {filter_key: str(book_id), "aktif": True, "stok": {"$gte": qty}},
            {"$inc": {"stok": -qty}, "$set": {"updated_at": waktu}},
        )
        if getattr(hasil, "modified_count", 0) == 1:
            return True
    try:
        hasil = db.books.update_one(
            {"_id": ObjectId(book_id), "aktif": True, "stok": {"$gte": qty}},
            {"$inc": {"stok": -qty}, "$set": {"updated_at": waktu}},
        )
        if getattr(hasil, "modified_count", 0) == 1:
            return True
    except Exception:
        pass
    return False

def _kembalikan_stok(daftar):
    db = get_db()
    if db is None:
        return
    for v in daftar:
        b_id = v["buku_id"]
        res = db.books.update_one({"id": str(b_id)}, {"$inc": {"stok": v["qty"]}})
        if getattr(res, "modified_count", 0) == 0:
            try:
                db.books.update_one({"_id": ObjectId(b_id)}, {"$inc": {"stok": v["qty"]}})
            except Exception:
                db.books.update_one({"_id": str(b_id)}, {"$inc": {"stok": v["qty"]}})

def _simpan_transaksi(doc):
    db = get_db()
    if db is None:
        raise RuntimeError("Database tidak terhubung")
    hasil = db.transactions.insert_one(doc)
    doc["id"] = str(hasil.inserted_id)
    doc.pop("_id", None)

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

@api_bp.route("/config", methods=["GET"])
def get_config():
    return jsonify({"tarif_pajak": TARIF_PAJAK})

@api_bp.route("/checkout", methods=["POST"])
def checkout():
    denied = check_auth("admin", "kasir")
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    data = request.get_json() or {}
    metode = str(data.get("metode_pembayaran", "tunai")).strip().lower()
    if metode in ("cash", "uang tunai"):
        metode = "tunai"

    pengguna = get_auth_user()
    kasir_nama = pengguna["username"] if pengguna else str(data.get("kasir_nama", "Kasir 1")).strip()

    tunai_diterima_raw = data.get("tunai_diterima")
    tunai_diterima = parse_int_safe(tunai_diterima_raw, default=0)

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

    # Validasi ketat nominal pembayaran: nominal tidak boleh kurang dari total tagihan
    if metode == "tunai":
        if tunai_diterima < total:
            return jsonify({
                "error": f"Uang tunai ({format_rupiah(tunai_diterima)}) kurang dari total tagihan ({format_rupiah(total)})"
            }), 400
        kembalian = tunai_diterima - total
    else:
        # Untuk non-tunai (kartu, qris, debit, dll): jika nominal disertakan, dilarang kurang dari total
        if tunai_diterima_raw is not None and str(tunai_diterima_raw).strip() != "":
            if tunai_diterima < total:
                return jsonify({
                    "error": f"Nominal pembayaran {metode.upper()} ({format_rupiah(tunai_diterima)}) kurang dari total tagihan ({format_rupiah(total)})"
                }), 400
        tunai_diterima = total
        kembalian = 0

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
        "tunai_diterima": tunai_diterima,
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

    db_err = require_db()
    if db_err:
        return db_err

    try:
        limit = max(1, min(int(request.args.get("limit", 50)), 200))
    except ValueError:
        limit = 50

    db = get_db()
    docs = list(db.transactions.find().sort("created_at", -1).limit(limit))
    return jsonify(serialize_docs(docs))

@api_bp.route("/transactions/<invoice_or_id>", methods=["GET"])
def get_transaction_detail(invoice_or_id):
    denied = check_auth()
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    query = {"no_faktur": invoice_or_id}
    try:
        query = {"$or": [{"no_faktur": invoice_or_id}, {"_id": ObjectId(invoice_or_id)}]}
    except Exception:
        pass
    doc = get_db().transactions.find_one(query)
    if not doc:
        return jsonify({"error": "Transaksi tidak ditemukan"}), 404
    return jsonify(serialize_doc(doc))

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

    db_err = require_db()
    if db_err:
        return db_err

    hari_ini = datetime.now(WIB).date()
    dari = _parse_tanggal(request.args.get("dari"), hari_ini - timedelta(days=6))
    sampai = _parse_tanggal(request.args.get("sampai"), hari_ini)
    if dari > sampai:
        return jsonify({"error": "Tanggal 'dari' tidak boleh setelah 'sampai'"}), 400
    if (sampai - dari).days > 366:
        return jsonify({"error": "Rentang laporan maksimal 1 tahun"}), 400

    batas_awal = dari.isoformat()
    batas_akhir = (sampai + timedelta(days=1)).isoformat()

    db = get_db()
    dokumen = db.transactions.find({"created_at": {"$gte": batas_awal, "$lt": batas_akhir}})
    transaksi = serialize_docs(list(dokumen))
    return jsonify(rangkum_transaksi(transaksi, dari, sampai))

# ----------------- STATISTIK & KPI -----------------
@api_bp.route("/stats", methods=["GET"])
def get_stats():
    denied = check_auth()
    if denied:
        return denied

    db_err = require_db()
    if db_err:
        return db_err

    now_date = datetime.now(WIB).strftime("%Y-%m-%d")
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
    if os.path.exists(os.path.join(PUBLIC_DIR, filename)):
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
