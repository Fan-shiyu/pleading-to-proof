"""Mode B validation exercise (forced — ignores auto-detection).

Runs the Stage 2 Mode B pipeline on the existing chunks_with_embeddings.json,
regardless of whether the bundle has pleadings, to measure whether Mode B
(unsupervised clustering + Gemini inference) independently recovers the same
legal territory as Mode A.

Writes:
  - propositions_mode_b.json   (Mode B propositions; NOT propositions.json)
  - mode_b_validation.json     (cross-check vs Mode A, recall, unmatched list)

Never overwrites the Mode A output (propositions.json).

Run with UTF-8 console:
    PYTHONUTF8=1 ./.venv/Scripts/python.exe run_mode_b_validation.py
"""

import json

import numpy as np
from dotenv import load_dotenv

from build_propositions import (
    EMBED_MODEL_NAME, IMPORTANCE, MODE_B_PROMPT_TEMPLATE,
    gemini_json, get_centroid_chunks,
)

EMBEDDINGS_FILE = "chunks_with_embeddings.json"
MODE_A_FILE = "propositions.json"
MODE_B_FILE = "propositions_mode_b.json"
VALIDATION_FILE = "mode_b_validation.json"

MATCH_THRESHOLD = 0.65


def cluster(chunks):
    import umap
    import hdbscan

    matrix = np.array([c["embedding"] for c in chunks])
    reducer = umap.UMAP(n_components=15, random_state=42, metric="cosine")
    reduced = reducer.fit_transform(matrix)

    min_cluster_size = max(3, int(len(chunks) * 0.05))
    clusterer = hdbscan.HDBSCAN(min_cluster_size=min_cluster_size, metric="euclidean")
    labels = clusterer.fit_predict(reduced)
    return reduced, labels, min_cluster_size


def build_mode_b_props(chunks, reduced, labels):
    cluster_ids = sorted(set(l for l in labels if l != -1))
    noise_idx = [i for i, l in enumerate(labels) if l == -1]

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
    return props, cluster_ids, noise_idx


def cross_check(mode_b_props, mode_a_props):
    """Best Mode A match per Mode B prop; Mode-A-centric recall."""
    from sentence_transformers import SentenceTransformer
    from sklearn.metrics.pairwise import cosine_similarity

    b_real = [p for p in mode_b_props if p["proposition_id"] != "unclassified"]
    model = SentenceTransformer(EMBED_MODEL_NAME)
    b_emb = model.encode([p["text"] for p in b_real])
    a_emb = model.encode([p["text"] for p in mode_a_props])

    # sims[i][j] = similarity(mode_b i, mode_a j)
    sims = cosine_similarity(b_emb, a_emb)

    records = []
    for i, p in enumerate(b_real):
        j = int(np.argmax(sims[i]))
        sim = float(sims[i][j])
        records.append({
            "pb_proposition_id": p["proposition_id"],
            "best_match_mode_a_id": mode_a_props[j]["proposition_id"],
            "best_match_similarity": round(sim, 2),
            "matched": sim >= MATCH_THRESHOLD,
        })

    # Recall: fraction of Mode A propositions covered by >= 1 Mode B prop above threshold.
    matched_a_ids, unmatched_a = set(), []
    for j, a in enumerate(mode_a_props):
        best = float(sims[:, j].max()) if len(b_real) else 0.0
        if best >= MATCH_THRESHOLD:
            matched_a_ids.add(a["proposition_id"])
        else:
            unmatched_a.append({
                "mode_a_id": a["proposition_id"],
                "legal_element_type": a["legal_element_type"],
                "best_similarity": round(best, 2),
            })
    recall = 100.0 * len(matched_a_ids) / len(mode_a_props) if mode_a_props else 0.0

    validation = {
        "threshold": MATCH_THRESHOLD,
        "mode_a_total": len(mode_a_props),
        "mode_a_matched": len(matched_a_ids),
        "recall_percent": round(recall, 1),
        "records": records,
        "unmatched_mode_a": unmatched_a,
    }
    return validation


def main():
    load_dotenv()
    chunks = json.load(open(EMBEDDINGS_FILE, encoding="utf-8"))
    mode_a_props = json.load(open(MODE_A_FILE, encoding="utf-8"))
    print(f"[Mode B] Forced run on {len(chunks)} chunks "
          f"(ignoring auto-detection). Mode A has {len(mode_a_props)} propositions.")

    reduced, labels, min_cluster_size = cluster(chunks)
    n_clusters = len(set(l for l in labels if l != -1))
    n_noise = int((labels == -1).sum())
    print(f"[Mode B] HDBSCAN (min_cluster_size={min_cluster_size}) found "
          f"{n_clusters} clusters, {n_noise} noise chunks")

    props, cluster_ids, noise_idx = build_mode_b_props(chunks, reduced, labels)
    with open(MODE_B_FILE, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)
    n_mode_b = len(props) - 1  # exclude the unclassified entry
    print(f"[Mode B] Wrote {MODE_B_FILE} "
          f"({n_mode_b} propositions + 1 unclassified noise entry)")

    validation = cross_check(props, mode_a_props)
    with open(VALIDATION_FILE, "w", encoding="utf-8") as f:
        json.dump(validation, f, ensure_ascii=False, indent=2)
    print(f"[Mode B] Wrote {VALIDATION_FILE}")

    # ---- Human-readable summary ----
    print("\n" + "=" * 64)
    print("MODE B VALIDATION SUMMARY")
    print("=" * 64)
    print(f"HDBSCAN clusters found     : {n_clusters}")
    print(f"Noise chunks (unclustered) : {n_noise}")
    print(f"Mode B propositions        : {n_mode_b}")
    print(f"Recall vs Mode A           : {validation['recall_percent']}%  "
          f"({validation['mode_a_matched']}/{validation['mode_a_total']} "
          f"Mode A props matched >= {MATCH_THRESHOLD})")

    print("\nMode B -> nearest Mode A:")
    for r in validation["records"]:
        flag = "OK " if r["matched"] else "MISS"
        print(f"  [{flag}] {r['pb_proposition_id']:5s} -> "
              f"{r['best_match_mode_a_id']:6s} sim={r['best_match_similarity']}")

    unmatched = validation["unmatched_mode_a"]
    print(f"\nMode A propositions with NO Mode B match >= {MATCH_THRESHOLD}: "
          f"{len(unmatched)}")
    for u in unmatched:
        print(f"  - {u['mode_a_id']:6s} {u['legal_element_type']:24s} "
              f"(best sim {u['best_similarity']})")

    print("\nFiles written:")
    print(f"  {MODE_B_FILE}")
    print(f"  {VALIDATION_FILE}")
    print("propositions.json (Mode A) was NOT modified.")


if __name__ == "__main__":
    main()
