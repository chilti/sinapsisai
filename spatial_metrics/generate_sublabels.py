"""
generate_sublabels.py
=====================
Enriquece articles_clusters.json con sub-etiquetas de nivel 2 para clusters
grandes, usando KMeans espacial + centroide semántico + LLM (con fallback TF-IDF).

El flujo por sub-cluster es:
  1. KMeans divide el cluster en N regiones espaciales.
  2. Para cada región: se calcula el centroide en espacio de embeddings 768D.
  3. Se seleccionan los 10 títulos más cercanos al centroide.
  4. TF-IDF extrae las top-5 palabras clave.
  5. El LLM genera una etiqueta de 2-4 palabras en español.
  6. Fallback a TF-IDF si el LLM no está disponible o falla.

Resultado en articles_clusters.json:
  { "cluster_id": 1, "label": "...", ...,
    "sublabels": [
      {"label": "Ganadería bovina extensiva", "x": ..., "y": ..., "size": ..., "level": 2},
      ...
    ]
  }

Uso:
    /home/ambientesPy/revistaslatam/bin/python spatial_metrics/generate_sublabels.py
    /home/ambientesPy/revistaslatam/bin/python spatial_metrics/generate_sublabels.py --tier1-only
    /home/ambientesPy/revistaslatam/bin/python spatial_metrics/generate_sublabels.py --min-size 400 --n-sub 3
"""

import argparse
import json
import os
import re
import sys
import time

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Stop Words ────────────────────────────────────────────────────────────────

STOPWORDS = list(set([
    # Inglés genérico
    "the", "and", "of", "to", "in", "for", "is", "on", "that", "by", "this",
    "with", "from", "as", "it", "are", "we", "an", "be", "was", "or", "which",
    "study", "analysis", "results", "using", "used", "paper", "based", "model",
    "data", "also", "were", "show", "can", "has", "effect", "effects",
    "different", "two", "method", "methods", "between", "these", "their",
    "have", "been", "they", "than", "more", "other", "our", "new", "high",
    "low", "both", "well", "such", "will", "these", "time", "each",
    # Español genérico
    "de", "la", "el", "en", "y", "a", "los", "se", "del", "las", "un", "por",
    "con", "no", "una", "su", "para", "es", "al", "lo", "como", "más", "o",
    "pero", "sus", "le", "ya", "este", "esta", "estudio", "análisis",
    "resultados", "método", "desarrollo", "artículo", "trabajo", "presenta",
    "través", "mediante", "entre", "hacia", "sobre", "fueron", "bajo",
    # Ruido XML/HTML
    "mrow", "math", "xmlns", "inline", "msub", "mi", "mn", "mo", "msup",
]))


def clean_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer(
        max_df=0.85, min_df=1, max_features=3000,
        stop_words=STOPWORDS,
        strip_accents="unicode",
        ngram_range=(1, 2),
        token_pattern=r"(?u)\b[a-zA-ZáéíóúüñÁÉÍÓÚÜÑ]{4,}\b",
    )


def get_tfidf_keywords(texts: list, vectorizer: TfidfVectorizer, top_n: int = 5) -> list:
    """Retorna los top_n términos TF-IDF sin redundancias de n-gramas."""
    if not texts:
        return []
    try:
        matrix = vectorizer.fit_transform(texts)
        features = vectorizer.get_feature_names_out()
        scores = np.asarray(matrix.sum(axis=0)).flatten()
        ranked = sorted(zip(features, scores), key=lambda x: -x[1])

        selected = []
        for term, _ in ranked:
            if len(selected) >= top_n:
                break
            if not any(term in s or s in term for s in selected):
                selected.append(term)
        return [w.title() for w in selected]
    except Exception as e:
        print(f"    ⚠ TF-IDF error: {e}")
        return []


def get_representative_titles(
    sub_df: pd.DataFrame,
    all_vectors: np.ndarray,
    top_k: int = 10
) -> list:
    """
    Calcula el centroide en espacio de embeddings 768D y devuelve
    los top_k títulos más cercanos (mayor similitud coseno al centroide).
    """
    indices = sub_df.index.tolist()
    if len(indices) == 0:
        return []

    vecs = all_vectors[indices]
    centroid = np.mean(vecs, axis=0)
    centroid_norm = np.linalg.norm(centroid)
    if centroid_norm == 0:
        return sub_df["title"].dropna().head(top_k).tolist()

    norms = np.linalg.norm(vecs, axis=1)
    sims = np.dot(vecs, centroid) / (norms * centroid_norm + 1e-9)
    closest = np.argsort(-sims)[:top_k]
    global_indices = [indices[i] for i in closest]
    return sub_df.loc[global_indices, "title"].dropna().tolist()


