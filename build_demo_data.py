"""demo_data.json — pre-computation build.

Assembles every stage output into the single file the frontend reads on load:
case_metadata, summary_stats, the 17 merged propositions, the 20 documents
(enriched from the graph), and the embedded graph views. The only generated text
is a grounded one-line summary per proposition (Gemini gemini-2.5-flash, temp 0.0,
assembled from real field values only, with a substring-grounding check + fallback).

Run with UTF-8 console:
    PYTHONUTF8=1 ./.venv/Scripts/python.exe build_demo_data.py
"""

import json
import os
import re
import time
from datetime import datetime

import google.generativeai as genai
from dotenv import load_dotenv

GEMINI_MODEL_NAME = "gemini-2.5-flash"

SUMMARY_SYSTEM_PROMPT = """You are a legal document analyst. Your task is to write a single plain-English sentence summarising the evidential status of a pleaded allegation in English commercial litigation.

CRITICAL RULES:
- Use ONLY the information provided in the user message. Do not add any facts, inferences, or legal conclusions not explicitly present in the inputs.
- Your sentence must reference the specific citation provided.
- Do not use phrases like "the AI found", "analysis shows", "our tool determined", or any language suggesting automated processing.
- Write as a lawyer summarising the evidence would write — direct, factual, citation-anchored.
- Maximum 35 words.
- Return ONLY the sentence. No preamble, no explanation, no punctuation outside the sentence itself."""

BANNED_PHRASES = ["ai found", "analysis shows", "our tool", "the model", "automated"]


def build_summary_prompt(prop, scoring, top_chunk):
    status_phrases = {
        "SUPPORTED": "is supported by evidence",
        "PARTIALLY_SUPPORTED": "is partially supported but not fully established by the evidence",
        "INCONCLUSIVE": "is not clearly established by the available evidence",
        "CONTRADICTED": "is contradicted by the evidence",
        "STRONGLY_CONTRADICTED": "is directly contradicted by the evidence",
        "CONTRADICTED_BY_OWN_EVIDENCE": "is contradicted by the claimant's own evidence",
        "GAP": "has no supporting evidence identified in this bundle",
    }
    status_phrase = status_phrases.get(scoring["status"], "status unclear")

    if top_chunk:
        return f"""Allegation: "{prop['text'][:120]}"
Evidential status: {status_phrase}
Most determinative citation: {top_chunk['citation']}
Document: {top_chunk['doc_title']}
Author: {top_chunk['author_party']}
Verbatim quote from document: "{top_chunk['verbatim_quote']}"

Write one sentence (max 35 words) summarising this allegation's evidential status, referencing the citation above."""
    return f"""Allegation: "{prop['text'][:120]}"
Evidential status: {status_phrase}
No evidence was retrieved for this allegation in the available bundle.

Write one sentence (max 35 words) stating that no supporting evidence was found for this allegation."""


def build_fallback_summary(prop_text, top_chunk):
    if top_chunk is None:
        return "No evidence has been identified in this bundle for this allegation."
    direction = "supported" if top_chunk.get("score", 0) > 0 else "contradicted"
    return f"This allegation is {direction} by {top_chunk['citation']} ({top_chunk['doc_title']})."


def validate_summary(summary, top_chunk, prop_text):
    """Returns (validated_summary, is_valid)."""
    summary = summary.strip()

    if len(summary.split()) > 40:  # allow slight buffer over 35
        return build_fallback_summary(prop_text, top_chunk), False

    if top_chunk:
        citation_words = set(top_chunk["citation"].lower().split())
        quote_words = set(top_chunk["verbatim_quote"].lower().split())
        summary_words = set(summary.lower().split())
        overlap = len((citation_words | quote_words) & summary_words)
        if overlap < 2:
            return build_fallback_summary(prop_text, top_chunk), False

    return summary, True


