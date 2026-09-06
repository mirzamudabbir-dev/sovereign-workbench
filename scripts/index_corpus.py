#!/usr/bin/env python3
"""L6 — the local knowledge base connector (R10).

Walk a directory of the organisation's own documents (manuals, SOPs, correspondence),
ingest each one via core.ingest.ingest(), and index the resulting EvidenceSpans via
core.kb.index_spans(). Skips files unchanged since the last run (mtime + size, recorded
in a small SQLite table); --force reindexes everything regardless.

    python scripts/index_corpus.py --dir /srv/plant-docs --recursive
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path

from core.config import SETTINGS
from core.ingest import ingest
from core.kb import index_spans
from core.schemas import WorkbenchError

logger = logging.getLogger(__name__)

_SUPPORTED_SUFFIXES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp",
    ".docx", ".xlsx", ".pptx", ".txt", ".md",
}


def _stable_doc_id(path: Path) -> str:
    """core.ingest.ingest() assigns a random doc_id per call unless told otherwise —
    fine for one-off uploads, but this connector's whole "re-ingesting updates in place"
    promise (core/kb.py's point ids are deterministic *given a stable span_id*) depends
    on the same file always producing the same doc_id. Derive it from the resolved path
    instead of letting ingest() randomise it, keeping the doc's "slug + 4 hex" shape."""
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-") or "doc"
    digest = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:4]
    return f"{slug}-{digest}"


def _state_db_path() -> Path:
    return SETTINGS.paths.data / "index_corpus_state.sqlite3"


def _open_state_db() -> sqlite3.Connection:
    path = _state_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS indexed_files ("
        "  path TEXT PRIMARY KEY, mtime REAL NOT NULL, size INTEGER NOT NULL, doc_id TEXT NOT NULL"
        ")"
    )
    conn.commit()
    return conn


def _is_unchanged(conn: sqlite3.Connection, path: Path) -> bool:
    stat = path.stat()
    row = conn.execute("SELECT mtime, size FROM indexed_files WHERE path = ?", (str(path),)).fetchone()
    if row is None:
        return False
    mtime, size = row
    return mtime == stat.st_mtime and size == stat.st_size


def _record(conn: sqlite3.Connection, path: Path, doc_id: str) -> None:
    stat = path.stat()
    conn.execute(
        "INSERT INTO indexed_files (path, mtime, size, doc_id) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET mtime = excluded.mtime, size = excluded.size, doc_id = excluded.doc_id",
        (str(path), stat.st_mtime, stat.st_size, doc_id),
    )
    conn.commit()


def _iter_files(root: Path, recursive: bool):
    pattern = "**/*" if recursive else "*"
    for path in sorted(root.glob(pattern)):
        if path.is_file() and path.suffix.lower() in _SUPPORTED_SUFFIXES:
            yield path


def _print_summary(rows: list[tuple[str, str, int]], total_spans: int) -> None:
    name_w = max((len(r[0]) for r in rows), default=len("file"))
    status_w = max((len(r[1]) for r in rows), default=len("status"))
    rule = "-" * (name_w + status_w + len("spans") + 6)
    print(rule)
    print(f"{'file':<{name_w}}  {'status':<{status_w}}  spans")
    print(rule)
    for name, status, count in rows:
        print(f"{name:<{name_w}}  {status:<{status_w}}  {count}")
    print(rule)
    print(f"total spans indexed this run: {total_spans}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path, help="directory to walk")
    parser.add_argument("--recursive", action="store_true", help="walk subdirectories too")
    parser.add_argument("--force", action="store_true", help="reindex even unchanged files")
    args = parser.parse_args(argv)

    root: Path = args.dir
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1

    conn = _open_state_db()
    files = list(_iter_files(root, args.recursive))
    rows: list[tuple[str, str, int]] = []
    total_spans = 0

    for i, path in enumerate(files, start=1):
        if not args.force and _is_unchanged(conn, path):
            print(f"[{i}/{len(files)}] {path.name}: unchanged, skipping")
            rows.append((path.name, "skipped (unchanged)", 0))
            continue

        print(f"[{i}/{len(files)}] {path.name}: ingesting...")
        t0 = time.monotonic()
        try:
            ref, spans = ingest(path, doc_id=_stable_doc_id(path))
            count = index_spans(spans, ref)
            _record(conn, path, ref.doc_id)
            elapsed = time.monotonic() - t0
            print(f"[{i}/{len(files)}] {path.name}: indexed {count} spans as {ref.doc_id} ({elapsed:.1f}s)")
            rows.append((path.name, f"indexed ({ref.doc_id})", count))
            total_spans += count
        except WorkbenchError as exc:
            print(f"[{i}/{len(files)}] {path.name}: FAILED — {exc}", file=sys.stderr)
            rows.append((path.name, "FAILED", 0))

    conn.close()

    if not rows:
        print(f"no supported files found under {root} (recursive={args.recursive})")
        return 0

    print()
    _print_summary(rows, total_spans)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
