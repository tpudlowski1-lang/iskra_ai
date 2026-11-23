"""Tenant-isolated document ingestion and lexical retrieval for Iskra AI.

Each company receives a high-entropy API key. Only its SHA-256 digest is stored.
Every document/chunk query is constrained by the authenticated tenant ID.
"""
import hashlib
import io
import json
import math
import os
import re
import secrets
import sqlite3
import time
import uuid
import threading
import zipfile
from contextlib import closing
from xml.etree import ElementTree
from werkzeug.utils import secure_filename

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_CHARS = 1_500_000
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".docx"}
_INITIALIZED_PATHS = {}
_INIT_LOCK = threading.Lock()


def _connect(db_path):
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def initialize(db_path):
    normalized_path = os.path.abspath(db_path)
    try:
        current_inode = os.stat(normalized_path).st_ino
    except OSError:
        current_inode = None
    if current_inode is not None and _INITIALIZED_PATHS.get(normalized_path) == current_inode:
        return
    with _INIT_LOCK:
        try:
            current_inode = os.stat(normalized_path).st_ino
        except OSError:
            current_inode = None
        if current_inode is not None and _INITIALIZED_PATHS.get(normalized_path) == current_inode:
            return
        with closing(_connect(normalized_path)) as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS tenants (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    api_key_hash TEXT NOT NULL UNIQUE,
                    created_at REAL NOT NULL
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    filename TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(tenant_id, sha256)
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS document_chunks (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    embedding_json TEXT,
                    UNIQUE(document_id, chunk_index)
                )
            """)
            connection.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts
                USING fts5(chunk_id UNINDEXED, tenant_id UNINDEXED,
                           document_id UNINDEXED, filename UNINDEXED,
                           content, tokenize='unicode61')
            """)
            chunk_columns = {row[1] for row in connection.execute("PRAGMA table_info(document_chunks)")}
            if "embedding_json" not in chunk_columns:
                connection.execute("ALTER TABLE document_chunks ADD COLUMN embedding_json TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_documents_tenant ON documents(tenant_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_chunks_tenant ON document_chunks(tenant_id)")
            connection.commit()
            _INITIALIZED_PATHS[normalized_path] = os.stat(normalized_path).st_ino


def _key_hash(api_key):
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def create_tenant(db_path, name):
    name = str(name or "").strip()
    if not name or len(name) > 120:
        raise ValueError("Nazwa firmy musi mieć od 1 do 120 znaków.")
    initialize(db_path)
    tenant_id = str(uuid.uuid4())
    api_key = "isk_" + secrets.token_urlsafe(36)
    with closing(_connect(db_path)) as connection:
        connection.execute(
            "INSERT INTO tenants(id, name, api_key_hash, created_at) VALUES (?, ?, ?, ?)",
            (tenant_id, name, _key_hash(api_key), time.time()),
        )
        connection.commit()
    return {"tenant_id": tenant_id, "name": name, "api_key": api_key}


def authenticate_tenant_key(db_path, api_key):
    if not api_key or len(api_key) > 256:
        return None
    initialize(db_path)
    with closing(_connect(db_path)) as connection:
        row = connection.execute(
            "SELECT id FROM tenants WHERE api_key_hash = ?", (_key_hash(api_key),)
        ).fetchone()
    return row["id"] if row else None


def list_documents(db_path, tenant_id):
    initialize(db_path)
    with closing(_connect(db_path)) as connection:
        rows = connection.execute("""
            SELECT id, filename, extension, created_at
            FROM documents WHERE tenant_id = ?
            ORDER BY created_at DESC
        """, (tenant_id,)).fetchall()
    return [dict(row) for row in rows]


def _extract_text(filename, data):
    extension = os.path.splitext(filename.lower())[1]
    if extension == ".txt":
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode("cp1250")
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Brak biblioteki pypdf — zainstaluj zależności projektu.") from exc
        reader = PdfReader(io.BytesIO(data), strict=False)
        if len(reader.pages) > 200:
            raise ValueError("PDF przekracza limit 200 stron.")
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    if extension == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                info = archive.getinfo("word/document.xml")
                if info.file_size > MAX_EXTRACTED_CHARS * 4:
                    raise ValueError("Dokument DOCX jest zbyt duży po rozpakowaniu.")
                xml_data = archive.read("word/document.xml")
            root = ElementTree.fromstring(xml_data)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            paragraphs = []
            for paragraph in root.findall(".//w:p", ns):
                text = "".join(node.text or "" for node in paragraph.findall(".//w:t", ns))
                if text.strip():
                    paragraphs.append(text)
            return "\n".join(paragraphs)
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise ValueError("Nieprawidłowy plik DOCX.") from exc
    raise ValueError("Dozwolone formaty: PDF, DOCX i TXT.")


