"""Stage 3 — Hybrid Retrieval.

For each proposition, retrieve the evidence chunks that support or contradict it:
  BM25 (legal tokeniser) + dense (MiniLM cosine) -> RRF fusion -> cross-encoder
  NLI filter (drops neutrals, labels direction) WITHOUT reordering the RRF rank.

Inputs (never modified): chunks.json, chunks_with_embeddings.json, propositions.json
Output: retrieval_results.json (17 proposition results, consumed by Stage 4 + UI)

Run with UTF-8 console:
    PYTHONUTF8=1 ./.venv/Scripts/python.exe build_retrieval.py
"""

import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
import re
from collections import defaultdict

import numpy as np
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder, SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from config import paths

# --------------------------------------------------------------------------- #
# Named constants — all thresholds live here (per spec)
# --------------------------------------------------------------------------- #

with open(paths.CHUNKS, "r", encoding="utf-8") as f:
    chunks = json.load(f)

RRF_K = 60                        # Standard RRF constant — do not tune
NEUTRAL_FILTER_THRESHOLD = 0.15  # lowered from 0.33 — NLI used for direction labelling not relevance gating
RRF_FLOOR = 3                     # Top-N chunks by RRF score always bypass the neutral filter
LETTER_WEIGHT_OVERRIDE = 0.75     # Override Stage 1 value of 0.5 for letter chunks
GAP_MIN_CHUNKS = max(2, int(0.02 * len(chunks)))  # Corpus-relative gap threshold

# Corpus-relative top-k values
k_bm25 = max(10, min(30, int(len(chunks) * 0.25)))   # ~24 for 99 chunks
k_dense = max(8, min(20, int(len(chunks) * 0.15)))    # ~14 for 99 chunks
k_rrf = max(12, min(20, int(len(chunks) * 0.18)))     # ~17 for 99 chunks, pre-rerank pool
k_final = 8                       # Max chunks passed to Stage 4 per proposition

# Targeted metadata pass-through rules. A chunk matching a rule for the current
# proposition's legal_element_type bypasses the NLI neutral filter and is added
# with the rule's assigned direction (used where terse factual evidence — e.g. a
# logged Platform Severity-1 defect — is real support but does not "entail" the
# pleading sentence in the NLI sense). Only fires for chunks already in the RRF pool.
METADATA_PASS_RULES = [
    {
        "condition": "defect_log_platform_evidence",
        "doc_type": "defect_log",
        "cause_attribution_contains": "Platform",
        "legal_element_type": "platform_defects",
        "assigned_direction": "supporting",
        "rule_label": "defect_log_platform_evidence",
    }
]


def match_metadata_rule(chunk, legal_element_type):
    """Return the first metadata rule the chunk matches for this proposition type, else None."""
    cause = (chunk.get("cause_attribution") or "").lower()
    for rule in METADATA_PASS_RULES:
        if (chunk.get("doc_type") == rule["doc_type"]
                and rule["cause_attribution_contains"].lower() in cause
                and legal_element_type == rule["legal_element_type"]):
            return rule
    return None

EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
CROSS_ENCODER_NAME = "cross-encoder/nli-deberta-v3-base"


# --------------------------------------------------------------------------- #
# Legal-aware tokeniser for BM25 (verbatim from spec)
# --------------------------------------------------------------------------- #

def legal_tokenise(text):
    """Legal-aware tokeniser for BM25.

    Preserves: hyphenated compounds, monetary figures with £, clause references like 14.1.
    Removes: generic stopwords but NOT legal negations (not, no, without, never). Lowercases.
    """
    text = text.lower()

    # Preserve monetary figures: £1,800,000 -> £1800000 (remove commas within figures)
    text = re.sub(r"£(\d{1,3}(?:,\d{3})*)", lambda m: "£" + m.group(1).replace(",", ""), text)

    # Preserve clause references: 14.1, 3.2, 22.1 — replace dot with underscore temporarily
    text = re.sub(r"\b(\d+)\.(\d+)\b", r"clause_\1_\2", text)

    # Tokenise on whitespace/punctuation EXCEPT hyphens (compounds) and underscores (clause markers)
    tokens = re.findall(r"[a-z0-9£_-]+", text)

    STOPWORDS = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
        "been", "being", "have", "has", "had", "do", "does", "did", "will",
        "would", "could", "should", "may", "might", "shall", "that", "this",
        "it", "its", "which", "who", "whom", "their", "they", "we", "our",
        "i", "my", "he", "she", "his", "her", "you", "your", "such", "any",
        "each", "all", "both", "other", "into", "also", "than", "then",
    }

    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    return tokens


