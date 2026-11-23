"""Resource-limited document parser worker.

The child returns JSON bytes rather than a pickled Python object. This avoids
unpickling data produced by a process that handles attacker-controlled files.
The worker is process-isolated and resource-limited, but is not an OS/container
sandbox; keep public routes disabled until deployment isolation is reviewed.
"""
import json
import multiprocessing
import os
import time

try:
    import resource
except ImportError:  # pragma: no cover - the production target is Linux
    resource = None

from iskra.documents.parsers import (
    MAX_UPLOAD_BYTES,
    ParsedDocument,
    parse_document,
)


MAX_WORKER_RESULT_BYTES = 8 * 1024 * 1024


def _apply_worker_limits(cpu_seconds, memory_limit_bytes):
    if resource is None:
        raise RuntimeError("Resource limits are unavailable on this platform")
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))


def _worker_entry(connection, filename, data, cpu_seconds, memory_limit_bytes):
    try:
        _apply_worker_limits(cpu_seconds, memory_limit_bytes)
        parsed = parse_document(filename, data)
        payload = {
            "ok": True,
            "filename": parsed.filename,
            "extension": parsed.extension,
            "sha256": parsed.sha256,
            "chunks": list(parsed.chunks),
        }
    except ValueError as exc:
        payload = {"ok": False, "kind": "invalid_document", "message": str(exc)}
    except Exception:
        payload = {
            "ok": False,
            "kind": "worker_error",
            "message": "Dokument nie mógł zostać bezpiecznie przetworzony.",
        }
    try:
        connection.send_bytes(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
    except (BrokenPipeError, OSError):
        pass
    finally:
        connection.close()


def parse_document_isolated(
    filename,
    data,
    timeout_seconds=15,
    cpu_seconds=10,
    memory_limit_bytes=512 * 1024 * 1024,
):
    """Parse an upload in a spawned process with hard resource limits."""
    if resource is None or os.name != "posix":
        raise RuntimeError("Izolowany parser wymaga systemu POSIX z resource limits")
    if not isinstance(data, bytes) or not data or len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Nieprawidłowy rozmiar pliku wejściowego")
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not 1 <= timeout_seconds <= 60):
        raise ValueError("timeout_seconds musi należeć do zakresu 1..60")
    if (isinstance(cpu_seconds, bool) or not isinstance(cpu_seconds, int)
            or not 1 <= cpu_seconds <= 30):
        raise ValueError("cpu_seconds musi należeć do zakresu 1..30")
    if (isinstance(memory_limit_bytes, bool) or not isinstance(memory_limit_bytes, int)
            or not 128 * 1024 * 1024 <= memory_limit_bytes <= 2 * 1024 * 1024 * 1024):
        raise ValueError("memory_limit_bytes musi należeć do zakresu 128 MiB..2 GiB")

    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker_entry,
        args=(child_connection, filename, data, cpu_seconds, memory_limit_bytes),
        name="iskra-document-parser",
        daemon=True,
    )
    started = False
    try:
        process.start()
        started = True
        child_connection.close()
        if not parent_connection.poll(timeout_seconds):
            process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
            raise TimeoutError("Przekroczono limit czasu przetwarzania dokumentu")
        try:
            raw = parent_connection.recv_bytes(maxlength=MAX_WORKER_RESULT_BYTES)
        except (EOFError, OSError) as exc:
            raise RuntimeError("Proces parsera zakończył się bez poprawnego wyniku") from exc
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            message = payload.get("message") if isinstance(payload, dict) else None
            kind = payload.get("kind") if isinstance(payload, dict) else None
            if kind == "invalid_document":
                raise ValueError(message or "Nieprawidłowy dokument")
            raise RuntimeError(message or "Błąd izolowanego parsera")
        if (set(payload) != {"ok", "filename", "extension", "sha256", "chunks"}
                or not isinstance(payload["filename"], str)
                or not isinstance(payload["extension"], str)
                or not isinstance(payload["sha256"], str)
                or not isinstance(payload["chunks"], list)
                or not payload["chunks"]
                or any(not isinstance(chunk, str) for chunk in payload["chunks"])):
            raise RuntimeError("Parser zwrócił nieprawidłową strukturę wyniku")
        return ParsedDocument(
            filename=payload["filename"],
            extension=payload["extension"],
            sha256=payload["sha256"],
            chunks=tuple(payload["chunks"]),
        )
    except (ValueError, TimeoutError, RuntimeError):
        raise
    except Exception as exc:
        raise RuntimeError("Nie można uruchomić izolowanego parsera") from exc
    finally:
        parent_connection.close()
        if not started:
            child_connection.close()
        if started:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