def _chunk_text(text):
    normalized = re.sub(r"[\t\r\f\v]+", " ", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        raise ValueError("Dokument nie zawiera tekstu możliwego do indeksowania.")
    if len(normalized) > MAX_EXTRACTED_CHARS:
        raise ValueError("Wyodrębniony tekst przekracza limit 1,5 mln znaków.")
    chunks = []
    start = 0
    while start < len(normalized):
        end = min(start + CHUNK_SIZE, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + CHUNK_SIZE // 2, end)
            if boundary > start:
                end = boundary
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(normalized):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def add_document(db_path, tenant_id, filename, data, embedding_fn=None):
    if not isinstance(data, bytes) or not data:
        raise ValueError("Plik jest pusty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Plik przekracza limit 8 MB.")
    safe_name = secure_filename(os.path.basename(filename or ""))
    extension = os.path.splitext(safe_name.lower())[1]
    if not safe_name or extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Dozwolone formaty: PDF, DOCX i TXT.")
    extracted = _extract_text(safe_name, data)
    chunks = _chunk_text(extracted)
    embeddings = None
    if embedding_fn:
        try:
            candidate = embedding_fn(chunks)
            if isinstance(candidate, list) and len(candidate) == len(chunks):
                normalized = []
                dimension = None
                for vector in candidate:
                    if not isinstance(vector, (list, tuple)) or not vector:
                        raise ValueError("Invalid embedding vector")
                    values = [float(value) for value in vector]
                    if not all(math.isfinite(value) for value in values):
                        raise ValueError("Non-finite embedding value")
                    if dimension is None:
                        dimension = len(values)
                    if len(values) != dimension:
                        raise ValueError("Embedding dimensions do not match")
                    normalized.append(values)
                embeddings = normalized
        except Exception as exc:
            print(f"Embedding: indeksowanie semantyczne pominięte ({type(exc).__name__}).")
    digest = hashlib.sha256(data).hexdigest()
    document_id = str(uuid.uuid4())
    initialize(db_path)
    with closing(_connect(db_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        tenant = connection.execute("SELECT 1 FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        if not tenant:
            connection.rollback()
            raise ValueError("Nieznana firma.")
        existing = connection.execute(
            "SELECT id FROM documents WHERE tenant_id=? AND sha256=?", (tenant_id, digest)
        ).fetchone()
        if existing:
            connection.commit()
            return {"document_id": existing["id"], "filename": safe_name,
                    "chunks": 0, "duplicate": True}
        connection.execute("""
            INSERT INTO documents(id, tenant_id, filename, extension, sha256, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (document_id, tenant_id, safe_name, extension, digest, time.time()))
        for index, content in enumerate(chunks):
            chunk_id = str(uuid.uuid4())
            connection.execute("""
                INSERT INTO document_chunks(id, tenant_id, document_id, chunk_index, content, embedding_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                chunk_id, tenant_id, document_id, index, content,
                json.dumps(embeddings[index], separators=(",", ":")) if embeddings else None,
            ))
            connection.execute("""
                INSERT INTO document_chunks_fts(chunk_id, tenant_id, document_id, filename, content)
                VALUES (?, ?, ?, ?, ?)
            """, (chunk_id, tenant_id, document_id, safe_name, content))
        connection.commit()
    return {"document_id": document_id, "filename": safe_name,
            "chunks": len(chunks), "duplicate": False}


def _cosine_similarity(left, right):
    if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)) or len(left) != len(right) or not left:
        return None
    try:
        a = [float(value) for value in left]
        b = [float(value) for value in right]
        if not all(math.isfinite(value) for value in a + b):
            return None
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if not norm_a or not norm_b:
            return None
        return dot / (norm_a * norm_b)
    except (TypeError, ValueError, OverflowError):
        return None


def search_documents(db_path, tenant_id, query, limit=5, embedding_fn=None):
    query = str(query or "").strip()
    if not query or len(query) > 1000:
        raise ValueError("Zapytanie musi mieć od 1 do 1000 znaków.")
    terms = re.findall(r"[\w]{2,}", query, flags=re.UNICODE)[:20]
    match_query = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
    max_results = max(1, min(int(limit), 10))
    initialize(db_path)
    lexical_rows = []
    semantic_rows = []
    with closing(_connect(db_path)) as connection:
        if match_query:
            lexical_rows = connection.execute("""
                SELECT c.id AS chunk_id, f.document_id, f.filename, f.content,
                       c.chunk_index, bm25(document_chunks_fts) AS score
                FROM document_chunks_fts AS f
                JOIN document_chunks AS c ON c.id = f.chunk_id
                WHERE document_chunks_fts MATCH ? AND f.tenant_id = ?
                ORDER BY score
                LIMIT ?
            """, (match_query, tenant_id, max_results * 4)).fetchall()
        query_vector = None
        if embedding_fn:
            try:
                query_vector = embedding_fn(query)
            except Exception as exc:
                print(f"Embedding: wyszukiwanie semantyczne pominięte ({type(exc).__name__}).")
        if isinstance(query_vector, (list, tuple)) and query_vector:
            rows = connection.execute("""
                SELECT c.id AS chunk_id, c.document_id, d.filename, c.content,
                       c.chunk_index, c.embedding_json
                FROM document_chunks AS c
                JOIN documents AS d ON d.id = c.document_id
                WHERE c.tenant_id = ? AND c.embedding_json IS NOT NULL
                ORDER BY d.created_at DESC
                LIMIT 5000
            """, (tenant_id,)).fetchall()
            for row in rows:
                try:
                    vector = json.loads(row["embedding_json"])
                except (TypeError, ValueError):
                    continue
                score = _cosine_similarity(query_vector, vector)
                if score is not None:
                    semantic_rows.append((score, row))
    fused = {}
    metadata = {}
    for rank, row in enumerate(lexical_rows, start=1):
        fused[row["chunk_id"]] = fused.get(row["chunk_id"], 0.0) + 1.0 / (60 + rank)
        metadata[row["chunk_id"]] = row
    semantic_rows.sort(key=lambda item: item[0], reverse=True)
    for rank, (_, row) in enumerate(semantic_rows[:max_results * 4], start=1):
        fused[row["chunk_id"]] = fused.get(row["chunk_id"], 0.0) + 1.0 / (60 + rank)
        metadata[row["chunk_id"]] = row
    ranked = sorted(fused, key=fused.get, reverse=True)[:max_results]
    return [{
        "document_id": metadata[chunk_id]["document_id"],
        "filename": metadata[chunk_id]["filename"],
        "chunk_index": metadata[chunk_id]["chunk_index"],
        "excerpt": metadata[chunk_id]["content"][:1200],
    } for chunk_id in ranked]


def delete_document(db_path, tenant_id, document_id):
    initialize(db_path)
    with closing(_connect(db_path)) as connection:
        row = connection.execute(
            "SELECT id FROM documents WHERE id=? AND tenant_id=?", (document_id, tenant_id)
        ).fetchone()
        if not row:
            return False
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM document_chunks_fts WHERE document_id=? AND tenant_id=?",
                           (document_id, tenant_id))
        connection.execute("DELETE FROM documents WHERE id=? AND tenant_id=?",
                           (document_id, tenant_id))
        connection.commit()
    return True


def list_tenants(db_path):
    initialize(db_path)
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            "SELECT id, name, created_at FROM tenants ORDER BY created_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def rotate_tenant_key(db_path, tenant_id):
    initialize(db_path)
    api_key = "isk_" + secrets.token_urlsafe(36)
    with closing(_connect(db_path)) as connection:
        cursor = connection.execute(
            "UPDATE tenants SET api_key_hash=? WHERE id=?",
            (_key_hash(api_key), tenant_id),
        )
        connection.commit()
    return api_key if cursor.rowcount else None


def delete_tenant(db_path, tenant_id):
    initialize(db_path)
    with closing(_connect(db_path)) as connection:
        exists = connection.execute("SELECT 1 FROM tenants WHERE id=?", (tenant_id,)).fetchone()
        if not exists:
            return False
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM document_chunks_fts WHERE tenant_id=?", (tenant_id,))
        connection.execute("DELETE FROM tenants WHERE id=?", (tenant_id,))
        connection.commit()
    return True