# --------------------------------------------------------------------------- #
# Pre-processing: letter weight override + evidence filter
# --------------------------------------------------------------------------- #

# Letter weight override (in memory only — do not modify chunks.json on disk)
for chunk in chunks:
    if chunk["doc_type"] == "letter":
        chunk["source_quality_weight"] = LETTER_WEIGHT_OVERRIDE

# Evidence filter — never retrieve pleading chunks as evidence
evidence_chunks = [c for c in chunks if c["is_evidence"] is True and c["doc_type"] != "pleading"]
print(f"[Stage 3] Evidence corpus: {len(evidence_chunks)} chunks "
      f"(excluded {len(chunks) - len(evidence_chunks)} non-evidence/pleading chunks)")


# --------------------------------------------------------------------------- #
# One-time setup: BM25, embeddings, cross-encoder
# --------------------------------------------------------------------------- #

corpus_tokens = [legal_tokenise(c["chunk_text"]) for c in evidence_chunks]
bm25 = BM25Okapi(corpus_tokens)
print(f"[Stage 3] BM25 index built: {len(evidence_chunks)} documents")

embed_model = SentenceTransformer(EMBED_MODEL_NAME)
with open(paths.EMBEDDINGS, "r", encoding="utf-8") as f:
    chunks_with_emb = json.load(f)
evidence_ids = {c["chunk_id"] for c in evidence_chunks}
emb_lookup = {c["chunk_id"]: np.array(c["embedding"])
              for c in chunks_with_emb if c["chunk_id"] in evidence_ids}
evidence_embeddings = np.array([emb_lookup[c["chunk_id"]] for c in evidence_chunks])
print(f"[Stage 3] Evidence embeddings loaded: {evidence_embeddings.shape}")

cross_encoder = CrossEncoder(CROSS_ENCODER_NAME)
print(f"[Stage 3] Cross-encoder loaded: {CROSS_ENCODER_NAME}")

# Confirm NLI label order from the model card (spec default: [contradiction, entailment, neutral]).
id2label = cross_encoder.model.config.id2label
label2idx = {v.lower(): k for k, v in id2label.items()}
CONTRADICTION_IDX = label2idx.get("contradiction", 0)
ENTAILMENT_IDX = label2idx.get("entailment", 1)
NEUTRAL_IDX = label2idx.get("neutral", 2)
print(f"[Stage 3] NLI label order: {id2label} "
      f"(contradiction={CONTRADICTION_IDX}, entailment={ENTAILMENT_IDX}, neutral={NEUTRAL_IDX})")


# --------------------------------------------------------------------------- #
# Per-proposition retrieval
# --------------------------------------------------------------------------- #

