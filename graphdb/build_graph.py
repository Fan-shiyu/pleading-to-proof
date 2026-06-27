"""Stage 6 — Neo4j Graph Layer.

Loads the full case into Neo4j Aura (Document / Chunk / Proposition nodes; BELONGS_TO,
SUPPORTS, CONTRADICTS, CORROBORATES, CITES edges) and exports graph_data.json with two
views (document_view, detailed_view) for the frontend.

WARNING: Step 1 clears the entire Aura database (DETACH DELETE) and repopulates it.

Run with UTF-8 console:
    PYTHONUTF8=1 ./.venv/Scripts/python.exe build_graph.py
"""

import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import json
import os
import re

import numpy as np
from dotenv import load_dotenv
from neo4j import GraphDatabase
from sklearn.metrics.pairwise import cosine_similarity

from config import paths

# --------------------------------------------------------------------------- #
# Named constants
# --------------------------------------------------------------------------- #

CORROBORATES_MIN_SIMILARITY = 0.30   # frontend slider filters above this at runtime
EVIDENCE_ACTIVE_MIN_EDGES = 1        # min SUPPORTS+CONTRADICTS edges -> evidentially active

LEGAL_TYPE_COLOUR = {
    "formation": "#6B7280",
    "scope_change": "#F59E0B",
    "timetable": "#F59E0B",
    "go_live_decision": "#EF4444",
    "acceptance": "#EF4444",
    "platform_defects": "#DC2626",
    "availability": "#DC2626",
    "training": "#6B7280",
    "misrepresentation": "#8B5CF6",
    "loss_wasted_expenditure": "#3B82F6",
    "loss_of_profit": "#3B82F6",
    "unclassified": "#9CA3AF",
}

STATUS_COLOUR = {
    "SUPPORTED": "#16A34A",
    "PARTIALLY_SUPPORTED": "#65A30D",
    "INCONCLUSIVE": "#D97706",
    "CONTRADICTED": "#DC2626",
    "STRONGLY_CONTRADICTED": "#991B1B",
    "CONTRADICTED_BY_OWN_EVIDENCE": "#7C3AED",
    "GAP": "#6B7280",
}

# CITES alias map (verbatim from spec)
CITES_ALIASES = {
    "TAB03": ["master services agreement", "the msa", "msa"],
    "TAB04": ["statement of work", "the sow", "sow-01"],
    "TAB07": ["change order no. 3", "change order 3", "co-003"],
    "TAB08": ["uat acceptance certificate", "acceptance certificate", "uat certificate"],
    "TAB09": ["go-live decision", "go-live email"],
    "TAB11": ["25 november outage", "northgate telecom", "nt-22841"],
    "TAB13": ["defect log", "issue log", "d-001", "d-002", "d-003"],
    "TAB15": ["techflow response", "harborne quinn"],
    "TAB19": ["whitfield", "dr whitfield", "dr alan whitfield"],
    "TAB20": ["greenhalgh", "fiona greenhalgh"],
}


# --------------------------------------------------------------------------- #
# CITES detection (per spec, doc_registry as a list of doc dicts)
# --------------------------------------------------------------------------- #

