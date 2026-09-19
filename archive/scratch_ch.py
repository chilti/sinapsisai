import clickhouse_connect

client = clickhouse_connect.get_client(host='10.90.0.87', port=8124, username='rag_user', password='$B3tt3r-R4g-3veR-d0N3++', database='rag')
res = client.query("SELECT DISTINCT entity, count() FROM paper_author_map WHERE institution = 'UNIVERSIDAD NACIONAL AUTONOMA DE MEXICO (UNAM)' GROUP BY entity")
for r in res.result_rows:
    print(r)
