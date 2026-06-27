"""Stage 5 — Scoring (deterministic; no LLM).

Reads classification_results.json + propositions.json and produces scoring_results.json:
per-proposition proof_score, status label, risk_score, classification confidence, and a
full citation audit trail. Grounded in English evidence law — contemporaneous-document
source hierarchy (Gestmin / Walter Lilly) and balance-of-probabilities asymmetric
thresholds. Every number traces to a document citation.

Run with UTF-8 console:
    PYTHONUTF8=1 ./.venv/Scripts/python.exe build_scoring.py
"""

import json

# --------------------------------------------------------------------------- #
# Named constants — all thresholds live here
# --------------------------------------------------------------------------- #

# Status label thresholds (asymmetric — reflects burden of proof)
THRESHOLD_SUPPORTED = 0.6          # proof_score >= 0.6 -> SUPPORTED
THRESHOLD_PARTIAL_UPPER = 0.2      # proof_score >= 0.2 -> PARTIALLY_SUPPORTED
THRESHOLD_PARTIAL_LOWER = -0.2     # proof_score >= -0.2 -> INCONCLUSIVE (if < upper)
THRESHOLD_CONTRADICTED = -0.6      # proof_score < -0.6 -> STRONGLY_CONTRADICTED
# Between -0.2 and -0.6 -> CONTRADICTED

OWN_EVIDENCE_MAJORITY = 0.5        # claimant contradiction weight must exceed 50% of total
OWN_EVIDENCE_MULTIPLIER = 1.25     # own-evidence risk multiplier
GAP_RISK_FACTOR = 0.95             # gap_risk = importance_weight * 0.95
MINIMUM_RISK_FLOOR = 0.05          # no proposition ever has zero litigation risk

BORDERLINE_THRESHOLD = 0.05        # < 0.05 from nearest boundary -> 'borderline'
MODERATE_THRESHOLD = 0.15          # < 0.15 -> 'moderate', else 'confident'

STATUS_BOUNDARIES = [THRESHOLD_SUPPORTED, THRESHOLD_PARTIAL_UPPER,
                     THRESHOLD_PARTIAL_LOWER, THRESHOLD_CONTRADICTED]

VALID_STATUSES = {
    "GAP", "SUPPORTED", "PARTIALLY_SUPPORTED", "INCONCLUSIVE",
    "CONTRADICTED", "STRONGLY_CONTRADICTED", "CONTRADICTED_BY_OWN_EVIDENCE",
}


# --------------------------------------------------------------------------- #
# Proof score
# --------------------------------------------------------------------------- #

def compute_proof_score(classified_chunks):
    """Returns (proof_score, max_possible). proof_score is None for genuine gaps."""
    eligible = [
        c for c in classified_chunks
        if not c.get("hallucination_flag")
        and c.get("score") is not None
        and c.get("final_direction") in ["supporting", "contradicting"]
    ]
    if not eligible:
        return None, 0.0

    raw_score = sum(
        c["score"] * c["source_quality_weight"] * c["confidence"] for c in eligible
    )
    max_possible = sum(c["source_quality_weight"] * 2.0 for c in eligible)
    if max_possible == 0:
        return None, 0.0

    proof_score = raw_score / max_possible  # range: -1.0 to +1.0
    return round(proof_score, 4), round(max_possible, 4)


# --------------------------------------------------------------------------- #
# Status label
# --------------------------------------------------------------------------- #

def assign_status(proof_score, classified_chunks, retrieval_gap, is_gap_proposition):
    if is_gap_proposition and not classified_chunks:
        return "GAP"

    if proof_score is None:
        neutral_exists = any(
            c.get("score") == 0 and not c.get("hallucination_flag")
            for c in classified_chunks
        )
        if neutral_exists:
            return "INCONCLUSIVE"
        return "GAP"

    if proof_score >= THRESHOLD_SUPPORTED:
        return "SUPPORTED"
    elif proof_score >= THRESHOLD_PARTIAL_UPPER:
        return "PARTIALLY_SUPPORTED"
    elif proof_score >= THRESHOLD_PARTIAL_LOWER:
        return "INCONCLUSIVE"
    elif proof_score >= THRESHOLD_CONTRADICTED:
        return "CONTRADICTED"
    else:
        return "STRONGLY_CONTRADICTED"


# --------------------------------------------------------------------------- #
# Own-evidence contradiction overlay
# --------------------------------------------------------------------------- #

def is_own_evidence_contradiction(classified_chunks):
    contradicting = [
        c for c in classified_chunks
        if c.get("final_direction") == "contradicting"
        and not c.get("hallucination_flag")
        and c.get("score") is not None
    ]
    if not contradicting:
        return False

    def weighted_contribution(c):
        return abs(c["score"]) * c["source_quality_weight"] * c["confidence"]

    total_weight = sum(weighted_contribution(c) for c in contradicting)
    claimant_weight = sum(
        weighted_contribution(c) for c in contradicting
        if c.get("author_party") == "claimant"
    )
    if total_weight == 0:
        return False
    return (claimant_weight / total_weight) > OWN_EVIDENCE_MAJORITY