def label_with_llm(
    client,
    model_name: str,
    keywords: list,
    representative_titles: list,
    parent_label: str,
) -> str | None:
    """
    Invoca el LLM para generar una sub-etiqueta en español de 2-4 palabras.
    Retorna None si falla para permitir fallback.
    """
    bullets = "\n".join(f"- {t}" for t in representative_titles[:10])
    kw_str = ", ".join(keywords[:5])

    prompt = f"""Analiza los siguientes títulos de artículos científicos que pertenecen a un SUB-GRUPO dentro del tema general: "{parent_label}".

Genera una etiqueta específica y descriptiva para este sub-grupo que lo diferencie claramente del tema general.

Reglas obligatorias:
1. La etiqueta debe describir el ángulo ESPECÍFICO de este sub-grupo (no repetir el tema general).
2. Debe ser muy corta: entre 2 y 4 palabras.
3. Debe estar en ESPAÑOL.
4. Responde ÚNICAMENTE con la etiqueta, sin explicaciones, sin comillas, sin introducciones.

Palabras clave del sub-grupo (TF-IDF):
{kw_str}

Títulos representativos del sub-grupo:
{bullets}

Etiqueta específica del sub-grupo:"""

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": "Eres un experto en clasificación de literatura científica mexicana. Generas etiquetas temáticas cortas y precisas en español."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=64,
            timeout=20.0,
        )
        label = response.choices[0].message.content.strip()
        # Limpiar comillas y espacios
        label = label.replace('"', "").replace("'", "").strip()
        # Eliminar artefactos de tokens especiales (<|...|>, [INST], etc.)
        label = re.sub(r"<\|[^|]*\|>|\[INST\]|\[/INST\]", "", label).strip()
        # Descartar si está vacío, es demasiado corto (1 sola palabra en inglés puro) o demasiado largo
        words = label.split()
        if not label or len(words) > 6 or len(label) < 4:
            return None
        # Descartar respuestas de una sola palabra si son pura ASCII (probablemente inglés sin traducir)
        if len(words) == 1 and label.isascii():
            return None
        return label
    except Exception as e:
        print(f"    ⚠ LLM error: {e}")
        return None


# ── Pipeline principal ────────────────────────────────────────────────────────

