"""Bounded parsers for untrusted tenant documents.

This module is intentionally not exposed through HTTP until a resource-limited
parser worker and the remaining operational controls are in place.
"""
from dataclasses import dataclass
import hashlib
import io
import os
import re
import zipfile
from pathlib import PurePosixPath

from defusedxml.ElementTree import fromstring as safe_xml_fromstring
from werkzeug.utils import secure_filename


MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_EXTRACTED_CHARS = 1_500_000
MAX_PDF_PAGES = 100
MAX_PDF_PAGE_CHARS = 100_000
MAX_DOCX_ENTRIES = 256
MAX_DOCX_TOTAL_UNCOMPRESSED = 12 * 1024 * 1024
MAX_DOCX_XML_BYTES = 8 * 1024 * 1024
MAX_DOCX_COMPRESSION_RATIO = 100
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
MAX_CHUNKS = 2000
ALLOWED_EXTENSIONS = frozenset({".txt", ".pdf", ".docx"})


@dataclass(frozen=True)
class ParsedDocument:
    filename: str
    extension: str
    sha256: str
    chunks: tuple[str, ...]


def _safe_filename(filename):
    raw = str(filename or "").replace("\\", "/")
    safe = secure_filename(os.path.basename(raw))
    if not safe or safe in {".", ".."}:
        raise ValueError("Nieprawidłowa nazwa pliku.")
    extension = os.path.splitext(safe.lower())[1]
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("Dozwolone formaty: PDF, DOCX i TXT.")
    return safe, extension


def _decode_text(data):
    if b"\x00" in data:
        raise ValueError("Plik tekstowy zawiera niedozwolone bajty NUL.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp1250")
        except UnicodeDecodeError as exc:
            raise ValueError("Plik tekstowy nie jest poprawnym UTF-8 ani CP1250.") from exc
    if not text.strip():
        raise ValueError("Dokument nie zawiera tekstu.")
    control_count = sum(1 for char in text if ord(char) < 32 and char not in "\n\r\t\f")
    if control_count / max(1, len(text)) > 0.01:
        raise ValueError("Plik tekstowy zawiera zbyt wiele znaków sterujących.")
    return text


def _extract_pdf(data):
    if not data.startswith(b"%PDF-"):
        raise ValueError("Zawartość pliku nie odpowiada formatowi PDF.")
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            raise ValueError("Zaszyfrowane pliki PDF nie są obsługiwane.")
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise ValueError(f"PDF przekracza limit {MAX_PDF_PAGES} stron.")
        parts = []
        total_chars = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if len(page_text) > MAX_PDF_PAGE_CHARS:
                raise ValueError("Strona PDF przekracza limit wyodrębnionego tekstu.")
            total_chars += len(page_text)
            if total_chars > MAX_EXTRACTED_CHARS:
                raise ValueError("PDF przekracza limit wyodrębnionego tekstu.")
            parts.append(page_text)
        return "\n".join(parts)
    except ValueError:
        raise
    except Exception as exc:
        # Do not return parser internals or file content to the caller.
        raise ValueError("Nie można bezpiecznie odczytać pliku PDF.") from exc


def _validate_docx_archive(archive):
    entries = archive.infolist()
    if not entries or len(entries) > MAX_DOCX_ENTRIES:
        raise ValueError("Archiwum DOCX ma nieprawidłową liczbę elementów.")
    names = set()
    total_size = 0
    document_xml = None
    for info in entries:
        name = info.filename
        path = PurePosixPath(name)
        if (not name or name in names or path.is_absolute()
                or ".." in path.parts or "\\" in name):
            raise ValueError("Archiwum DOCX zawiera niebezpieczną ścieżkę.")
        names.add(name)
        if info.flag_bits & 0x1:
            raise ValueError("Zaszyfrowane archiwa DOCX nie są obsługiwane.")
        if info.file_size < 0 or info.compress_size < 0:
            raise ValueError("Archiwum DOCX zawiera nieprawidłowe rozmiary.")
        total_size += info.file_size
        if total_size > MAX_DOCX_TOTAL_UNCOMPRESSED:
            raise ValueError("Archiwum DOCX przekracza limit rozmiaru po rozpakowaniu.")
        if info.file_size and (
            info.compress_size == 0
            or info.file_size / info.compress_size > MAX_DOCX_COMPRESSION_RATIO
        ):
            raise ValueError("Archiwum DOCX przekracza limit kompresji.")
        if name == "word/document.xml":
            document_xml = info
    if document_xml is None or document_xml.file_size > MAX_DOCX_XML_BYTES:
        raise ValueError("Archiwum DOCX nie zawiera poprawnego document.xml.")
    return document_xml


def _extract_docx(data):
    if not data.startswith(b"PK\x03\x04"):
        raise ValueError("Zawartość pliku nie odpowiada formatowi DOCX.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = _validate_docx_archive(archive)
            xml_data = archive.read(info)
        root = safe_xml_fromstring(
            xml_data,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Nie można bezpiecznie odczytać pliku DOCX.") from exc

    paragraphs = []
    total_chars = 0
    for paragraph in root.iter():
        if not str(paragraph.tag).endswith("}p"):
            continue
        text = "".join(
            node.text or ""
            for node in paragraph.iter()
            if str(node.tag).endswith("}t")
        )
        if text:
            total_chars += len(text)
            if total_chars > MAX_EXTRACTED_CHARS:
                raise ValueError("DOCX przekracza limit wyodrębnionego tekstu.")
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _normalize_and_chunk(text):
    normalized = re.sub(r"[\t\r\f\v]+", " ", text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        raise ValueError("Dokument nie zawiera tekstu możliwego do indeksowania.")
    if len(normalized) > MAX_EXTRACTED_CHARS:
        raise ValueError("Wyodrębniony tekst przekracza limit.")
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
            if len(chunks) > MAX_CHUNKS:
                raise ValueError("Dokument generuje zbyt wiele fragmentów.")
        if end >= len(normalized):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return tuple(chunks)


def parse_document(filename, data):
    """Validate and parse a bounded PDF, DOCX or TXT document."""
    if not isinstance(data, bytes) or not data:
        raise ValueError("Plik jest pusty lub ma nieprawidłowy typ.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Plik przekracza limit 8 MiB.")
    safe_name, extension = _safe_filename(filename)
    if extension == ".txt":
        extracted = _decode_text(data)
    elif extension == ".pdf":
        extracted = _extract_pdf(data)
    else:
        extracted = _extract_docx(data)
    chunks = _normalize_and_chunk(extracted)
    return ParsedDocument(
        filename=safe_name,
        extension=extension,
        sha256=hashlib.sha256(data).hexdigest(),
        chunks=chunks,
    )