def retrieve_for_proposition(proposition):
    # 4a — BM25 retrieval
    query_tokens = legal_tokenise(proposition["text"])
    bm25_scores = bm25.get_scores(query_tokens)
    bm25_ranked = sorted(enumerate(bm25_scores), key=lambda x: -x[1])
    bm25_top = bm25_ranked[:k_bm25]

    # 4b — Dense retrieval
    query_embedding = embed_model.encode([proposition["text"]])[0]
    similarities = cosine_similarity([query_embedding], evidence_embeddings)[0]
    dense_ranked = sorted(enumerate(similarities), key=lambda x: -x[1])
    dense_top = dense_ranked[:k_dense]

    # 4c — RRF fusion
    rrf_scores = defaultdict(float)
    for rank, (idx, _) in enumerate(bm25_top):
        rrf_scores[idx] += 1.0 / (RRF_K + rank + 1)
    dense_indices = {idx: rank for rank, (idx, _) in enumerate(dense_top)}
    for idx in rrf_scores:
        dense_rank = dense_indices.get(idx, 100)
        rrf_scores[idx] += 1.0 / (RRF_K + dense_rank + 1)
    for rank, (idx, _) in enumerate(dense_top):
        if idx not in rrf_scores:
            bm25_rank = 100
            rrf_scores[idx] = 1.0 / (RRF_K + bm25_rank + 1) + 1.0 / (RRF_K + rank + 1)
    rrf_ranked = sorted(rrf_scores.items(), key=lambda x: -x[1])
    rrf_top = rrf_ranked[:k_rrf]

    # 4d — Cross-encoder classification + neutral filtering
    pairs = [(evidence_chunks[idx]["chunk_text"], proposition["text"]) for idx, _ in rrf_top]
    raw_scores = cross_encoder.predict(pairs, apply_softmax=False)
    raw_scores = np.array(raw_scores)
    probs = np.exp(raw_scores) / np.exp(raw_scores).sum(axis=1, keepdims=True)

    classified_chunks = []
    prop_ltype = proposition.get("legal_element_type")
    for i, (idx, rrf_score) in enumerate(rrf_top):
        chunk = evidence_chunks[idx]
        rule = match_metadata_rule(chunk, prop_ltype)

        if rule:
            # Metadata pass-through: bypass the NLI neutral filter; null out NLI probs.
            p_entail = p_contradict = p_neutral = None
            nli_direction = rule["assigned_direction"]
        else:
            p_entail = float(probs[i][ENTAILMENT_IDX])
            p_contradict = float(probs[i][CONTRADICTION_IDX])
            p_neutral = float(probs[i][NEUTRAL_IDX])

            # rrf_top is RRF-ranked; index i is the RRF rank (0-based).
            is_floor = i < RRF_FLOOR  # top RRF_FLOOR chunks always pass through
            below_threshold = (p_entail < NEUTRAL_FILTER_THRESHOLD
                               and p_contradict < NEUTRAL_FILTER_THRESHOLD)

            # Neutral filter applies only to chunks ranked 4 and below (i >= RRF_FLOOR).
            if not is_floor and below_threshold:
                continue

            if is_floor and below_threshold:
                # Floor chunk the NLI model cannot classify either way.
                nli_direction = "uncertain"
            else:
                nli_direction = "supporting" if p_entail >= p_contradict else "contradicting"

        entry = {
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "doc_title": chunk["doc_title"],
            "doc_type": chunk["doc_type"],
            "doc_date": chunk["doc_date"],
            "author_party": chunk["author_party"],
            "chunk_text": chunk["chunk_text"],
            "citation": chunk["citation"],
            "source_quality_weight": chunk["source_quality_weight"],
            "is_opinion_section": chunk.get("is_opinion_section"),
            "witness_type": chunk.get("witness_type"),
            "rrf_score": rrf_score,
            "p_entailment": p_entail,
            "p_contradiction": p_contradict,
            "p_neutral": p_neutral,
            "nli_direction": nli_direction,
            # Type-specific citation metadata — pass through for Stage 4 and UI
            "clause_number": chunk.get("clause_number"),
            "paragraph_number": chunk.get("paragraph_number"),
            "witness_name": chunk.get("witness_name"),
            "expert_name": chunk.get("expert_name"),
            "section_name": chunk.get("section_name"),
            "defect_id": chunk.get("defect_id"),
            "severity": chunk.get("severity"),
            "cause_attribution": chunk.get("cause_attribution"),
        }
        if rule:
            entry["metadata_rule_applied"] = True
            entry["metadata_rule_label"] = rule["rule_label"]
        classified_chunks.append(entry)

    # Preserve RRF ranking — do NOT re-sort by NLI score
    classified_chunks = sorted(classified_chunks, key=lambda x: -x["rrf_score"])
    final_chunks = classified_chunks[:k_final]

    supporting_count = sum(1 for c in final_chunks if c["nli_direction"] == "supporting")
    contradicting_count = sum(1 for c in final_chunks if c["nli_direction"] == "contradicting")
    uncertain_count = sum(1 for c in final_chunks if c["nli_direction"] == "uncertain")

    # 4e — Gap detection on DIRECTIONAL chunks only. Uncertain floor chunks are
    # still passed to Stage 4 but do not count against the gap threshold.
    directional_count = supporting_count + contradicting_count
    retrieval_gap = directional_count < GAP_MIN_CHUNKS

    # 4f — Result object
    return {
        "proposition_id": proposition["proposition_id"],
        "allegation_number": proposition["allegation_number"],
        "proposition_text": proposition["text"],
        "legal_element_type": proposition["legal_element_type"],
        "importance_weight": proposition["importance_weight"],
        "retrieval_gap": retrieval_gap,
        "chunk_count": len(final_chunks),
        "supporting_count": supporting_count,
        "contradicting_count": contradicting_count,
        "uncertain_count": uncertain_count,
        "retrieved_chunks": final_chunks,
    }