def build_proposition_object(prop, scoring, classification, retrieval, one_line_summary):
    citation_audit = scoring.get("citation_audit", {})
    most_determinative = citation_audit.get("most_determinative_citation")

    classified_chunks = []
    for chunk in classification.get("classified_chunks", []):
        classified_chunks.append({
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "doc_title": chunk["doc_title"],
            "doc_type": chunk["doc_type"],
            "author_party": chunk["author_party"],
            "doc_date": chunk.get("doc_date"),
            "chunk_text": chunk["chunk_text"],
            "verbatim_quote": chunk.get("verbatim_quote"),
            "citation": chunk["citation"],
            "clause_number": chunk.get("clause_number"),
            "paragraph_number": chunk.get("paragraph_number"),
            "witness_name": chunk.get("witness_name"),
            "expert_name": chunk.get("expert_name"),
            "section_name": chunk.get("section_name"),
            "defect_id": chunk.get("defect_id"),
            "severity": chunk.get("severity"),
            "score": chunk.get("score"),
            "final_direction": chunk.get("final_direction"),
            "confidence": chunk.get("confidence"),
            "reason": chunk.get("reason"),
            "source_quality_weight": chunk["source_quality_weight"],
            "weighted_contribution": chunk.get("weighted_contribution"),
            "nli_direction": chunk.get("nli_direction"),
            "hallucination_flag": chunk.get("hallucination_flag", False),
            "human_review": chunk.get("human_review", False),
            "metadata_rule_applied": chunk.get("metadata_rule_applied", False),
            "metadata_rule_label": chunk.get("metadata_rule_label"),
        })

    return {
        "proposition_id": prop["proposition_id"],
        "allegation_number": prop["allegation_number"],
        "proposition_text": prop["text"],
        "legal_element_type": prop["legal_element_type"],
        "importance_weight": prop["importance_weight"],
        "proof_score": scoring["proof_score"],
        "risk_score": scoring["risk_score"],
        "max_possible_score": scoring.get("max_possible_score"),
        "status": scoring["status"],
        "classification_confidence": scoring["classification_confidence"],
        "boundary_distance": scoring.get("boundary_distance"),
        "one_line_summary": one_line_summary,
        "retrieval_gap": retrieval.get("retrieval_gap", False),
        "is_own_evidence_contradiction": scoring.get("is_own_evidence_contradiction", False),
        "chunk_count": scoring["chunk_count"],
        "supporting_count": scoring["supporting_count"],
        "contradicting_count": scoring["contradicting_count"],
        "neutral_count": scoring.get("neutral_count", 0),
        "human_review_count": scoring.get("human_review_count", 0),
        "top_supporting_citation": citation_audit.get("top_supporting_citation"),
        "top_contradicting_citation": citation_audit.get("top_contradicting_citation"),
        "most_determinative_citation": most_determinative,
        "own_evidence_citations": citation_audit.get("own_evidence_citations", []),
        "human_review_citations": citation_audit.get("human_review_citations", []),
        "no_evidence_note": citation_audit.get("no_evidence_note"),
        "classified_chunks": classified_chunks,
    }


def build_documents_list(registry_list, graph_data):
    documents = []
    for doc in registry_list:
        graph_node = next(
            (n for n in graph_data["document_view"]["nodes"]
             if n.get("node_type") == "document" and n["id"] == doc["doc_id"]),
            None,
        )
        documents.append({
            "doc_id": doc["doc_id"],
            "doc_title": doc["doc_title"],
            "doc_type": doc["doc_type"],
            "doc_date": doc.get("doc_date") or doc.get("date"),  # registry uses 'date'
            "author_party": doc.get("author_party"),
            "source_quality_weight": doc.get("source_quality_weight"),
            "edge_count": graph_node["edge_count"] if graph_node else 0,
            "is_evidence_active": graph_node["is_active"] if graph_node else False,
            "dominant_legal_type": graph_node["dominant_legal_type"] if graph_node else "unclassified",
            "colour": graph_node["colour"] if graph_node else "#6B7280",
        })
    return documents


def _allegation_key(alleg):
    """Natural sort key: '15a' -> (15, 'a'), '2' -> (2, '')."""
    m = re.match(r"(\d+)([a-z]*)", str(alleg))
    return (int(m.group(1)), m.group(2)) if m else (9999, str(alleg))