def detect_citations(chunk_text, doc_registry, current_doc_id):
    """Returns list of (cited_doc_id, verbatim_citation_text) tuples."""
    citations_found = []

    title_variants = {}
    for doc in doc_registry:
        doc_id = doc["doc_id"]
        if doc_id == current_doc_id:
            continue
        title_variants[doc["doc_title"].lower()] = doc_id
        for alias in CITES_ALIASES.get(doc_id, []):
            title_variants[alias] = doc_id

    sentences = re.split(r"(?<=[.!?])\s+", chunk_text)
    for sentence in sentences:
        sentence_lower = sentence.lower()
        for variant, cited_doc_id in title_variants.items():
            if variant in sentence_lower:
                citations_found.append((cited_doc_id, sentence.strip()))
                break  # one match per sentence
    return citations_found


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def main():
    load_dotenv(paths.ENV)
    driver = GraphDatabase.driver(
        os.environ["NEO4J_URI"],
        auth=(os.environ["NEO4J_USERNAME"], os.environ["NEO4J_PASSWORD"]),
    )

    registry = json.load(open(paths.REGISTRY, encoding="utf-8"))
    doc_registry = [v for k, v in registry.items() if not k.startswith("_")]
    chunks_with_emb = json.load(open(paths.EMBEDDINGS, encoding="utf-8"))
    classification_results = json.load(open(paths.CLASSIFICATION, encoding="utf-8"))
    scoring_results = json.load(open(paths.SCORING, encoding="utf-8"))

    # --- Step 1: clear ---
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        print("[Stage 6] Neo4j cleared")

    # --- Step 2: indexes ---
    with driver.session() as session:
        session.run("CREATE INDEX document_id IF NOT EXISTS FOR (d:Document) ON (d.doc_id)")
        session.run("CREATE INDEX chunk_id IF NOT EXISTS FOR (c:Chunk) ON (c.chunk_id)")
        session.run("CREATE INDEX proposition_id IF NOT EXISTS FOR (p:Proposition) ON (p.proposition_id)")
        print("[Stage 6] Indexes created")

    # --- Step 3: Document nodes (registry uses 'date' -> doc_date) ---
    with driver.session() as session:
        for doc in doc_registry:
            session.run("""
                CREATE (d:Document {
                    doc_id: $doc_id, doc_title: $doc_title, doc_type: $doc_type,
                    doc_date: $doc_date, author_party: $author_party,
                    source_quality_weight: $sqw,
                    edge_count: 0, is_evidence_active: false,
                    dominant_legal_type: null, colour_group: null
                })
            """, doc_id=doc["doc_id"], doc_title=doc["doc_title"], doc_type=doc["doc_type"],
                 doc_date=doc["date"], author_party=doc["author_party"],
                 sqw=doc["source_quality_weight"])
        print(f"[Stage 6] Document nodes: {len(doc_registry)}")

    # --- Step 4: Chunk nodes (no embedding) + BELONGS_TO ---
    with driver.session() as session:
        for c in chunks_with_emb:
            session.run("""
                CREATE (c:Chunk {
                    chunk_id: $chunk_id, doc_id: $doc_id, doc_title: $doc_title,
                    doc_type: $doc_type, author_party: $author_party, chunk_text: $chunk_text,
                    citation: $citation, source_quality_weight: $sqw,
                    paragraph_number: $paragraph_number, clause_number: $clause_number,
                    witness_name: $witness_name, expert_name: $expert_name,
                    token_count: $token_count
                })
            """, chunk_id=c["chunk_id"], doc_id=c["doc_id"], doc_title=c["doc_title"],
                 doc_type=c["doc_type"], author_party=c["author_party"], chunk_text=c["chunk_text"],
                 citation=c["citation"], sqw=c["source_quality_weight"],
                 paragraph_number=c.get("paragraph_number"), clause_number=c.get("clause_number"),
                 witness_name=c.get("witness_name"), expert_name=c.get("expert_name"),
                 token_count=c.get("token_count"))
            session.run("""
                MATCH (c:Chunk {chunk_id: $chunk_id})
                MATCH (d:Document {doc_id: $doc_id})
                CREATE (c)-[:BELONGS_TO]->(d)
            """, chunk_id=c["chunk_id"], doc_id=c["doc_id"])
        print(f"[Stage 6] Chunk nodes + BELONGS_TO: {len(chunks_with_emb)}")

    # --- Step 5: Proposition nodes ---
    with driver.session() as session:
        for p in scoring_results:
            session.run("""
                CREATE (p:Proposition {
                    proposition_id: $pid, allegation_number: $alleg,
                    proposition_text: $text, legal_element_type: $ltype,
                    importance_weight: $iw, proof_score: $proof, risk_score: $risk,
                    status: $status, classification_confidence: $conf,
                    is_own_evidence_contradiction: $own,
                    supporting_count: $sup, contradicting_count: $con, colour: $colour
                })
            """, pid=p["proposition_id"], alleg=p["allegation_number"],
                 text=p["proposition_text"], ltype=p["legal_element_type"],
                 iw=p["importance_weight"], proof=p["proof_score"], risk=p["risk_score"],
                 status=p["status"], conf=p["classification_confidence"],
                 own=p["is_own_evidence_contradiction"],
                 sup=p["supporting_count"], con=p["contradicting_count"],
                 colour=STATUS_COLOUR.get(p["status"], "#6B7280"))
        print(f"[Stage 6] Proposition nodes: {len(scoring_results)}")

    # --- Step 6: SUPPORTS / CONTRADICTS ---
    n_sup = n_con = 0
    with driver.session() as session:
        for prop in classification_results:
            prop_id = prop["proposition_id"]
            for chunk in prop["classified_chunks"]:
                if chunk.get("hallucination_flag") or chunk.get("score") is None:
                    continue
                wc = abs(chunk["score"]) * chunk["source_quality_weight"] * chunk["confidence"]
                if chunk["final_direction"] == "supporting" and chunk["score"] > 0:
                    session.run("""
                        MATCH (c:Chunk {chunk_id: $cid})
                        MATCH (p:Proposition {proposition_id: $pid})
                        CREATE (c)-[:SUPPORTS {
                            score: $score, confidence: $conf, source_quality_weight: $sqw,
                            weighted_contribution: $wc, verbatim_quote: $quote,
                            reason: $reason, citation: $citation
                        }]->(p)
                    """, cid=chunk["chunk_id"], pid=prop_id, score=chunk["score"],
                         conf=chunk["confidence"], sqw=chunk["source_quality_weight"],
                         wc=round(wc, 4), quote=chunk["verbatim_quote"],
                         reason=chunk["reason"], citation=chunk["citation"])
                    n_sup += 1
                elif chunk["final_direction"] == "contradicting" and chunk["score"] < 0:
                    session.run("""
                        MATCH (c:Chunk {chunk_id: $cid})
                        MATCH (p:Proposition {proposition_id: $pid})
                        CREATE (c)-[:CONTRADICTS {
                            score: $score, confidence: $conf, source_quality_weight: $sqw,
                            weighted_contribution: $wc, verbatim_quote: $quote,
                            reason: $reason, citation: $citation,
                            is_own_evidence: $own
                        }]->(p)
                    """, cid=chunk["chunk_id"], pid=prop_id, score=chunk["score"],
                         conf=chunk["confidence"], sqw=chunk["source_quality_weight"],
                         wc=round(wc, 4), quote=chunk["verbatim_quote"],
                         reason=chunk["reason"], citation=chunk["citation"],
                         own=(chunk.get("author_party") == "claimant"))
                    n_con += 1
        print(f"[Stage 6] SUPPORTS: {n_sup} | CONTRADICTS: {n_con}")

    # --- Step 7: Document edge_count / is_evidence_active / dominant_legal_type / colour ---
    with driver.session() as session:
        session.run("""
            MATCH (d:Document)
            OPTIONAL MATCH (c:Chunk)-[:BELONGS_TO]->(d)
            OPTIONAL MATCH (c)-[r:SUPPORTS|CONTRADICTS]->()
            WITH d, count(r) as ec
            SET d.edge_count = ec,
                d.is_evidence_active = (ec >= $min_edges)
        """, min_edges=EVIDENCE_ACTIVE_MIN_EDGES)

        session.run("""
            MATCH (d:Document)<-[:BELONGS_TO]-(c:Chunk)-[r:SUPPORTS|CONTRADICTS]->(p:Proposition)
            WITH d, p.legal_element_type as ltype, sum(r.weighted_contribution) as total_weight
            ORDER BY total_weight DESC
            WITH d, collect(ltype)[0] as dominant_type
            SET d.dominant_legal_type = dominant_type
            SET d.colour_group = CASE dominant_type
                WHEN 'platform_defects' THEN '#DC2626'
                WHEN 'availability' THEN '#DC2626'
                WHEN 'acceptance' THEN '#EF4444'
                WHEN 'go_live_decision' THEN '#EF4444'
                WHEN 'scope_change' THEN '#F59E0B'
                WHEN 'timetable' THEN '#F59E0B'
                WHEN 'loss_of_profit' THEN '#3B82F6'
                WHEN 'loss_wasted_expenditure' THEN '#3B82F6'
                WHEN 'misrepresentation' THEN '#8B5CF6'
                ELSE '#6B7280'
            END
        """)
        # Peripheral documents (no edges) -> 'unclassified' + light grey (validation 9)
        session.run("""
            MATCH (d:Document)
            WHERE d.dominant_legal_type IS NULL
            SET d.dominant_legal_type = 'unclassified', d.colour_group = '#9CA3AF'
        """)
        print("[Stage 6] Document properties updated")

    # --- Step 8: CITES ---
    n_cites = 0
    with driver.session() as session:
        for c in chunks_with_emb:
            found = detect_citations(c["chunk_text"], doc_registry, c["doc_id"])
            for cited_doc_id, verbatim_text in found:
                # MATCH the existing Documents first, then MERGE only the relationship.
                # (MERGE on the full path would create duplicate Document nodes.)
                session.run("""
                    MATCH (src:Document {doc_id: $src_id})
                    MATCH (tgt:Document {doc_id: $tgt_id})
                    MERGE (src)-[r:CITES]->(tgt)
                    ON CREATE SET r.citing_chunk_ids = [$chunk_id],
                                  r.verbatim_citation_texts = [$verbatim_text]
                    ON MATCH SET r.citing_chunk_ids = r.citing_chunk_ids + $chunk_id,
                                 r.verbatim_citation_texts = r.verbatim_citation_texts + $verbatim_text
                """, src_id=c["doc_id"], tgt_id=cited_doc_id,
                     chunk_id=c["chunk_id"], verbatim_text=verbatim_text)
                n_cites += 1
        print(f"[Stage 6] CITES edge-entries: {n_cites}")

    # --- Step 9: CORROBORATES ---
    emb_lookup = {c["chunk_id"]: np.array(c["embedding"]) for c in chunks_with_emb}
    corroborates_count = 0
    with driver.session() as session:
        for prop in classification_results:
            prop_id = prop["proposition_id"]
            for direction in ["supporting", "contradicting"]:
                active = [
                    c for c in prop.get("classified_chunks", [])
                    if c.get("final_direction") == direction
                    and not c.get("hallucination_flag")
                    and c.get("score") is not None
                ]
                if len(active) < 2:
                    continue
                chunk_ids = [c["chunk_id"] for c in active]
                doc_ids = [c["doc_id"] for c in active]
                embeddings = np.array([emb_lookup[cid] for cid in chunk_ids])
                sim_matrix = cosine_similarity(embeddings)
                for i in range(len(active)):
                    for j in range(i + 1, len(active)):
                        if doc_ids[i] == doc_ids[j]:
                            continue
                        similarity = float(sim_matrix[i][j])
                        if similarity < CORROBORATES_MIN_SIMILARITY:
                            continue
                        session.run("""
                            MATCH (c1:Chunk {chunk_id: $id1})
                            MATCH (c2:Chunk {chunk_id: $id2})
                            MERGE (c1)-[:CORROBORATES {
                                similarity: $sim,
                                shared_proposition_id: $prop_id,
                                shared_direction: $direction
                            }]->(c2)
                        """, id1=chunk_ids[i], id2=chunk_ids[j],
                             sim=round(similarity, 4), prop_id=prop_id, direction=direction)
                        corroborates_count += 1
        print(f"[Stage 6] CORROBORATES edges created: {corroborates_count}")

    # --- Export + validate + diagnostics ---
    graph_data = export_graph_data(driver)
    with open(paths.GRAPH, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2, ensure_ascii=False)
    print("[Stage 6] graph_data.json written")

    validate(driver, graph_data)
    diagnostics(driver, graph_data)
    driver.close()


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

