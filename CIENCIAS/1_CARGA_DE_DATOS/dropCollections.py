from pymilvus import MilvusClient

client = MilvusClient(
    uri="http://localhost:19530",
    token="root:Milvus"
)

res = client.drop_collection(
    collection_name="ICN_InCitesRecords_Milvus_JSON"
)
print(res)

res = client.drop_collection(
    collection_name="Ciencias_08_25_InCitesRecords_Milvus_JSON_COS"
)
print(res)
res = client.drop_collection(
    collection_name="Ciencias_08_25_InCitesRecords_Milvus_JSON_COSINE"
)
print(res)
res = client.drop_collection(
    collection_name="Ciencias_08_25_InCitesRecords_Milvus_JSON"
)

print(res)