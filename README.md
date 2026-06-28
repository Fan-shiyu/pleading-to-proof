# Pleading to Proof — ALLEGATOR

[![Tool](https://img.shields.io/badge/Tool-pleading--to--proof-blue?logo=vercel)](https://pleading-to-proof-txpb.vercel.app/)

An AI evidence-mapping pipeline that stress-tests a litigation case theory by extracting the pleaded
allegations from a court bundle, retrieving the supporting and contradicting evidence for each one,
classifying and scoring it against English evidence-law principles, and presenting the result as an
auditable **proof matrix**, **risk dashboard**, and **evidence graph** in a web UI.

Every number in the output traces back to a verbatim quote in a real document — nothing is
free-generated.

## The case

The bundle is a synthetic English commercial dispute, **Meridian Retail Group plc v TechFlow
Solutions Limited** (claim HT-2025-000231, TCC) — a failed retail EPOS/inventory platform
implementation. 20 documents (pleadings, contracts, amendments, emails, witness statements, expert
reports, a defect log, letters, a UAT certificate) → 99 text chunks → 17 pleaded propositions.

The headline finding the pipeline surfaces: most of the claimant's allegations are **contradicted by
its own evidence** (its signed UAT certificate, its own experts, its own witnesses), while only the
platform-defects and wasted-expenditure claims stand up.

## Architecture — a 6-stage pipeline

Each stage is a standalone Python script that reads the previous stage's JSON and writes the next.
All thresholds/constants live at the top of each script.

| Stage | Script | Reads | Writes | What it does |
|---|---|---|---|---|
| 1 · Ingestion | `build_chunks.py` (+ `document_registry.py`, `extract.py`, `parsers.py`) | the 20 `.docx` files | `chunks.json`, `chunk_stats.json`, `registry.json` | Parses each document by type (contract clauses, witness paras, email threads, defect-log table, etc.) into citable chunks with a unified metadata schema + auto-generated legal citations. |
| 2 · Propositions | `build_propositions.py` | `chunks.json` | `propositions.json`, `chunks_with_embeddings.json` | Auto-detects Mode A (extract allegations from pleadings via Gemini) vs Mode B (cluster evidence with UMAP+HDBSCAN). Always embeds chunks (MiniLM). |
| 3 · Retrieval | `build_retrieval.py` | `chunks.json`, `chunks_with_embeddings.json`, `propositions.json` | `retrieval_results.json` | Per proposition: legal-tokenised BM25 + dense cosine → RRF fusion → cross-encoder NLI filter (labels supporting/contradicting, drops neutrals). RRF floor + targeted metadata pass-through rules. |
| 4 · Classification | `build_classification.py` | `retrieval_results.json` | `classification_results.json` | One Gemini call per chunk (temp 0) with a 7-layer hallucination-prevention stack: quote-first, programmatic substring validation, score/direction consistency, human-review quarantine. |
| 5 · Scoring | `build_scoring.py` | `classification_results.json`, `propositions.json` | `scoring_results.json` | Deterministic: weighted `proof_score`, asymmetric status thresholds, `CONTRADICTED_BY_OWN_EVIDENCE` overlay, `risk_score`, and a full citation audit trail. No LLM. |
| 6 · Graph | `build_graph.py` | all of the above + `registry.json` | populated **Neo4j Aura** graph + `graph_data.json` | Builds Document/Chunk/Proposition nodes and BELONGS_TO / SUPPORTS / CONTRADICTS / CORROBORATES / CITES edges; exports two views for the UI. |
| Final · UI data | `build_demo_data.py` | every stage output | `demo_data.json` | Merges everything into one file the frontend loads, plus a grounded one-line summary per proposition (Gemini, citation-anchored, validated). |

Supporting scripts: `test_connection.py` (Neo4j connectivity check), `schema.py` / `load_propositions.py`
(initial Neo4j scaffolding, superseded by `build_graph.py`), `verify.py` (Stage-1 spot checks),
`run_mode_b_validation.py` (forces Mode B and cross-checks it against Mode A →
`propositions_mode_b.json`, `mode_b_validation.json`).

## Frontend (`frontend/`)

A single-page **Vite + React** app (no routing — pure React state) that reads `demo_data.json` and
`graph_data.json` once on load. Styling follows the Stitch **DESIGN.md** ("Functional Minimalism":
Inter + Source Serif 4, flat, rectangular badges, 4px radius, no shadows).

Views: **Overview** (metric cards + risk chart), **Proof Matrix** (per-allegation table), **Risk
Dashboard** (risk × importance bubble chart, bubble size = proof strength), **Evidence Graph**
(force-directed, document/detailed toggle, similarity slider), and **Allegation Detail** (evidence
cards with verbatim quotes, source document titles, own-evidence banner, expandable passages) with a
slide-in **Document panel** (metadata + every parsed passage from that document).

## Tech stack

- **Python**: `python-docx`, `sentence-transformers` (`all-MiniLM-L6-v2` embeddings,
  `cross-encoder/nli-deberta-v3-base` NLI), `rank-bm25`, `umap-learn`, `hdbscan`, `scikit-learn`,
  `numpy`, `neo4j`, `python-dotenv`, `google-generativeai` (Gemini `gemini-2.5-flash`).
- **Frontend**: Vite, React, Tailwind CSS v4, Chart.js / react-chartjs-2, react-force-graph-2d.
- **Services**: Neo4j Aura (graph), Google Gemini API (proposition extraction, classification,
  summaries).

## Setup

```bash
# Python pipeline
python -m venv .venv
./.venv/Scripts/python.exe -m pip install neo4j python-dotenv python-docx \
    google-generativeai sentence-transformers scikit-learn numpy \
    rank-bm25 sentencepiece umap-learn hdbscan
```

Create a `.env` (gitignored) with your credentials:

```
NEO4J_URI=neo4j+s://<your-instance>.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=<password>
NEO4J_DATABASE=neo4j
GEMINI_API_KEY=<your-gemini-key>
```

## Running the pipeline

The 20 source `.docx` files (the synthetic bundle) live in `bundle/` (gitignored). Run the stages in
order **from the repo root**:

```bash
PYTHONUTF8=1 ./.venv/Scripts/python.exe pipeline/build_chunks.py          # Stage 1
PYTHONUTF8=1 ./.venv/Scripts/python.exe pipeline/build_propositions.py    # Stage 2  (Gemini)
PYTHONUTF8=1 ./.venv/Scripts/python.exe pipeline/build_retrieval.py       # Stage 3  (downloads NLI model)
PYTHONUTF8=1 ./.venv/Scripts/python.exe pipeline/build_classification.py  # Stage 4  (Gemini, ~85 calls)
PYTHONUTF8=1 ./.venv/Scripts/python.exe pipeline/build_scoring.py         # Stage 5
PYTHONUTF8=1 ./.venv/Scripts/python.exe graphdb/build_graph.py            # Stage 6  (writes to Neo4j Aura)
PYTHONUTF8=1 ./.venv/Scripts/python.exe pipeline/build_demo_data.py       # data/demo_data.json  (Gemini)
```

> Note: `graphdb/build_graph.py` **clears** the target Neo4j database (`DETACH DELETE`) before
> repopulating. All file locations are defined once in `config/paths.py`.

## Running the frontend

```bash
cd frontend
npm install
npm run dev        # → http://localhost:5173
```

The app needs `frontend/public/demo_data.json` and `frontend/public/graph_data.json`. To refresh them
after re-running the pipeline:

```bash
cp data/demo_data.json data/graph_data.json frontend/public/
```

## Repo layout

```
config/    paths.py — every input/output file location (single source)
lib/       document_registry.py, extract.py, parsers.py — shared Stage-1 helpers
pipeline/  build_chunks → build_propositions → build_retrieval → build_classification
           → build_scoring → build_demo_data (+ run_mode_b_validation)
graphdb/   build_graph + Neo4j utilities (test_connection, schema, load_propositions, verify)
data/      registry.json + every stage output (.json)
bundle/    the 20 source .docx  (gitignored)
frontend/  Vite + React app
```

## What's tracked vs regenerated

Late-stage outputs in `data/` are committed so the UI is inspectable without re-running the pipeline:
`registry.json`, `retrieval_results.json`, `classification_results.json`, `scoring_results.json`,
`graph_data.json`, `demo_data.json`, `propositions_mode_b.json`, `mode_b_validation.json`.

Early derived data is gitignored and regenerated by the scripts: `data/chunks.json`,
`data/chunk_stats.json`, `data/chunks_with_embeddings.json`, `data/propositions.json`. Also
gitignored: `.env`, the `bundle/` source `.docx`, `frontend/node_modules`, and the Stitch design
export.

## Notes

- `.mcp.json` configures the optional Google Stitch MCP (used to author the UI design system); it is
  not required to run anything.
- The pipeline is built to be case-agnostic: swap in a new `registry.json` + bundle and re-run.
