"""Shared helpers for the Election Desk pollers.

Layer discipline (non-negotiable): polls, ratings, early_vote, results, calls and
scenarios are separate files/directories and never write into each other. Every
pull is an append-only snapshot with a raw payload hash. Nothing is overwritten.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
LAYERS = ("polls", "ratings", "early_vote", "results", "calls", "scenarios")

USER_AGENT = "election-desk-2026/0.1 (public results desk; contact info@ganttformichigan.com)"


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    os.replace(tmp, path)


def append_jsonl(path, record: dict):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def sources() -> dict:
    return {s["id"]: s for s in load_json(os.path.join(DATA, "sources.json"), {"sources": []})["sources"]}


class RateLimiter:
    """Per-source minimum spacing between requests, in seconds."""

    def __init__(self):
        self.last: dict[str, float] = {}

    def wait(self, source_id: str, min_interval_s: float):
        now = time.monotonic()
        prev = self.last.get(source_id)
        if prev is not None and now - prev < min_interval_s:
            time.sleep(min_interval_s - (now - prev))
        self.last[source_id] = time.monotonic()


def record_snapshot(source_id: str, layer: str, raw: bytes, parse_status: str, keep_raw: bool = True, note: str = "") -> dict:
    """Append a snapshot record. Raw payloads are stored gzip'd under data/raw/<source>/<hash12>.gz,
    deduplicated by hash, so an unchanged payload costs nothing beyond the index row."""
    assert layer in LAYERS, layer
    h = sha256_bytes(raw)
    fetched_at = utcnow()
    raw_path = None
    if keep_raw:
        rel = os.path.join("data", "raw", source_id, h[:12] + ".gz")
        full = os.path.join(ROOT, rel)
        if not os.path.exists(full):
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with gzip.open(full, "wb") as fh:
                fh.write(raw)
        raw_path = rel
    snap = {
        "id": f"{source_id}:{fetched_at}:{h[:12]}",
        "source_id": source_id,
        "layer": layer,
        "fetched_at": fetched_at,
        "raw_hash": h,
        "raw_bytes": len(raw),
        "parse_status": parse_status,
        "raw_path": raw_path,
        "note": note,
    }
    append_jsonl(os.path.join(DATA, "snapshots", "index.jsonl"), snap)
    return snap


def last_snapshot_hash(source_id: str) -> str | None:
    rows = [r for r in read_jsonl(os.path.join(DATA, "snapshots", "index.jsonl")) if r["source_id"] == source_id]
    return rows[-1]["raw_hash"] if rows else None


def ops_log(event: str, **kw):
    rec = {"at": utcnow(), "event": event}
    rec.update(kw)
    append_jsonl(os.path.join(DATA, "ops_log.jsonl"), rec)


def update_source_health(source_id: str, ok: bool, error: str = ""):
    path = os.path.join(DATA, "sources.json")
    doc = load_json(path, {"sources": []})
    for s in doc["sources"]:
        if s["id"] == source_id:
            if ok:
                s["last_success_at"] = utcnow()
                s["last_error"] = ""
            else:
                s["last_error"] = f"{utcnow()} {error}"[:500]
    dump_json(path, doc)
