from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
)

constraints = [
    "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (d:Document) REQUIRE d.id IS UNIQUE",
    "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT proposition_id IF NOT EXISTS FOR (p:Proposition) REQUIRE p.id IS UNIQUE",
]

with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
    for constraint in constraints:
        session.run(constraint)
        print(f"Created: {constraint[:60]}...")

driver.close()
print("Schema setup complete.")

# Edge types that will be created later by the pipeline:
# (:Chunk)-[:SUPPORTS {score, confidence, quote}]->(:Proposition)
# (:Chunk)-[:CONTRADICTS {score, confidence, quote}]->(:Proposition)
# (:Chunk)-[:CORROBORATES {similarity}]->(:Chunk)
# (:Document)-[:CITES]->(:Document)
# (:Chunk)-[:BELONGS_TO]->(:Document)
