"""Stage 4 — Classification.

For each retrieved evidence chunk, ask Gemini to classify its relationship to the
proposition (score -2..+2, verbatim quote, reason, confidence), guarded by a
7-layer hallucination-prevention stack and programmatic validation. Produces
classification_results.json for Stage 5 + UI. Stage 4 does NOT assign the final
status label — only a preliminary status_hint.

Gap handling (user-approved): a proposition is skipped as GAP only when its
retrieved_chunks list is empty. Propositions flagged retrieval_gap=True that still
carry chunks are classified normally; the retrieval_gap flag passes through.

LLM: gemini-2.5-flash via google-generativeai, key from GEMINI_API_KEY, temp 0.0.

Run with UTF-8 console:
    PYTHONUTF8=1 ./.venv/Scripts/python.exe build_classification.py
"""

import json
import os
import time

import google.generativeai as genai
from dotenv import load_dotenv

RETRIEVAL_FILE = "retrieval_results.json"
OUTPUT_FILE = "classification_results.json"
GEMINI_MODEL_NAME = "gemini-2.5-flash"

VALID_STATUS_HINTS = {
    "GAP", "SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED",
    "CONTRADICTED_BY_OWN_EVIDENCE", "INCONCLUSIVE",
}

SYSTEM_PROMPT = """You are a legal evidence analyst classifying the relationship between a piece of evidence and a pleaded allegation in English commercial litigation.

Your task is to determine whether the evidence chunk supports, contradicts, or is neutral/inconclusive with respect to the proposition.

You must respond with ONLY valid JSON matching the schema below. No preamble, no explanation outside the JSON, no markdown formatting.

Output schema:
{
  "verbatim_quote": "<exact words copied from the evidence chunk that most directly drive your classification — must be a substring of the chunk text>",
  "reason": "<one sentence explaining how the quote relates to the proposition>",
  "score": <integer: -2 (direct contradiction), -1 (weak contradiction), 0 (inconclusive), 1 (weak support), 2 (direct support)>,
  "confidence": <float 0.0 to 1.0>
}

Scoring rules:
- Score +2: The chunk directly and unambiguously supports the proposition using clear factual assertions
- Score +1: The chunk is consistent with the proposition but does not directly confirm it
- Score 0: The chunk is topically related but does not clearly support or contradict the proposition
- Score -1: The chunk is in tension with the proposition but the contradiction is indirect or qualified
- Score -2: The chunk directly and unambiguously contradicts the proposition using clear factual assertions

Critical rules:
- Your verbatim_quote must be copied exactly from the chunk text — do not paraphrase or modify it
- Your reason must be grounded only in the verbatim_quote — do not reason beyond the quoted text
- Do not use background legal knowledge to infer relationships not present in the chunk text
- Do not consider document type when assigning your score — classify only what the text says"""

PROPOSITION_ENRICHMENT = {
    "p13": "This proposition concerns formal contractual acceptance under the MSA — specifically whether Meridian gave formal UAT sign-off or acceptance of the Platform. Evidence about post-acceptance conduct (ending the relationship, withholding milestone payments, expressing dissatisfaction with quality) is NOT evidence about whether formal acceptance was given. Classify only based on whether the chunk provides evidence about whether formal UAT acceptance or sign-off was or was not given.",
    "p15a": "This proposition relates specifically to wasted expenditure of £1,800,000 — the total sums paid by Meridian to TechFlow under the MSA.",
    "p15b": "This proposition relates specifically to loss of profit of £4,200,000 claimed by Meridian for the peak trading period of November and December 2024.",
}


def build_user_prompt(proposition, chunk, enrichment=None):
    proposition_text = proposition["text"]
    if enrichment:
        proposition_text += f"\n\nAdditional context: {enrichment}"

    nli_note = ""
    if chunk.get("nli_direction") == "uncertain":
        nli_note = ("\n\nNote: a preliminary automated filter assigned this chunk the direction: "
                    "uncertain. You are not bound by this assessment — reason from the text alone.")

    return f"""PROPOSITION (pleaded allegation):
{proposition_text}

EVIDENCE CHUNK:
Document: {chunk['doc_title']}
Type: {chunk['doc_type']}
Citation: {chunk['citation']}
Author party: {chunk['author_party']}
Text: {chunk['chunk_text']}{nli_note}

Classify the relationship between this evidence chunk and the proposition. Return JSON only."""


