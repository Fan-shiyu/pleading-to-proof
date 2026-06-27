"""Stage 1 orchestrator.

Loop the registry -> extract -> dispatch to the per-type parser -> validate ->
self-check the five canonical spot-check chunks -> only then write chunks.json
and chunk_stats.json. The self-check is the quality gate before Stage 2.

Run with UTF-8 console so spot-checks render £/—/' correctly:
    PYTHONUTF8=1 ./.venv/Scripts/python.exe build_chunks.py
"""

import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
import statistics

from config import paths
from lib.parsers import PARSERS

CHUNKS_FILE = paths.CHUNKS
STATS_FILE = paths.CHUNK_STATS
REGISTRY_FILE = paths.REGISTRY

# Load the case registry from JSON at runtime, so a new case can swap in a new
# registry.json without touching Python. document_registry.py remains the
# human-readable reference / source of truth. Keys beginning with "_" (e.g.
# "_note") are metadata, not documents, and are skipped when building chunks.
with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
    DOCUMENT_REGISTRY = json.load(f)


# --------------------------------------------------------------------------- #
# Validation (verbatim from the Stage 1 spec)
# --------------------------------------------------------------------------- #

def validate_chunks(chunks):
    warnings = []
    for chunk in chunks:
        # Rule 1: No evidence chunk should have empty chunk_text
        if chunk["is_evidence"] and not chunk["chunk_text"].strip():
            warnings.append(f"EMPTY CHUNK: {chunk['chunk_id']}")
        # Rule 2: No chunk shorter than 30 tokens
        if chunk["token_count"] < 30:
            warnings.append(f"TOO SHORT ({chunk['token_count']} tokens): {chunk['chunk_id']}")
        # Rule 3: No chunk longer than 512 tokens
        if chunk["token_count"] > 512:
            warnings.append(f"TOO LONG ({chunk['token_count']} tokens): {chunk['chunk_id']}")
        # Rule 4: Every chunk must have a non-empty citation string
        if not chunk.get("citation"):
            warnings.append(f"MISSING CITATION: {chunk['chunk_id']}")
        # Rule 5: Pleadings chunks must not be in the evidence store
        if chunk["doc_type"] == "pleading" and chunk["is_evidence"]:
            warnings.append(f"PLEADING IN EVIDENCE STORE: {chunk['chunk_id']}")
        # Rule 6: Defect log chunks must have cause_attribution
        if chunk["doc_type"] == "defect_log" and not chunk.get("cause_attribution"):
            warnings.append(f"MISSING CAUSE ATTRIBUTION: {chunk['chunk_id']}")
    return warnings


def is_blocking(warning):
    """Rules 1, 4, 5, 6 block; Rules 2/3 (too short/long) are warnings only."""
    return warning.startswith((
        "EMPTY CHUNK", "MISSING CITATION",
        "PLEADING IN EVIDENCE STORE", "MISSING CAUSE ATTRIBUTION",
    ))


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def build_all_chunks():
    all_chunks = []
    for doc_id, doc_meta in DOCUMENT_REGISTRY.items():
        if doc_id.startswith("_"):   # skip metadata keys like "_note"
            continue
        parser = PARSERS[doc_meta["doc_type"]]
        chunks = parser(doc_id, doc_meta)
        all_chunks.extend(chunks)
    return all_chunks


def compute_stats(chunks, warnings):
    by_type = {}
    for c in chunks:
        by_type.setdefault(c["doc_type"], []).append(c["token_count"])
    per_type = {}
    for dt, tokens in sorted(by_type.items()):
        per_type[dt] = {
            "count": len(tokens),
            "min_tokens": min(tokens),
            "max_tokens": max(tokens),
            "avg_tokens": round(statistics.mean(tokens), 1),
        }
    evidence = [c for c in chunks if c["is_evidence"]]
    return {
        "total_chunks": len(chunks),
        "evidence_chunks": len(evidence),
        "non_evidence_chunks": len(chunks) - len(evidence),
        "by_doc_type": per_type,
        "warnings": warnings,
    }


# --------------------------------------------------------------------------- #
# Self-check spot-checks
# --------------------------------------------------------------------------- #

def find_one(chunks, predicate):
    for c in chunks:
        if predicate(c):
            return c
    return None


SPOT_CHECKS = [
    ("MSA clause 14.1",
     lambda c: c["doc_id"] == "TAB03" and c.get("clause_number") == "14.1"),
    ("Vance WS para 4",
     lambda c: c["doc_id"] == "TAB16" and c.get("paragraph_number") == 4),
    ("Whitfield Expert Report para 3",
     lambda c: c["doc_id"] == "TAB19" and c.get("paragraph_number") == 3),
    ("TAB09 email 1 (Reilly deferral)",
     lambda c: c["doc_id"] == "TAB09" and c.get("email_position") == 1),
    ("Defect Log D-003",
     lambda c: c["doc_id"] == "TAB13" and c.get("defect_id") == "D-003"),
]


def run_spot_checks(chunks):
    print("\n=== SPOT-CHECKS ===")
    all_ok = True
    for label, pred in SPOT_CHECKS:
        c = find_one(chunks, pred)
        if c is None:
            print(f"  [MISSING] {label}")
            all_ok = False
            continue
        ok = bool(c.get("citation")) and c["token_count"] > 0 and c["chunk_text"].strip()
        flag = "OK" if ok else "MALFORMED"
        if not ok:
            all_ok = False
        print(f"  [{flag}] {label}")
        print(f"      chunk_id   : {c['chunk_id']}")
        print(f"      citation   : {c['citation']}")
        print(f"      token_count: {c['token_count']}")
        print(f"      text[:100] : {c['chunk_text'][:100]!r}")
    return all_ok


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    chunks = build_all_chunks()
    warnings = validate_chunks(chunks)
    stats = compute_stats(chunks, warnings)

    print("=== CHUNK STATS ===")
    print(f"Total chunks      : {stats['total_chunks']}")
    print(f"Evidence chunks   : {stats['evidence_chunks']}  (expected ~88–116)")
    print(f"Non-evidence      : {stats['non_evidence_chunks']}  (pleadings)")
    print("\nBy document type:")
    for dt, s in stats["by_doc_type"].items():
        print(f"  {dt:18s} count={s['count']:3d}  "
              f"min={s['min_tokens']:4d}  max={s['max_tokens']:4d}  avg={s['avg_tokens']}")

    blocking = [w for w in warnings if is_blocking(w)]
    non_blocking = [w for w in warnings if not is_blocking(w)]
    print(f"\nWarnings: {len(warnings)} total "
          f"({len(blocking)} blocking, {len(non_blocking)} non-blocking)")
    for w in blocking:
        print(f"  [BLOCK] {w}")
    for w in non_blocking:
        print(f"  [warn]  {w}")

    spot_ok = run_spot_checks(chunks)

    print("\n=== GATE ===")
    if blocking:
        print(f"BLOCKED: {len(blocking)} blocking validation violation(s). "
              f"Fix parser(s) before writing outputs. Not proceeding to Stage 2.")
        return
    if not spot_ok:
        print("BLOCKED: one or more spot-check chunks missing/malformed. "
              "Fix parser(s) before writing outputs.")
        return

    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"PASSED: wrote {CHUNKS_FILE} ({len(chunks)} chunks) and {STATS_FILE}.")


if __name__ == "__main__":
    main()