def export_graph_data(driver):
    with driver.session() as session:
        doc_nodes = session.run("""
            MATCH (d:Document)
            RETURN d.doc_id as id, d.doc_title as label, 'document' as node_type,
                   d.doc_type as doc_type, d.author_party as author_party,
                   d.edge_count as edge_count, d.is_evidence_active as is_active,
                   d.dominant_legal_type as dominant_legal_type,
                   d.colour_group as colour, d.source_quality_weight as weight
        """).data()

        prop_nodes = session.run("""
            MATCH (p:Proposition)
            RETURN p.proposition_id as id, p.allegation_number as label,
                   'proposition' as node_type, p.proposition_text as text,
                   p.legal_element_type as legal_element_type,
                   p.status as status, p.proof_score as proof_score,
                   p.risk_score as risk_score, p.colour as colour,
                   p.is_own_evidence_contradiction as is_own_evidence,
                   p.importance_weight as importance_weight
        """).data()

        doc_to_prop_edges = session.run("""
            MATCH (d:Document)<-[:BELONGS_TO]-(c:Chunk)-[r:SUPPORTS|CONTRADICTS]->(p:Proposition)
            WITH d, p, type(r) as rel_type,
                 sum(r.weighted_contribution) as total_weight,
                 count(r) as edge_count,
                 collect(r.citation)[0] as top_citation
            RETURN d.doc_id as source, p.proposition_id as target,
                   rel_type as edge_type, total_weight, edge_count, top_citation
        """).data()

        cites_edges = session.run("""
            MATCH (src:Document)-[r:CITES]->(tgt:Document)
            RETURN src.doc_id as source, tgt.doc_id as target,
                   'CITES' as edge_type,
                   r.verbatim_citation_texts as verbatim_texts,
                   r.citing_chunk_ids as chunk_ids
        """).data()

        chunk_nodes = session.run("""
            MATCH (c:Chunk)-[:BELONGS_TO]->(d:Document)
            WHERE (c)-[:SUPPORTS|CONTRADICTS]->()
               OR ()-[:CORROBORATES]->(c)
            RETURN c.chunk_id as id, c.citation as label, 'chunk' as node_type,
                   c.doc_id as doc_id, c.doc_type as doc_type,
                   c.author_party as author_party, c.chunk_text as chunk_text,
                   c.citation as citation, c.source_quality_weight as weight,
                   d.colour_group as colour
        """).data()

        chunk_edges = session.run("""
            MATCH (c:Chunk)-[r:SUPPORTS|CONTRADICTS]->(p:Proposition)
            RETURN c.chunk_id as source, p.proposition_id as target,
                   type(r) as edge_type, r.score as score,
                   r.weighted_contribution as weight,
                   r.verbatim_quote as verbatim_quote,
                   r.reason as reason, r.citation as citation,
                   r.is_own_evidence as is_own_evidence
        """).data()

        corroborates_edges = session.run("""
            MATCH (c1:Chunk)-[r:CORROBORATES]->(c2:Chunk)
            RETURN c1.chunk_id as source, c2.chunk_id as target,
                   'CORROBORATES' as edge_type, r.similarity as similarity,
                   r.shared_proposition_id as proposition_id,
                   r.shared_direction as direction
        """).data()

        belongs_edges = session.run("""
            MATCH (c:Chunk)-[:BELONGS_TO]->(d:Document)
            WHERE (c)-[:SUPPORTS|CONTRADICTS]->()
            RETURN c.chunk_id as source, d.doc_id as target, 'BELONGS_TO' as edge_type
        """).data()

    return {
        "document_view": {
            "nodes": doc_nodes + prop_nodes,
            "edges": doc_to_prop_edges + cites_edges,
        },
        "detailed_view": {
            "nodes": doc_nodes + chunk_nodes + prop_nodes,
            "edges": chunk_edges + corroborates_edges + belongs_edges + cites_edges,
        },
        "metadata": {
            "document_count": len(doc_nodes),
            "chunk_count": len(chunk_nodes),
            "proposition_count": len(prop_nodes),
            "corroborates_edge_count": len(corroborates_edges),
            "cites_edge_count": len(cites_edges),
        },
    }