def _normalise(text):
    """Normalise Unicode curly quotes and non-breaking spaces to ASCII equivalents.

    Future-proofing for the Layer 2 substring check: applied to both the quote and
    the chunk_text before comparison so a genuine verbatim quote is not falsely
    flagged merely because Gemini emitted a straight quote where the source had a
    curly one (or vice versa). This does NOT rescue non-contiguous/spliced quotes.
    """
    if not text:
        return text
    replacements = {
        "‘": "'", "’": "'",   # curly single quotes / apostrophes
        "“": '"', "”": '"',   # curly double quotes
        " ": " ",                   # non-breaking space
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    return text


def validate_classification(raw_response, chunk):
    """Parse + validate Gemini output; set hallucination_flag / human_review."""
    result = {
        "verbatim_quote": None,
        "reason": None,
        "score": None,
        "confidence": None,
        "final_direction": None,
        "hallucination_flag": False,
        "human_review": False,
        "validation_errors": [],
    }

    try:
        clean = raw_response.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        parsed = json.loads(clean)
    except json.JSONDecodeError as e:
        result["hallucination_flag"] = True
        result["human_review"] = True
        result["validation_errors"].append(f"JSON parse error: {e}")
        return result

    # Layer 2 — substring check (normalise curly quotes / nbsp on both sides first)
    quote = parsed.get("verbatim_quote", "")
    result["verbatim_quote"] = quote
    if not quote or _normalise(quote) not in _normalise(chunk["chunk_text"]):
        result["hallucination_flag"] = True
        result["human_review"] = True
        result["validation_errors"].append("verbatim_quote not found in chunk_text")

    # Layer 3 — score boundary
    score = parsed.get("score")
    if score not in [-2, -1, 0, 1, 2]:
        result["hallucination_flag"] = True
        result["human_review"] = True
        result["validation_errors"].append(f"score out of bounds: {score}")
    else:
        result["score"] = score

    # Layer 3 — confidence boundary
    confidence = parsed.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        result["hallucination_flag"] = True
        result["human_review"] = True
        result["validation_errors"].append(f"confidence out of bounds: {confidence}")
    else:
        result["confidence"] = float(confidence)

    # Layer 4 — score/direction consistency
    if score is not None:
        if score > 0:
            result["final_direction"] = "supporting"
        elif score < 0:
            result["final_direction"] = "contradicting"
        else:
            result["final_direction"] = "neutral"

    result["reason"] = parsed.get("reason", "")
    return result


def compute_status_hint(classified_chunks):
    valid = [c for c in classified_chunks if not c["hallucination_flag"] and c["score"] is not None]
    supporting = [c for c in valid if c["final_direction"] == "supporting"]
    contradicting = [c for c in valid if c["final_direction"] == "contradicting"]

    if not valid:
        status = "INCONCLUSIVE"
    elif contradicting and not supporting:
        own = [c for c in contradicting if c["author_party"] == "claimant"]
        status = "CONTRADICTED_BY_OWN_EVIDENCE" if own else "CONTRADICTED"
    elif supporting and not contradicting:
        status = "SUPPORTED"
    elif supporting and contradicting:
        status = "PARTIALLY_SUPPORTED"
    else:
        status = "INCONCLUSIVE"
    return status, supporting, contradicting


def merge_chunk(chunk, validation):
    return {
        "chunk_id": chunk["chunk_id"],
        "doc_id": chunk["doc_id"],
        "doc_title": chunk["doc_title"],
        "doc_type": chunk["doc_type"],
        "doc_date": chunk["doc_date"],
        "author_party": chunk["author_party"],
        "chunk_text": chunk["chunk_text"],
        "citation": chunk["citation"],
        "source_quality_weight": chunk["source_quality_weight"],
        "clause_number": chunk.get("clause_number"),
        "paragraph_number": chunk.get("paragraph_number"),
        "witness_name": chunk.get("witness_name"),
        "witness_type": chunk.get("witness_type"),
        "expert_name": chunk.get("expert_name"),
        "is_opinion_section": chunk.get("is_opinion_section"),
        "defect_id": chunk.get("defect_id"),
        "severity": chunk.get("severity"),
        "cause_attribution": chunk.get("cause_attribution"),
        "rrf_score": chunk.get("rrf_score"),
        "nli_direction": chunk.get("nli_direction"),
        **validation,
    }


def validate_output(results, total_flags):
    assert len(results) == 17, f"Expected 17 proposition objects, got {len(results)}"
    for r in results:
        if not r["classified_chunks"]:
            assert r["status_hint"] == "GAP", f"{r['proposition_id']} empty but not GAP"
        assert r["status_hint"] in VALID_STATUS_HINTS, \
            f"{r['proposition_id']} bad status_hint {r['status_hint']}"
        for c in r["classified_chunks"]:
            assert c["doc_type"] != "pleading", f"Pleading classified: {c['chunk_id']}"
            assert c["source_quality_weight"] != 0.0, f"Weight 0.0 classified: {c['chunk_id']}"
            if not c["hallucination_flag"]:
                assert c["verbatim_quote"] and c["verbatim_quote"] in c["chunk_text"], \
                    f"{c['chunk_id']} quote not substring"
                assert c["score"] in [-2, -1, 0, 1, 2], f"{c['chunk_id']} score oob"
                assert 0.0 <= c["confidence"] <= 1.0, f"{c['chunk_id']} confidence oob"
    print(f"[Stage 4] Validation passed. Total hallucination flags: {total_flags}")


def main():
    load_dotenv()
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL_NAME,
        system_instruction=SYSTEM_PROMPT,
        generation_config=genai.GenerationConfig(
            temperature=0.0,
            response_mime_type="application/json",
        ),
    )

    with open(RETRIEVAL_FILE, "r", encoding="utf-8") as f:
        retrieval_results = json.load(f)

    all_results = []
    total_chunks_classified = 0
    total_hallucination_flags = 0

    for prop_result in retrieval_results:
        prop_id = prop_result["proposition_id"]
        chunks = prop_result["retrieved_chunks"]

        # Skip-as-GAP only when there are no chunks to classify (approved decision).
        if not chunks:
            all_results.append({
                "proposition_id": prop_id,
                "allegation_number": prop_result["allegation_number"],
                "proposition_text": prop_result["proposition_text"],
                "legal_element_type": prop_result["legal_element_type"],
                "importance_weight": prop_result["importance_weight"],
                "retrieval_gap": prop_result["retrieval_gap"],
                "status_hint": "GAP",
                "classified_chunks": [],
            })
            print(f"[Stage 4] {prop_id}: GAP (no chunks) — skipped")
            continue

        enrichment = PROPOSITION_ENRICHMENT.get(prop_id)
        classified_chunks = []

        for chunk in chunks:
            user_prompt = build_user_prompt(
                {"text": prop_result["proposition_text"]}, chunk, enrichment)
            try:
                response = model.generate_content(user_prompt)
                raw = response.text
            except Exception as e:
                print(f"[Stage 4] {prop_id} / {chunk['chunk_id']}: API error — {e}")
                err = {
                    "verbatim_quote": None, "reason": None, "score": None, "confidence": None,
                    "final_direction": None, "hallucination_flag": True, "human_review": True,
                    "validation_errors": [f"API error: {e}"],
                }
                classified_chunks.append(merge_chunk(chunk, err))
                total_hallucination_flags += 1
                continue

            validation = validate_classification(raw, chunk)
            if validation["hallucination_flag"]:
                total_hallucination_flags += 1
                print(f"[Stage 4] {prop_id} / {chunk['chunk_id']}: HALLUCINATION FLAG — "
                      f"{validation['validation_errors']}")

            classified_chunks.append(merge_chunk(chunk, validation))
            total_chunks_classified += 1
            time.sleep(0.5)

        status_hint, supporting, contradicting = compute_status_hint(classified_chunks)
        valid_count = sum(1 for c in classified_chunks
                          if not c["hallucination_flag"] and c["score"] is not None)

        all_results.append({
            "proposition_id": prop_id,
            "allegation_number": prop_result["allegation_number"],
            "proposition_text": prop_result["proposition_text"],
            "legal_element_type": prop_result["legal_element_type"],
            "importance_weight": prop_result["importance_weight"],
            "retrieval_gap": prop_result["retrieval_gap"],
            "status_hint": status_hint,
            "supporting_count": len(supporting),
            "contradicting_count": len(contradicting),
            "human_review_count": sum(1 for c in classified_chunks if c["human_review"]),
            "classified_chunks": classified_chunks,
        })
        print(f"[Stage 4] {prop_id}: {status_hint} — {len(supporting)} supporting, "
              f"{len(contradicting)} contradicting, "
              f"{len(classified_chunks) - valid_count} flagged")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    validate_output(all_results, total_hallucination_flags)

    print("\n[Stage 4] Complete")
    print(f"  Propositions classified: "
          f"{len([r for r in all_results if r['classified_chunks']])}")
    print(f"  Gap propositions skipped: "
          f"{len([r for r in all_results if not r['classified_chunks']])}")
    print(f"  Total chunks classified: {total_chunks_classified}")
    print(f"  Hallucination flags: {total_hallucination_flags}")

    # Diagnostic table
    print("\n[Stage 4] Diagnostic\n")
    print(f"{'prop_id':8s} | {'status_hint':28s} | {'supporting':10s} | "
          f"{'contradicting':13s} | {'flagged':7s} | top citation")
    print("-" * 8 + "-|-" + "-" * 28 + "-|-" + "-" * 10 + "-|-" + "-" * 13 + "-|-"
          + "-" * 7 + "-|-" + "-" * 13)
    for r in all_results:
        cc = r["classified_chunks"]
        top_cit = cc[0]["citation"] if cc else "—"
        print(f"{r['proposition_id']:8s} | {r['status_hint']:28s} | "
              f"{r.get('supporting_count', 0):<10d} | {r.get('contradicting_count', 0):<13d} | "
              f"{r.get('human_review_count', 0):<7d} | {top_cit}")


if __name__ == "__main__":
    main()