def apply_own_evidence_overlay(status, classified_chunks):
    if status in ("CONTRADICTED", "STRONGLY_CONTRADICTED"):
        if is_own_evidence_contradiction(classified_chunks):
            return "CONTRADICTED_BY_OWN_EVIDENCE"
    return status


# --------------------------------------------------------------------------- #
# Risk score
# --------------------------------------------------------------------------- #

def compute_risk_score(proof_score, importance_weight, status):
    if status == "GAP" or proof_score is None:
        base_risk = importance_weight * GAP_RISK_FACTOR
        return round(max(MINIMUM_RISK_FLOOR, base_risk), 4)

    base_risk = importance_weight * (1 - proof_score) / 2
    if status == "CONTRADICTED_BY_OWN_EVIDENCE":
        base_risk = min(1.0, base_risk * OWN_EVIDENCE_MULTIPLIER)

    return round(max(MINIMUM_RISK_FLOOR, base_risk), 4)


# --------------------------------------------------------------------------- #
# Boundary distance + classification confidence
# --------------------------------------------------------------------------- #

def compute_boundary_distance(proof_score):
    if proof_score is None:
        return None
    return round(min(abs(proof_score - b) for b in STATUS_BOUNDARIES), 4)


def compute_classification_confidence(boundary_distance):
    if boundary_distance is None:
        return "n/a"
    if boundary_distance < BORDERLINE_THRESHOLD:
        return "borderline"
    elif boundary_distance < MODERATE_THRESHOLD:
        return "moderate"
    else:
        return "confident"


# --------------------------------------------------------------------------- #
# Citation audit trail
# --------------------------------------------------------------------------- #

def build_citation_audit(classified_chunks):
    eligible = [
        c for c in classified_chunks
        if not c.get("hallucination_flag") and c.get("score") is not None
    ]
    supporting = [c for c in eligible if c.get("final_direction") == "supporting"]
    contradicting = [c for c in eligible if c.get("final_direction") == "contradicting"]
    neutral = [c for c in eligible if c.get("score") == 0]
    flagged = [c for c in classified_chunks if c.get("hallucination_flag")]

    def contribution(c):
        return abs(c["score"]) * c["source_quality_weight"] * c["confidence"]

    def sort_by_contribution(chunks):
        return sorted(chunks, key=contribution, reverse=True)

    def format_citation_entry(c):
        return {
            "citation": c["citation"],
            "doc_title": c["doc_title"],
            "doc_type": c["doc_type"],
            "author_party": c["author_party"],
            "score": c["score"],
            "confidence": c["confidence"],
            "source_quality_weight": c["source_quality_weight"],
            "verbatim_quote": c["verbatim_quote"],
            "reason": c["reason"],
            "weighted_contribution": round(contribution(c), 4),
        }

    sorted_supporting = sort_by_contribution(supporting)
    sorted_contradicting = sort_by_contribution(contradicting)

    own_evidence = [c for c in contradicting if c.get("author_party") == "claimant"]
    own_evidence_sorted = sort_by_contribution(own_evidence)

    all_directional = supporting + contradicting
    most_determinative = None
    if all_directional:
        best = sort_by_contribution(all_directional)[0]
        most_determinative = format_citation_entry(best)

    return {
        "top_supporting_citation":
            format_citation_entry(sorted_supporting[0]) if sorted_supporting else None,
        "top_contradicting_citation":
            format_citation_entry(sorted_contradicting[0]) if sorted_contradicting else None,
        "most_determinative_citation": most_determinative,
        "own_evidence_citations": [format_citation_entry(c) for c in own_evidence_sorted],
        "all_supporting_citations": [format_citation_entry(c) for c in sorted_supporting],
        "all_contradicting_citations": [format_citation_entry(c) for c in sorted_contradicting],
        "neutral_citations": [
            {"citation": c["citation"], "doc_title": c["doc_title"], "reason": c["reason"]}
            for c in neutral
        ],
        "human_review_citations": [
            {
                "citation": c["citation"],
                "doc_title": c["doc_title"],
                "note": "Classification uncertain — requires human review",
                "validation_errors": c.get("validation_errors", []),
            }
            for c in flagged
        ] if flagged else [],
        "no_evidence_note":
            "No evidence retrieved for this proposition" if not eligible else None,
    }


# --------------------------------------------------------------------------- #
# Validation (10 checks)
# --------------------------------------------------------------------------- #

