import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

from config import paths
load_dotenv(paths.ENV)

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
)

with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:

    # Count propositions
    count = session.run("MATCH (p:Proposition) RETURN count(p) AS total").single()["total"]
    print(f"Total propositions in Neo4j: {count}")

    # Show all propositions
    print("\nAll propositions:")
    print("-" * 80)
    results = session.run("""
        MATCH (p:Proposition)
        RETURN p.id AS id,
               p.allegation_para AS para,
               p.expected_status AS expected,
               p.importance_weight AS weight,
               p.text AS text
        ORDER BY p.id
    """)
    for record in results:
        print(f"{record['id']} | {record['para']} | "
              f"Expected: {record['expected']} | "
              f"Weight: {record['weight']}")
        print(f"  {record['text'][:80]}...")
        print()

    # Show constraints
    print("Database constraints:")
    constraints = session.run("SHOW CONSTRAINTS")
    for c in constraints:
        print(f"  {c['name']}: {c['type']}")

driver.close()
print("\nVerification complete.")
