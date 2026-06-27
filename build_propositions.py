"""Stage 2 — Proposition Extraction.

Turns chunks.json (Stage 1) into propositions.json.

Run behaviour (per spec):
  1. Load chunks.json.
  2. Auto-detect Mode A (pleadings present) vs Mode B (no pleadings).
  3. Embedding step (always) -> chunks_with_embeddings.json.
  4. Mode A: one Gemini extraction over the pleadings -> validate -> propositions.json.
     Mode B: UMAP -> HDBSCAN -> per-cluster Gemini inference -> propositions.json
             -> cross-check vs Mode A -> mode_b_validation.json.
  5. Print completion summary.

LLM: Gemini gemini-2.0-flash via google-generativeai, key from GEMINI_API_KEY.

Run with UTF-8 console:
    PYTHONUTF8=1 ./.venv/Scripts/python.exe build_propositions.py
"""

import json
import os

import numpy as np
from dotenv import load_dotenv

CHUNKS_FILE = "chunks.json"
EMBEDDINGS_FILE = "chunks_with_embeddings.json"
PROPOSITIONS_FILE = "propositions.json"
MODE_B_VALIDATION_FILE = "mode_b_validation.json"

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
# Spec named gemini-2.0-flash, but that model now returns 404 (retired for
# generateContent). gemini-2.5-flash is its current stable successor.
GEMINI_MODEL_NAME = "gemini-2.5-flash"

# The 11 permitted legal_element_type values.
ELEMENT_TYPES = [
    "formation", "scope_change", "timetable", "go_live_decision", "acceptance",
    "platform_defects", "availability", "training", "misrepresentation",
    "loss_wasted_expenditure", "loss_of_profit",
]

# Fixed importance-weight table (authoritative; assigned in code).
IMPORTANCE = {
    "platform_defects": 1.0,
    "availability": 1.0,
    "acceptance": 0.95,
    "loss_of_profit": 0.95,
    "misrepresentation": 0.90,
    "go_live_decision": 0.85,
    "scope_change": 0.85,
    "timetable": 0.75,
    "loss_wasted_expenditure": 0.75,
    "formation": 0.60,
    "training": 0.50,
}

MODE_A_SYSTEM_PROMPT = """You are a legal analyst extracting propositions from court pleadings.
Extract each numbered paragraph from the Particulars of Claim provided.
Return ONLY a valid JSON array with no preamble, explanation, or markdown formatting.

Each object must have exactly these fields:
- proposition_id: string e.g. "p1", "p2", "p15a", "p15b"
- allegation_number: string e.g. "1", "9", "15a"
- text: verbatim paragraph text, preserving all wording exactly
- legal_element_type: one of: formation | scope_change | timetable | go_live_decision | acceptance | platform_defects | availability | training | misrepresentation | loss_wasted_expenditure | loss_of_profit
- importance_weight: number from this fixed table:
  platform_defects=1.0, availability=1.0, acceptance=0.95, loss_of_profit=0.95,
  misrepresentation=0.90, go_live_decision=0.85, scope_change=0.85,
  timetable=0.75, loss_wasted_expenditure=0.75, formation=0.60, training=0.50

Rules:
1. Every numbered paragraph becomes exactly one proposition.
2. Split compound paragraphs with distinct sub-claims into suffixed propositions (e.g. 15a, 15b). Paragraph 15 MUST be split into 15a (wasted expenditure) and 15b (loss of profit).
3. Preserve verbatim text in the text field.
4. Return nothing except the JSON array."""

MODE_B_PROMPT_TEMPLATE = """You are a legal analyst examining excerpts from a litigation bundle that have been grouped by topic.
Based only on these excerpts, return ONLY valid JSON with exactly two fields:
- text: a single sentence in pleading style stating the legal proposition these excerpts relate to
- legal_element_type: one of: formation | scope_change | timetable | go_live_decision | acceptance | platform_defects | availability | training | misrepresentation | loss_wasted_expenditure | loss_of_profit

Excerpts:
1. {c1}
2. {c2}
3. {c3}
4. {c4}"""


# --------------------------------------------------------------------------- #
# Gemini helper
# --------------------------------------------------------------------------- #

def _strip_fences(text):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.lower().startswith("json"):
            t = t[4:]
        if t.endswith("```"):
            t = t[: t.rfind("```")]
    return t.strip()