def validate(results):
    assert len(results) == 17, f"Expected 17 results, got {len(results)}"
    for r in results:
        ps = r["proof_score"]
        assert ps is None or (-1.0 <= ps <= 1.0), f"{r['proposition_id']} proof_score oob: {ps}"
        assert MINIMUM_RISK_FLOOR <= r["risk_score"] <= 1.0, \
            f"{r['proposition_id']} risk_score oob: {r['risk_score']}"
        assert r["status"] in VALID_STATUSES, f"{r['proposition_id']} bad status {r['status']}"
        assert r["classification_confidence"] in {"borderline", "moderate", "confident", "n/a"}, \
            f"{r['proposition_id']} bad confidence"
        ca = r["citation_audit"]
        assert ca["most_determinative_citation"] is not None or ca["no_evidence_note"], \
            f"{r['proposition_id']} no determinative citation and no no_evidence_note"
        for hrc in ca["human_review_citations"]:
            assert hrc["note"] == "Classification uncertain — requires human review", \
                f"{r['proposition_id']} bad human_review note"
        # No 0.0 source_quality_weight in any citation entry
        for key in ("all_supporting_citations", "all_contradicting_citations"):
            for entry in ca[key]:
                assert entry["source_quality_weight"] != 0.0, \
                    f"{r['proposition_id']} weight 0.0 in {key}"
        is_own = r["is_own_evidence_contradiction"]
        assert is_own == (r["status"] == "CONTRADICTED_BY_OWN_EVIDENCE"), \
            f"{r['proposition_id']} own-evidence flag/status mismatch"
        if r["status"] == "CONTRADICTED_BY_OWN_EVIDENCE":
            assert ca["own_evidence_citations"], \
                f"{r['proposition_id']} CONTRADICTED_BY_OWN_EVIDENCE with no own_evidence_citations"
    print("[Stage 5] All 10 validation checks passed.")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    with open("classification_results.json", "r", encoding="utf-8") as f:
        classification_results = json.load(f)
    with open("propositions.json", "r", encoding="utf-8") as f:
        propositions = json.load(f)

    importance_lookup = {p["proposition_id"]: p["importance_weight"] for p in propositions}

    all_results = []
    for prop in classification_results:
        prop_id = prop["proposition_id"]
        classified_chunks = prop.get("classified_chunks", [])
        retrieval_gap = prop.get("retrieval_gap", False)
        importance_weight = importance_lookup.get(prop_id, 0.5)
        is_gap_proposition = retrieval_gap and not classified_chunks

        proof_score, max_possible = compute_proof_score(classified_chunks)
        status = assign_status(proof_score, classified_chunks, retrieval_gap, is_gap_proposition)
        status = apply_own_evidence_overlay(status, classified_chunks)
        risk_score = compute_risk_score(proof_score, importance_weight, status)
        boundary_distance = compute_boundary_distance(proof_score)
        classification_confidence = compute_classification_confidence(boundary_distance)
        citation_audit = build_citation_audit(classified_chunks)

        non_flagged = [c for c in classified_chunks if not c.get("hallucination_flag")]
        supporting_count = sum(1 for c in non_flagged if c.get("final_direction") == "supporting")
        contradicting_count = sum(1 for c in non_flagged if c.get("final_direction") == "contradicting")
        neutral_count = sum(1 for c in non_flagged if c.get("score") == 0)
        human_review_count = sum(1 for c in classified_chunks if c.get("hallucination_flag"))

        result = {
            "proposition_id": prop_id,
            "allegation_number": prop["allegation_number"],
            "proposition_text": prop["proposition_text"],
            "legal_element_type": prop["legal_element_type"],
            "importance_weight": importance_weight,
            "proof_score": proof_score,
            "risk_score": risk_score,
            "max_possible_score": max_possible,
            "status": status,
            "classification_confidence": classification_confidence,
            "boundary_distance": boundary_distance,
            "retrieval_gap": retrieval_gap,
            "is_own_evidence_contradiction": status == "CONTRADICTED_BY_OWN_EVIDENCE",
            "chunk_count": len(classified_chunks),
            "supporting_count": supporting_count,
            "contradicting_count": contradicting_count,
            "neutral_count": neutral_count,
            "human_review_count": human_review_count,
            "citation_audit": citation_audit,
        }
        all_results.append(result)
        print(f"[Stage 5] {prop_id}: {status} | proof={proof_score} | "
              f"risk={risk_score} | conf={classification_confidence}")

    with open("scoring_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print("\n[Stage 5] Complete — scoring_results.json written")

    validate(all_results)

    # Diagnostic table, sorted by risk_score descending
    print("\n[Stage 5] Risk dashboard (sorted by risk_score descending)\n")
    print(f"{'prop_id':8s} | {'status':29s} | {'proof':6s} | {'risk':5s} | "
          f"{'conf':10s} | top citation")
    print("-" * 8 + "-|-" + "-" * 29 + "-|-" + "-" * 6 + "-|-" + "-" * 5 + "-|-"
          + "-" * 10 + "-|-" + "-" * 13)
    for r in sorted(all_results, key=lambda x: -x["risk_score"]):
        md = r["citation_audit"]["most_determinative_citation"]
        top_cit = md["citation"] if md else "—"
        ps = f"{r['proof_score']:+.2f}" if r["proof_score"] is not None else "None"
        print(f"{r['proposition_id']:8s} | {r['status']:29s} | {ps:6s} | "
              f"{r['risk_score']:.2f}  | {r['classification_confidence']:10s} | {top_cit}")


if __name__ == "__main__":
    main()
