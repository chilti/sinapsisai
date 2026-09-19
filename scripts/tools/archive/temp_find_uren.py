import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import sys
import os
sys.path.append(os.path.abspath('.'))

from database.knowledge_graph import Neo4jGraphStore

db = Neo4jGraphStore()
with db.driver.session() as session:
    query = """
    MATCH (a:Academic {name: "U'REN CORTES, ALFRED BARRY"})
    RETURN a.name as name
    """
    res = session.run(query)
    for row in res:
        print("EXACT MATCH:", row['name'])

db.close()