def main():
    load_dotenv()
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL_NAME,
        system_instruction=SUMMARY_SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(temperature=0.0),
    )

    scoring_results = {s["proposition_id"]: s for s in json.load(open("scoring_results.json", encoding="utf-8"))}
    classification_results = {c["proposition_id"]: c for c in json.load(open("classification_results.json", encoding="utf-8"))}
    propositions = {p["proposition_id"]: p for p in json.load(open("propositions.json", encoding="utf-8"))}
    retrieval_results = {r["proposition_id"]: r for r in json.load(open("retrieval_results.json", encoding="utf-8"))}
    graph_data = json.load(open("graph_data.json", encoding="utf-8"))
    registry = json.load(open("registry.json", encoding="utf-8"))
    registry_list = [v for k, v in registry.items() if not k.startswith("_")]

    propositions_built = []
    validation_failures = 0

    for prop_id, prop in propositions.items():
        scoring = scoring_results[prop_id]
        classification = classification_results[prop_id]
        retrieval = retrieval_results[prop_id]
        most_determinative = scoring.get("citation_audit", {}).get("most_determinative_citation")

        prompt = build_summary_prompt(prop, scoring, most_determinative)
        try:
            response = model.generate_content(prompt)
            raw_summary = response.text.strip()
            summary, is_valid = validate_summary(raw_summary, most_determinative, prop["text"])
            if not is_valid:
                validation_failures += 1
                print(f"[demo_data] {prop_id}: summary failed validation — using fallback")
        except Exception as e:
            summary = build_fallback_summary(prop["text"], most_determinative)
            validation_failures += 1
            print(f"[demo_data] {prop_id}: Gemini error ({e}) — using fallback")

        print(f"[demo_data] {prop_id} ({scoring['status']}): {summary}")
        propositions_built.append(
            build_proposition_object(prop, scoring, classification, retrieval, summary))
        time.sleep(0.3)

    status_counts = {}
    for p in propositions_built:
        status_counts[p["status"]] = status_counts.get(p["status"], 0) + 1

    highest_risk = max(propositions_built, key=lambda x: x["risk_score"])
    strongest = max([p for p in propositions_built if p["proof_score"] is not None],
                    key=lambda x: x["proof_score"])

    summary_stats = {
        "supported_count": status_counts.get("SUPPORTED", 0),
        "partially_supported_count": status_counts.get("PARTIALLY_SUPPORTED", 0),
        "inconclusive_count": status_counts.get("INCONCLUSIVE", 0),
        "contradicted_count": status_counts.get("CONTRADICTED", 0),
        "strongly_contradicted_count": status_counts.get("STRONGLY_CONTRADICTED", 0),
        "contradicted_by_own_evidence_count": status_counts.get("CONTRADICTED_BY_OWN_EVIDENCE", 0),
        "gap_count": status_counts.get("GAP", 0),
        "highest_risk_proposition_id": highest_risk["proposition_id"],
        "highest_risk_allegation_number": highest_risk["allegation_number"],
        "strongest_proposition_id": strongest["proposition_id"],
        "strongest_allegation_number": strongest["allegation_number"],
        "own_evidence_contradiction_count": sum(
            1 for p in propositions_built if p["is_own_evidence_contradiction"]),
    }

    # Compute case-metadata counts from the real data (post p12 metadata fix).
    chunks_classified = sum(len(c["classified_chunks"]) for c in classification_results.values())
    hallucination_flags = sum(
        1 for c in classification_results.values()
        for ch in c["classified_chunks"] if ch.get("hallucination_flag"))

    demo_data = {
        "case_metadata": {
            "case_name": "Meridian Retail Group plc v TechFlow Solutions Limited",
            "claim_number": "HT-2025-000231",
            "court": "High Court of Justice, Business and Property Courts, TCC (KBD)",
            "bundle_document_count": 20,
            "proposition_count": 17,
            "chunk_count": 99,
            "chunks_classified": chunks_classified,
            "hallucination_flags": hallucination_flags,
            "generated_at": datetime.now().isoformat(),
            "pipeline_version": "1.0.0",
        },
        "summary_stats": summary_stats,
        "propositions": {p["proposition_id"]: p for p in propositions_built},
        "risk_dashboard_order": [
            p["proposition_id"] for p in
            sorted(propositions_built, key=lambda x: -x["risk_score"])],
        "proof_matrix_order": [
            p["proposition_id"] for p in
            sorted(propositions_built, key=lambda x: _allegation_key(x["allegation_number"]))],
        "documents": build_documents_list(registry_list, graph_data),
        "graph": {
            "document_view": graph_data["document_view"],
            "detailed_view": graph_data["detailed_view"],
            "metadata": graph_data["metadata"],
        },
    }

    with open("demo_data.json", "w", encoding="utf-8") as f:
        json.dump(demo_data, f, indent=2, ensure_ascii=False)

    validate(demo_data)
    diagnostics(demo_data, validation_failures)


