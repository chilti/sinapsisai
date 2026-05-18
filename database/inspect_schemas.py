import os
import json
from database.clickhouse_db import ch_client
from database.knowledge_graph import Neo4jGraphStore

def inspect_clickhouse():
    print("# CLICKHOUSE SCHEMAS\n")
    try:
        tables = ch_client.query("SHOW TABLES FROM rag").result_rows
        for (table_name,) in tables:
            print(f"## Table: {table_name}")
            # Usar backticks para nombres con guiones o caracteres especiales
            schema = ch_client.query(f"DESCRIBE rag.`{table_name}`").result_rows
            print("| Column | Type |")
            print("|--------|------|")
            for col in schema:
                name, ctype = col[0], col[1]
                print(f"| {name} | {ctype} |")
            print("\n")
    except Exception as e:
        print(f"Error inspecting ClickHouse: {e}")

def inspect_neo4j():
    print("# NEO4J SCHEMAS\n")
    graph = Neo4jGraphStore()
    try:
        with graph.driver.session() as session:
            # Labels and property keys
            print("## Node Labels and Properties")
            labels_res = session.run("CALL db.labels() YIELD label RETURN label")
            for rec in labels_res:
                label = rec['label']
                # Sample properties for this label
                prop_res = session.run(f"MATCH (n:`{label}`) RETURN keys(n) AS keys LIMIT 10")
                all_keys = set()
                for p_rec in prop_res:
                    all_keys.update(p_rec['keys'])
                print(f"### `{label}`\n**Properties:** {', '.join(sorted(all_keys))}\n")

            # Relationships
            print("## Relationship Types and Hierarchies")
            rel_res = session.run("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
            for rec in rel_res:
                rel = rec['relationshipType']
                print(f"### `[:{rel}]`")
                # Sample usage with direction and typical labels
                usage_res = session.run(f"MATCH (a)-[r:`{rel}`]->(b) RETURN labels(a) AS from, labels(b) AS to LIMIT 5")
                paths = set()
                for u in usage_res:
                    path_str = f"({', '.join(u['from'])}) -> (:{rel}) -> ({', '.join(u['to'])})"
                    paths.add(path_str)
                for p in paths:
                    print(f"- {p}")
                print("\n")
    except Exception as e:
        print(f"Error inspecting Neo4j: {e}")
    finally:
        graph.close()

if __name__ == "__main__":
    inspect_clickhouse()
    inspect_neo4j()
