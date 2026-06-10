"""
test_nomic_embeddings.py
========================
Script de diagnóstico para verificar la conectividad y funcionamiento
del modelo de embeddings Nomic (nomic-embed-text) usando las mismas
credenciales centralizadas en lib/llm_utils.py.

Uso:
    /home/ambientesPy/revistaslatam/bin/python scripts/diagnostics/test_nomic_embeddings.py

Pruebas que realiza:
    1. Conexión al servidor LM Studio y listado de modelos disponibles
    2. Generación de un embedding simple (texto corto)
    3. Generación en batch (múltiples textos)
    4. Verificación de dimensionalidad y rango de valores
    5. Prueba de similaridad coseno (textos similares vs. disímiles)
"""

import os
import sys
import time
import numpy as np

# Añadir raíz del proyecto al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from lib.llm_utils import LLMConfig, get_openai_client, get_embeddings_model

# ── Helpers ───────────────────────────────────────────────────────────────────

def cosine_similarity(a: list, b: list) -> float:
    va, vb = np.array(a), np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-9))

def banner(title: str):
    print(f"\n{'─' * 55}")
    print(f"  {title}")
    print(f"{'─' * 55}")

def ok(msg): print(f"  ✅ {msg}")
def fail(msg): print(f"  ❌ {msg}")
def info(msg): print(f"  ℹ  {msg}")

# ── Pruebas ───────────────────────────────────────────────────────────────────

def test_1_connection(client):
    banner("Prueba 1: Conexión al servidor LLM")
    info(f"Base URL : {LLMConfig.get_auth_url()}")
    info(f"API Key  : {LLMConfig.get_api_key()[:6]}***")
    info(f"Modelo   : {LLMConfig.get_embedding_model_name()}")
    try:
        models = client.models.list()
        names = [m.id for m in models.data]
        ok(f"Servidor responde. Modelos disponibles ({len(names)}):")
        for n in names:
            print(f"     • {n}")
        return True
    except Exception as e:
        fail(f"No se pudo conectar: {e}")
        return False


def test_2_single_embedding(client):
    banner("Prueba 2: Embedding de texto corto")
    model = LLMConfig.get_embedding_model_name()
    text = "Fotosíntesis en plantas tropicales de México"
    info(f"Texto: \"{text}\"")
    try:
        t0 = time.time()
        response = client.embeddings.create(model=model, input=[text])
        elapsed = time.time() - t0
        vec = response.data[0].embedding
        ok(f"Embedding generado en {elapsed:.2f}s")
        ok(f"Dimensionalidad: {len(vec)}")
        ok(f"Rango de valores: [{min(vec):.4f}, {max(vec):.4f}]")
        norm = np.linalg.norm(vec)
        ok(f"Norma L2: {norm:.4f}")
        return vec
    except Exception as e:
        fail(f"Error al generar embedding: {e}")
        return None


def test_3_batch_embeddings(client):
    banner("Prueba 3: Batch de embeddings")
    model = LLMConfig.get_embedding_model_name()
    texts = [
        "Síntesis de nanopartículas de plata",
        "Historia de la Revolución Mexicana",
        "Control de robots móviles autónomos",
        "Prevalencia de diabetes tipo 2 en México",
        "Observaciones astronómicas de galaxias lejanas",
    ]
    info(f"Batch de {len(texts)} textos:")
    for i, t in enumerate(texts):
        print(f"     [{i}] {t}")
    try:
        t0 = time.time()
        response = client.embeddings.create(model=model, input=texts)
        elapsed = time.time() - t0
        vecs = [r.embedding for r in response.data]
        ok(f"Batch generado en {elapsed:.2f}s ({elapsed/len(texts)*1000:.0f} ms/texto)")
        ok(f"Vectores recibidos: {len(vecs)}")
        ok(f"Dimensiones: {len(vecs[0])}")
        return vecs, texts
    except Exception as e:
        fail(f"Error en batch: {e}")
        return None, None


def test_4_similarity(vecs, texts):
    banner("Prueba 4: Similaridad coseno")
    if not vecs:
        fail("No hay vectores de la prueba anterior.")
        return

    info("Matriz de similaridad (pares seleccionados):\n")
    pairs = [
        (0, 1, "Química vs. Historia"),
        (0, 2, "Química vs. Robótica"),
        (0, 3, "Química vs. Salud"),
        (1, 4, "Historia vs. Astronomía"),
        (2, 4, "Robótica vs. Astronomía"),
    ]
    for i, j, label in pairs:
        sim = cosine_similarity(vecs[i], vecs[j])
        bar = "█" * int(sim * 20)
        print(f"     {label:<30} sim={sim:.4f}  |{bar}")

    # El par más similar debería ser temas relacionados
    sims = [(i, j, cosine_similarity(vecs[i], vecs[j])) for i in range(len(texts)) for j in range(i+1, len(texts))]
    best = max(sims, key=lambda x: x[2])
    worst = min(sims, key=lambda x: x[2])
    print()
    ok(f"Par más similar   : [{best[0]}] & [{best[1]}] → {best[2]:.4f}")
    print(f"     \"{texts[best[0]]}\"")
    print(f"     \"{texts[best[1]]}\"")
    ok(f"Par más distante  : [{worst[0]}] & [{worst[1]}] → {worst[2]:.4f}")
    print(f"     \"{texts[worst[0]]}\"")
    print(f"     \"{texts[worst[1]]}\"")


def test_5_langchain_wrapper():
    banner("Prueba 5: Wrapper LangChain (get_embeddings_model)")
    try:
        emb_model = get_embeddings_model()
        text = "Ciencia abierta y acceso a publicaciones académicas"
        info(f"Texto: \"{text}\"")
        t0 = time.time()
        vec = emb_model.embed_query(text)
        elapsed = time.time() - t0
        ok(f"LangChain wrapper funciona correctamente")
        ok(f"Tiempo: {elapsed:.2f}s | Dim: {len(vec)}")
        return True
    except Exception as e:
        fail(f"Error con LangChain wrapper: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 55)
    print("  TEST: Modelo de Embeddings Nomic")
    print("=" * 55)

    client = get_openai_client(async_mode=False)

    ok_conn = test_1_connection(client)
    if not ok_conn:
        print("\n⛔ Abortando: no hay conexión al servidor LLM.")
        sys.exit(1)

    test_2_single_embedding(client)
    vecs, texts = test_3_batch_embeddings(client)
    test_4_similarity(vecs, texts)
    test_5_langchain_wrapper()

    print("\n" + "=" * 55)
    print("  Diagnóstico completado.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