# --------------------------------------------------------------------------- #
# Validation (12 checks)
# --------------------------------------------------------------------------- #

def _count(session, query):
    return session.run(query).single()[0]


def validate(driver, graph_data):
    with driver.session() as session:
        assert _count(session, "MATCH (d:Document) RETURN count(d)") == 20, "not 20 Documents"
        assert _count(session, "MATCH (c:Chunk) RETURN count(c)") == 99, "not 99 Chunks"
        assert _count(session, "MATCH (p:Proposition) RETURN count(p)") == 17, "not 17 Propositions"
        assert _count(session, "MATCH (:Chunk)-[r:BELONGS_TO]->(:Document) RETURN count(r)") == 99, \
            "not 99 BELONGS_TO"
        bad_wc = _count(session, """
            MATCH (:Chunk)-[r:SUPPORTS|CONTRADICTS]->(:Proposition)
            WHERE r.weighted_contribution IS NULL OR r.weighted_contribution = 0
            RETURN count(r)
        """)
        assert bad_wc == 0, f"{bad_wc} edges with null/0 weighted_contribution"
        pleading_edges = _count(session, """
            MATCH (c:Chunk)-[r:SUPPORTS|CONTRADICTS]->(:Proposition)
            WHERE c.doc_type = 'pleading' RETURN count(r)
        """)
        assert pleading_edges == 0, f"{pleading_edges} edges on pleading chunks"
        bad_sim = _count(session, f"""
            MATCH (:Chunk)-[r:CORROBORATES]->(:Chunk)
            WHERE r.similarity < {CORROBORATES_MIN_SIMILARITY} RETURN count(r)
        """)
        assert bad_sim == 0, f"{bad_sim} CORROBORATES below min similarity"
        same_doc = _count(session, """
            MATCH (c1:Chunk)-[r:CORROBORATES]->(c2:Chunk)
            WHERE c1.doc_id = c2.doc_id RETURN count(r)
        """)
        assert same_doc == 0, f"{same_doc} CORROBORATES within same document"
        null_dom = _count(session, """
            MATCH (d:Document) WHERE d.dominant_legal_type IS NULL RETURN count(d)
        """)
        assert null_dom == 0, f"{null_dom} Documents with null dominant_legal_type"

    assert "document_view" in graph_data and "detailed_view" in graph_data, "missing views"
    for view in ("document_view", "detailed_view"):
        for n in graph_data[view]["nodes"]:
            for field in ("id", "label", "node_type", "colour"):
                assert field in n and n[field] is not None, \
                    f"{view} node {n.get('id')} missing {field}"
    for e in graph_data["detailed_view"]["edges"]:
        if e["edge_type"] in ("SUPPORTS", "CONTRADICTS"):
            assert e.get("verbatim_quote") and e.get("citation"), \
                f"detailed SUPPORTS/CONTRADICTS edge missing quote/citation"
    print("[Stage 6] All 12 validation checks passed.")


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #

def diagnostics(driver, graph_data):
    with driver.session() as session:
        counts = {
            "BELONGS_TO": _count(session, "MATCH ()-[r:BELONGS_TO]->() RETURN count(r)"),
            "SUPPORTS": _count(session, "MATCH ()-[r:SUPPORTS]->() RETURN count(r)"),
            "CONTRADICTS": _count(session, "MATCH ()-[r:CONTRADICTS]->() RETURN count(r)"),
            "CORROBORATES": _count(session, "MATCH ()-[r:CORROBORATES]->() RETURN count(r)"),
            "CITES": _count(session, "MATCH ()-[r:CITES]->() RETURN count(r)"),
        }
        docs = session.run("""
            MATCH (d:Document)
            RETURN d.doc_id as id, d.doc_title as title, d.dominant_legal_type as dom,
                   d.edge_count as ec ORDER BY d.doc_id
        """).data()

    print("\n[Stage 6] Graph build complete\n")
    print("Nodes:\n  Documents:    20\n  Chunks:       99\n  Propositions: 17")
    print("\nEdges:")
    for k, v in counts.items():
        suffix = f"  (similarity >= {CORROBORATES_MIN_SIMILARITY})" if k == "CORROBORATES" else ""
        print(f"  {k+':':14s}{v}{suffix}")

    print("\nDocument summary (by dominant legal type):")
    for d in docs:
        if d["ec"] > 0:
            print(f"  {d['id']} {d['title'][:38]:38s} -> {d['dom']:22s} edge_count={d['ec']}")

    print("\nEvidentially peripheral documents (edge_count=0):")
    for d in docs:
        if d["ec"] == 0:
            print(f"  {d['id']} {d['title']}")

    md = graph_data["metadata"]
    dv, det = graph_data["document_view"], graph_data["detailed_view"]
    print("\ngraph_data.json:")
    print(f"  document_view nodes: {len(dv['nodes'])}  edges: {len(dv['edges'])}")
    print(f"  detailed_view nodes: {len(det['nodes'])}  edges: {len(det['edges'])}")
    print(f"  metadata: {md}")


if __name__ == "__main__":
    main()