def gemini_json(system_prompt, user_text):
    """Call Gemini with temperature 0 and JSON response; return parsed JSON."""
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set in the environment.")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL_NAME, system_instruction=system_prompt)
    response = model.generate_content(
        user_text,
        generation_config={"temperature": 0.0, "response_mime_type": "application/json"},
    )
    return json.loads(_strip_fences(response.text))


# --------------------------------------------------------------------------- #
# Mode detection + embeddings
# --------------------------------------------------------------------------- #

def detect_mode(chunks):
    if any(c["doc_type"] == "pleading" for c in chunks):
        return "A"
    return "B"


def embed_chunks(chunks):
    """Encode every chunk_text and attach `embedding`; write chunks_with_embeddings.json."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBED_MODEL_NAME)
    texts = [c["chunk_text"] for c in chunks]
    embeddings = model.encode(texts, show_progress_bar=True)
    for i, chunk in enumerate(chunks):
        chunk["embedding"] = embeddings[i].tolist()
    with open(EMBEDDINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False)
    print(f"[Stage 2] Wrote {EMBEDDINGS_FILE} ({len(chunks)} chunks, "
          f"dim={len(chunks[0]['embedding'])})")
    return chunks


# --------------------------------------------------------------------------- #
# Mode A — extraction from pleadings
# --------------------------------------------------------------------------- #

def run_mode_a(chunks):
    pleadings = [c for c in chunks if c["doc_type"] == "pleading"]
    pleadings.sort(key=lambda c: (c["doc_id"], c.get("paragraph_number") or 0))

    # Reconstruct the numbered Particulars so the model can recover allegation
    # numbers (Stage 1 stripped the leading "N." into paragraph_number).
    lines = []
    for c in pleadings:
        n = c.get("paragraph_number")
        lines.append(f"{n}. {c['chunk_text']}" if n is not None else c["chunk_text"])
    user_text = "\n\n".join(lines)

    props = gemini_json(MODE_A_SYSTEM_PROMPT, user_text)

    # Authoritative importance weight from the fixed table.
    for p in props:
        if p.get("legal_element_type") in IMPORTANCE:
            p["importance_weight"] = IMPORTANCE[p["legal_element_type"]]

    _validate_mode_a(props)

    for p in props:
        p["mode"] = "A"
        p["source_chunks"] = None

    with open(PROPOSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)
    print(f"[Stage 2] Wrote {PROPOSITIONS_FILE} ({len(props)} propositions)")
    return props


def _validate_mode_a(props):
    required = {"proposition_id", "allegation_number", "text",
                "legal_element_type", "importance_weight"}
    assert isinstance(props, list) and props, "Result must be a non-empty list"
    ids = []
    for p in props:
        assert isinstance(p, dict), f"Non-dict object: {p!r}"
        missing = required - set(p.keys())
        assert not missing, f"{p.get('proposition_id')} missing fields: {missing}"
        assert p["legal_element_type"] in ELEMENT_TYPES, \
            f"{p['proposition_id']} bad legal_element_type: {p['legal_element_type']}"
        expected = IMPORTANCE[p["legal_element_type"]]
        assert p["importance_weight"] == expected, \
            f"{p['proposition_id']} importance_weight {p['importance_weight']} != {expected}"
        ids.append(p["proposition_id"])
    assert len(ids) == len(set(ids)), f"Duplicate proposition_id(s): {ids}"
    assert "p15a" in ids and "p15b" in ids, \
        f"Expected both p15a and p15b; got ids: {ids}"


# --------------------------------------------------------------------------- #
# Mode B — inference from evidence (clustering); not run when pleadings exist
# --------------------------------------------------------------------------- #

def get_centroid_chunks(cluster_id, labels, chunks, reduced, n=4):
    from sklearn.metrics.pairwise import cosine_similarity

    indices = [i for i, l in enumerate(labels) if l == cluster_id]
    vecs = reduced[indices]
    centroid = vecs.mean(axis=0, keepdims=True)
    sims = cosine_similarity(centroid, vecs)[0]
    top_n = sorted(zip(indices, sims), key=lambda x: -x[1])[:n]
    return [chunks[i] for i, _ in top_n]


def run_mode_b(chunks):
    import umap
    import hdbscan

    embedding_matrix = np.array([c["embedding"] for c in chunks])
    reducer = umap.UMAP(n_components=15, random_state=42, metric="cosine")
    reduced = reducer.fit_transform(embedding_matrix)

    min_cluster_size = max(3, int(len(chunks) * 0.05))
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(reduced)

    cluster_ids = sorted(set(l for l in labels if l != -1))
    noise_idx = [i for i, l in enumerate(labels) if l == -1]
    print(f"[Stage 2] HDBSCAN found {len(cluster_ids)} clusters, "
          f"{len(noise_idx)} noise chunks")

    props = []
    for n, cluster_id in enumerate(cluster_ids, 1):
        reps = get_centroid_chunks(cluster_id, labels, chunks, reduced, n=4)
        rep_texts = [r["chunk_text"] for r in reps]
        while len(rep_texts) < 4:
            rep_texts.append("")
        prompt = MODE_B_PROMPT_TEMPLATE.format(
            c1=rep_texts[0], c2=rep_texts[1], c3=rep_texts[2], c4=rep_texts[3])
        result = gemini_json("You are a legal analyst.", prompt)
        etype = result.get("legal_element_type")
        cluster_chunk_ids = [chunks[i]["chunk_id"]
                             for i, l in enumerate(labels) if l == cluster_id]
        props.append({
            "proposition_id": f"pb{n}",
            "allegation_number": None,
            "text": result.get("text"),
            "legal_element_type": etype,
            "importance_weight": IMPORTANCE.get(etype),
            "mode": "B",
            "source_chunks": cluster_chunk_ids,
        })

    props.append({
        "proposition_id": "unclassified",
        "allegation_number": None,
        "text": "Evidence not mapped to any identifiable legal proposition",
        "legal_element_type": "unclassified",
        "importance_weight": None,
        "mode": "B",
        "source_chunks": [chunks[i]["chunk_id"] for i in noise_idx],
    })

    with open(PROPOSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)
    print(f"[Stage 2] Wrote {PROPOSITIONS_FILE} ({len(props)} propositions)")

    _cross_check_mode_b(props)
    return props


def _cross_check_mode_b(mode_b_props):
    """Step 6: match each Mode B proposition to nearest Mode A proposition."""
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity

    if not os.path.exists(PROPOSITIONS_FILE):
        return
    # Mode A propositions must exist from a prior run to cross-check against.
    mode_a = []
    # (In a pure Mode B case there is no Mode A file; cross-check is best-effort.)
    mode_a_path = "propositions_mode_a.json"
    if os.path.exists(mode_a_path):
        mode_a = json.load(open(mode_a_path, encoding="utf-8"))
    if not mode_a:
        print("[Stage 2] No Mode A propositions available; skipping cross-check.")
        return

    model = SentenceTransformer(EMBED_MODEL_NAME)
    b_real = [p for p in mode_b_props if p["proposition_id"] != "unclassified"]
    b_emb = model.encode([p["text"] for p in b_real])
    a_emb = model.encode([p["text"] for p in mode_a])

    records, matched_a = [], set()
    for i, p in enumerate(b_real):
        sims = cosine_similarity([b_emb[i]], a_emb)[0]
        j = int(np.argmax(sims))
        sim = float(sims[j])
        matched = sim >= 0.65
        if matched:
            matched_a.add(mode_a[j]["proposition_id"])
        records.append({
            "pb_proposition_id": p["proposition_id"],
            "best_match_mode_a_id": mode_a[j]["proposition_id"],
            "best_match_similarity": round(sim, 2),
            "matched": matched,
        })
    with open(MODE_B_VALIDATION_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    recall = 100.0 * len(matched_a) / len(mode_a) if mode_a else 0.0
    print(f"[Stage 2] Mode B recall vs Mode A: {recall:.1f}% "
          f"({len(matched_a)}/{len(mode_a)} matched >= 0.65)")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    load_dotenv()
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    mode = detect_mode(chunks)
    print(f"[Stage 2] Mode detected: {mode}")

    chunks = embed_chunks(chunks)

    if mode == "A":
        props = run_mode_a(chunks)
        warnings = []
    else:
        props = run_mode_b(chunks)
        warnings = []

    print("\n=== Stage 2 complete ===")
    print(f"Mode             : {mode}")
    print(f"Propositions     : {len(props)}")
    print(f"Warnings         : {len(warnings)}")
    for w in warnings:
        print(f"  - {w}")


if __name__ == "__main__":
    main()