# --------------------------------------------------------------------------- #
# Validation (assert all; raise on failure)
# --------------------------------------------------------------------------- #

def validate(results):
    assert len(results) == 17, f"Expected 17 results, got {len(results)}"
    for r in results:
        for key in ("proposition_id", "retrieval_gap", "retrieved_chunks"):
            assert key in r, f"{r.get('proposition_id')} missing {key}"
        for c in r["retrieved_chunks"]:
            assert c["doc_type"] != "pleading", f"Pleading retrieved: {c['chunk_id']}"
            assert c["source_quality_weight"] != 0.0, f"Weight 0.0 retrieved: {c['chunk_id']}"
            if c["doc_type"] == "letter":
                assert c["source_quality_weight"] == 0.75, \
                    f"Letter weight not overridden: {c['chunk_id']}"
        assert r["chunk_count"] == len(r["retrieved_chunks"]), \
            f"{r['proposition_id']} chunk_count mismatch"
        assert r["supporting_count"] + r["contradicting_count"] + r.get("uncertain_count", 0) \
            == r["chunk_count"], \
            f"{r['proposition_id']} support+contradict+uncertain != chunk_count"
    # is_evidence==False can't occur because evidence_chunks already filters it; assert on source
    retrieved_ids = {c["chunk_id"] for r in results for c in r["retrieved_chunks"]}
    assert retrieved_ids.issubset(evidence_ids), "Retrieved a non-evidence chunk"


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    with open(paths.PROPOSITIONS, "r", encoding="utf-8") as f:
        propositions = json.load(f)

    all_results = [retrieve_for_proposition(p) for p in propositions]

    validate(all_results)

    with open(paths.RETRIEVAL, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\n[Stage 3] retrieval_results.json written: {len(all_results)} propositions")

    gap_count = sum(1 for r in all_results if r["retrieval_gap"])
    print(f"[Stage 3] Propositions with retrieval_gap: {gap_count}")

    # Diagnostic table
    print("\n[Stage 3] Retrieval complete\n")
    print(f"{'prop_id':8s} | {'allegation':10s} | {'chunks':6s} | {'supporting':10s} | "
          f"{'contradicting':13s} | {'uncert':6s} | {'gap':5s} | top citation")
    print("-" * 8 + "-|-" + "-" * 10 + "-|-" + "-" * 6 + "-|-" + "-" * 10 + "-|-"
          + "-" * 13 + "-|-" + "-" * 6 + "-|-" + "-" * 5 + "-|-" + "-" * 13)
    for r in all_results:
        top_cit = r["retrieved_chunks"][0]["citation"] if r["retrieved_chunks"] else "—"
        gap = "TRUE" if r["retrieval_gap"] else "false"
        print(f"{r['proposition_id']:8s} | {str(r['allegation_number']):10s} | "
              f"{r['chunk_count']:<6d} | {r['supporting_count']:<10d} | "
              f"{r['contradicting_count']:<13d} | {r.get('uncertain_count', 0):<6d} | "
              f"{gap:5s} | {top_cit}")


if __name__ == "__main__":
    main()
