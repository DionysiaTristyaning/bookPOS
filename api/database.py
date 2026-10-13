import os
import re
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING
from bson import ObjectId
import certifi

# Load environment variables from project root .env
_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_env_path)

def get_mongo_uri():
    return os.getenv("MONGO_URI", "").strip()

def get_db_name():
    return os.getenv("DB_NAME", "bookpos")

MONGO_URI = get_mongo_uri()
DB_NAME = get_db_name()

_client = None
_db = None
_is_connected = False
_connection_error = None

def normalize_isbn(isbn_str):
    """Normalize ISBN-13: remove hyphens, spaces, and non-alphanumeric chars."""
    if not isbn_str:
        return ""
    return re.sub(r"[^0-9X]", "", str(isbn_str).strip().upper())

def slugify(text):
    """Generate clean slug: lowercase, hyphenated, no special chars."""
    text = str(text or "").lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")

def init_db():
    global _client, _db, _is_connected, _connection_error, MONGO_URI, DB_NAME
    MONGO_URI = get_mongo_uri()
    DB_NAME = get_db_name()
    
    if not MONGO_URI or "<username>" in MONGO_URI:
        _is_connected = False
        _connection_error = "MONGO_URI belum dikonfigurasi atau masih berisi placeholder."
        return None

    try:
        _client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            tlsCAFile=certifi.where()
        )
        # Test connection ping
        _client.admin.command("ping")
        _db = _client[DB_NAME]
        
        # Ensure Indexes sesuai SkemaUserDanBuku.md
        # 1. Koleksi books
        _db.books.create_index([("isbn", ASCENDING)], unique=True)
        _db.books.create_index([("judul", ASCENDING)])
        _db.books.create_index([("kategori_id", ASCENDING)])
        _db.books.create_index([("aktif", ASCENDING)])
        
        # 2. Koleksi categories
        _db.categories.create_index([("slug", ASCENDING)], unique=True)
        
        # 3. Koleksi users
        _db.users.create_index([("username", ASCENDING)], unique=True)
        
        # 4. Koleksi transactions
        _db.transactions.create_index([("no_faktur", ASCENDING)], unique=True)
        _db.transactions.create_index([("created_at", ASCENDING)])
        
        _is_connected = True
        _connection_error = None
        print(f"[Database] Terhubung ke MongoDB Atlas: {DB_NAME}")
        return _db
    except Exception as e:
        _is_connected = False
        _connection_error = str(e)
        print(f"[Database] Koneksi gagal: {e}")
        return None

# Inisialisasi koneksi awal
init_db()

def get_db():
    global _db, _is_connected
    if _db is None or not _is_connected:
        init_db()
    return _db

def get_connection_status():
    global _is_connected, _connection_error
    return {
        "connected": _is_connected,
        "database": DB_NAME if _is_connected else None,
        "error": _connection_error
    }

def serialize_doc(doc, hide_password=True):
    """Serializes MongoDB BSON document to JSON-safe dictionary."""
    if doc is None:
        return None
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d["_id"])
        del d["_id"]
    if "kategori_id" in d and isinstance(d["kategori_id"], ObjectId):
        d["kategori_id"] = str(d["kategori_id"])
    if hide_password and "password_hash" in d:
        del d["password_hash"]
    for key, val in list(d.items()):
        if isinstance(val, ObjectId):
            d[key] = str(val)
        elif isinstance(val, datetime):
            d[key] = val.isoformat()
    return d

def serialize_docs(docs, hide_password=True):
    return [serialize_doc(doc, hide_password) for doc in docs]
