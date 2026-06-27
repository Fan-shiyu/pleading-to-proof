from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()

driver = GraphDatabase.driver(
    os.getenv("NEO4J_URI"),
    auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD"))
)

with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
    result = session.run("RETURN 'Connection successful' AS message")
    print(result.single()["message"])

driver.close()