def generate_sublabels(
    csv_path: str,
    vectors_path: str,
    clusters_json_path: str,
    n_sub: int = 4,
    min_size: int = 1200,
    tier1_only: bool = False,
) -> None:

    if '--force' not in sys.argv and os.path.exists(clusters_json_path):
        try:
            with open(clusters_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if any(c.get('sublabels') for c in data):
                print(f"  -> Sub-etiquetas ya existen en {clusters_json_path}. Saltando sub-etiquetado...")
                return
        except Exception:
            pass

    # Cargar CSV con coordenadas 2D y metadatos
    print(f"Cargando {csv_path}...")
    df = pd.read_csv(csv_path)
    required = {"cluster", "title", "x", "y"}
    if missing := required - set(df.columns):
        raise ValueError(f"Columnas faltantes en CSV: {missing}")

    # Cargar embeddings 768D (necesarios para centroide semántico)
    print(f"Cargando embeddings desde {vectors_path}...")
    df_vec = pd.read_parquet(vectors_path)
    all_vectors = np.stack(df_vec["embedding"].values).astype(np.float32)
    print(f"  → {all_vectors.shape[0]:,} embeddings de dim {all_vectors.shape[1]}")

    # Verificar alineación (mismo orden que el CSV por índice)
    if len(df) != len(all_vectors):
        raise ValueError(
            f"Desalineación: CSV tiene {len(df)} filas pero vectors tiene {len(all_vectors)}. "
            "Ejecuta build_tiles.py y extract_vectors.py desde cero."
        )

    # Cargar clusters existentes
    print(f"Cargando {clusters_json_path}...")
    with open(clusters_json_path, "r", encoding="utf-8") as f:
        clusters = json.load(f)
    print(f"  → {len(clusters)} clusters existentes")

    # Intentar inicializar LLM
    client = None
    model_name = None
    try:
        from lib.llm_utils import get_openai_client, LLMConfig
        client = get_openai_client(async_mode=False)
        model_name = LLMConfig.get_model_name()
        print(f"  → LLM disponible: {model_name}")
    except Exception as e:
        print(f"  → ⚠ LLM no disponible, se usará TF-IDF como fallback: {e}")

    vectorizer = build_vectorizer()

    # Determinar qué clusters procesar
    threshold = 4000 if tier1_only else min_size
    clusters_by_id = {c["cluster_id"]: c for c in clusters}
    to_process = [c for c in clusters if c["size"] >= threshold]
    print(f"\nClusters a sub-etiquetar (size >= {threshold}): {len(to_process)}")

    total_llm_calls = 0
    total_tfidf_fallbacks = 0
    t_start = time.time()

    for cluster_meta in sorted(to_process, key=lambda x: -x["size"]):
        cid = cluster_meta["cluster_id"]
        cdf = df[df["cluster"] == cid].copy()
        n_docs = len(cdf)

        print(f"\n[Cluster {cid}] '{cluster_meta['label']}' | {n_docs:,} docs")

        actual_n = min(n_sub, n_docs // 50)
        if actual_n < 2:
            print(f"  → Cluster muy pequeño para sub-dividir. Saltando.")
            clusters_by_id[cid]["sublabels"] = []
            continue

        # KMeans espacial sobre coordenadas UMAP 2D
        coords = cdf[["x", "y"]].values
        km = KMeans(n_clusters=actual_n, n_init="auto", random_state=42, max_iter=300)
        cdf = cdf.copy()
        cdf["sub_cluster"] = km.fit_predict(coords)

        sublabels = []
        used_labels = {cluster_meta["label"].lower()}

        for sub_id in range(actual_n):
            sub_df = cdf[cdf["sub_cluster"] == sub_id]
            sub_size = len(sub_df)
            if sub_size < 10:
                continue

            cx = float(km.cluster_centers_[sub_id][0])
            cy = float(km.cluster_centers_[sub_id][1])

            # Textos para TF-IDF
            raw_texts = sub_df["title"].fillna("").astype(str).tolist()
            texts = [clean_text(t) for t in raw_texts if t.strip()]
            keywords = get_tfidf_keywords(texts, vectorizer, top_n=5)

            label = None

            # Intentar LLM con centroide semántico
            if client is not None:
                rep_titles = get_representative_titles(sub_df, all_vectors, top_k=10)
                label = label_with_llm(client, model_name, keywords, rep_titles, cluster_meta["label"])
                if label:
                    total_llm_calls += 1

            # Fallback a TF-IDF si el LLM falló
            if not label:
                # Elegir keyword no redundante con el cluster padre
                for kw in keywords:
                    if kw.lower() not in used_labels and not any(
                        kw.lower() in ul or ul in kw.lower() for ul in used_labels
                    ):
                        label = kw
                        break
                if not label:
                    label = keywords[0] if keywords else f"Sub-tema {sub_id + 1}"
                total_tfidf_fallbacks += 1

            used_labels.add(label.lower())

            sublabels.append({
                "label": label,
                "keywords": keywords,
                "x": cx,
                "y": cy,
                "size": sub_size,
                "level": 2,
            })
            print(f"  Sub {sub_id}: '{label}' ({sub_size:,} docs) [{('LLM' if total_llm_calls > 0 else 'TF-IDF')}]")

        sublabels.sort(key=lambda s: -s["size"])
        clusters_by_id[cid]["sublabels"] = sublabels

    # Asegurar campo sublabels en clusters no procesados
    for c in clusters:
        if "sublabels" not in c:
            c["sublabels"] = []

    # Guardar
    print(f"\nGuardando {clusters_json_path}...")
    with open(clusters_json_path, "w", encoding="utf-8") as f:
        json.dump(list(clusters_by_id.values()), f, ensure_ascii=False)

    elapsed = time.time() - t_start
    total_sub = sum(len(c.get("sublabels", [])) for c in clusters_by_id.values())
    print(f"\n✅ Listo en {elapsed:.0f}s")
    print(f"   {total_sub} sub-etiquetas para {len(to_process)} clusters")
    print(f"   LLM: {total_llm_calls} etiquetas | TF-IDF fallback: {total_tfidf_fallbacks}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera sub-etiquetas de nivel 2 para clusters de artículos usando LLM + TF-IDF."
    )
    parser.add_argument("--csv", default="data/maps/articles_umap.csv",
                        help="CSV con columnas: cluster, title, x, y (default: data/maps/articles_umap.csv)")
    parser.add_argument("--vectors", default="data/maps/articles_vectors.parquet",
                        help="Parquet con embeddings originales (default: data/maps/articles_vectors.parquet)")
    parser.add_argument("--json", default="public/tiles/articles_clusters.json",
                        help="JSON de clusters a enriquecer in-place (default: public/tiles/articles_clusters.json)")
    parser.add_argument("--n-sub", type=int, default=4,
                        help="Número máximo de sub-clusters por cluster (default: 4)")
    parser.add_argument("--min-size", type=int, default=1200,
                        help="Tamaño mínimo del cluster para sub-etiquetar (default: 1200)")
    parser.add_argument("--tier1-only", action="store_true",
                        help="Procesar solo clusters Tier 1 (>4000 puntos) — útil para pruebas rápidas")
    parser.add_argument("--force", action="store_true",
                        help="Forzar la regeneración de sub-etiquetas e ignorar cache")
    args = parser.parse_args()

    generate_sublabels(
        csv_path=args.csv,
        vectors_path=args.vectors,
        clusters_json_path=args.json,
        n_sub=args.n_sub,
        min_size=args.min_size,
        tier1_only=args.tier1_only,
    )
