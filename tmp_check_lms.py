import lmstudio as lms
try:
    model = lms.embedding_model('text-embedding-nomic-ai-nomic-embed-text-v2-moe')
    emb = model.embed('test')
    print("TYPE:", type(emb))
    if hasattr(emb, '__dict__'):
        print("DICT:", emb.__dict__)
except Exception as e:
    print("ERROR:", e)