# --------------------------------------------------------------------------- #
# Validation (12 checks)
# --------------------------------------------------------------------------- #

def validate(demo_data):
    for key in ("case_metadata", "summary_stats", "propositions",
                "risk_dashboard_order", "proof_matrix_order", "documents", "graph"):
        assert key in demo_data, f"missing top-level key {key}"
    props = demo_data["propositions"]
    assert len(props) == 17, f"not 17 propositions: {len(props)}"
    for pid, p in props.items():
        assert isinstance(p["one_line_summary"], str) and p["one_line_summary"].strip(), \
            f"{pid} empty one_line_summary"
        for field in ("proposition_text", "status", "proof_score", "risk_score"):
            assert field in p, f"{pid} missing {field}"
        low = p["one_line_summary"].lower()
        for phrase in BANNED_PHRASES:
            assert phrase not in low, f"{pid} summary contains banned phrase '{phrase}'"
        for ch in p["classified_chunks"]:
            assert ch["chunk_text"] and ch["chunk_text"].strip(), f"{pid} chunk empty chunk_text"
            assert "verbatim_quote" in ch, f"{pid} chunk missing verbatim_quote"
            if ch.get("hallucination_flag"):
                assert ch.get("human_review"), f"{pid} flagged chunk not human_review"
            assert ch["source_quality_weight"] != 0.0, f"{pid} chunk weight 0.0"
    assert len(demo_data["risk_dashboard_order"]) == 17, "risk order != 17"
    assert len(demo_data["proof_matrix_order"]) == 17, "proof order != 17"
    assert len(demo_data["documents"]) == 20, f"not 20 documents: {len(demo_data['documents'])}"
    assert demo_data["graph"]["document_view"]["nodes"], "document_view empty"
    assert demo_data["graph"]["detailed_view"]["nodes"], "detailed_view empty"
    ss = demo_data["summary_stats"]
    status_total = sum(ss[k] for k in (
        "supported_count", "partially_supported_count", "inconclusive_count",
        "contradicted_count", "strongly_contradicted_count",
        "contradicted_by_own_evidence_count", "gap_count"))
    assert status_total == 17, f"status counts sum to {status_total}, not 17"
    print("[demo_data] All 12 validation checks passed.")


def diagnostics(demo_data, validation_failures):
    import os as _os
    props = demo_data["propositions"]
    print("\n[demo_data] One-line summaries by risk (highest first)\n")
    print(f"{'risk':5s} | {'prop':5s} | {'status':29s} | summary")
    print("-" * 5 + "-|-" + "-" * 5 + "-|-" + "-" * 29 + "-|-" + "-" * 8)
    for pid in demo_data["risk_dashboard_order"]:
        p = props[pid]
        print(f"{p['risk_score']:.2f}  | {pid:5s} | {p['status']:29s} | {p['one_line_summary']}")
    size_kb = _os.path.getsize("demo_data.json") / 1024
    print(f"\nFile size: {size_kb:.1f} KB")
    print(f"Validation failures (fallback used): {validation_failures}")
    cm = demo_data["case_metadata"]
    print(f"case_metadata: chunks_classified={cm['chunks_classified']} "
          f"hallucination_flags={cm['hallucination_flags']}")


if __name__ == "__main__":
    main()
