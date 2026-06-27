"""Central file-path registry for the pipeline.

Every script reads/writes through these constants so the on-disk layout can change
in one place. Paths are computed relative to the repo root (this file's grandparent),
so scripts work regardless of the current working directory.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BUNDLE = ROOT / "bundle"
ENV = ROOT / ".env"

# --- Stage inputs / outputs (all under data/) ---
REGISTRY = str(DATA / "registry.json")
CHUNKS = str(DATA / "chunks.json")
CHUNK_STATS = str(DATA / "chunk_stats.json")
EMBEDDINGS = str(DATA / "chunks_with_embeddings.json")
PROPOSITIONS = str(DATA / "propositions.json")
RETRIEVAL = str(DATA / "retrieval_results.json")
CLASSIFICATION = str(DATA / "classification_results.json")
SCORING = str(DATA / "scoring_results.json")
GRAPH = str(DATA / "graph_data.json")
DEMO = str(DATA / "demo_data.json")
MODE_B = str(DATA / "propositions_mode_b.json")
MODE_B_VALIDATION = str(DATA / "mode_b_validation.json")
