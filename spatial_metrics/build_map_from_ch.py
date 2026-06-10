"""
build_map_from_ch.py
====================
Genera un nuevo mapa semántico de artículos directamente desde ClickHouse.

Fuentes:
  - embeddings_cache: embeddings SPECTER2 de 990K artículos (id = OpenAlex Work ID)
  - works_academic_all: metadatos (title, doi, topic, source_id, etc.)
  - paper_author_map: autores nacionales por paper
  - sources: nombre de revistas

Salida:
  - data/maps/articles_ch_umap.csv  (coordenadas UMAP con OpenAlex ID como ID)
  - public/tiles/articles_ch_data.json (JSON del mapa para el visor WebGL)

Uso:
  python spatial_metrics/build_map_from_ch.py
  python spatial_metrics/build_map_from_ch.py --sample 50000   # prueba rápida
  python spatial_metrics/build_map_from_ch.py --skip-umap       # solo regenerar JSON desde CSV existente
"""

import os
import sys
import json
import argparse
import numpy as np
import pandas as pd
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from database.clickhouse_db import ch_client

# ── Configuración ─────────────────────────────────────────────────────────────
OUT_CSV  = "data/maps/articles_ch_umap.csv"
OUT_JSON = "public/tiles/articles_ch_data.json"

# ── Helpers ───────────────────────────────────────────────────────────────────
def format_authors(authors):
    if not isinstance(authors, (list, tuple)) or len(authors) == 0:
        return ""
    if len(authors) <= 2:
        return " y ".join(str(a) for a in authors)
    return f"{authors[0]} et al."


def build_umap(df_emb, n_components=2, n_neighbors=15, min_dist=0.1, sample=None):
    from umap import UMAP

    vecs = np.array(df_emb["embedding"].tolist(), dtype=np.float32)
    if sample and sample < len(vecs):
        idx = np.random.choice(len(vecs), sample, replace=False)
        vecs = vecs[idx]
        df_emb = df_emb.iloc[idx].copy()
        print(f"  Usando muestra de {sample:,} vectores para UMAP")

    print(f"  Ejecutando UMAP sobre {len(vecs):,} vectores ({vecs.shape[1]}d)...")
    reducer = UMAP(n_components=n_components, n_neighbors=n_neighbors,
                   min_dist=min_dist, metric="cosine", random_state=42, verbose=True)
    coords = reducer.fit_transform(vecs)
    df_emb = df_emb.copy()
    df_emb["x"] = coords[:, 0]
    df_emb["y"] = coords[:, 1]
    return df_emb


def build_json(df, out_path):
    """Construye el JSON del mapa para el visor WebGL."""
    print(f"  Construyendo JSON para {len(df):,} puntos...")

    # Institución primaria = México para simplificar (o la primera del array)
    institutions = df["institution"].fillna("México").unique().tolist()
    inst_map = {n: i for i, n in enumerate(institutions)}

    data = {
        "x":            df["x"].round(4).tolist(),
        "y":            df["y"].round(4).tolist(),
        "names":        df["title"].astype(str).fillna("").tolist(),
        "institutions": df["institution"].fillna("México").tolist(),
        "inst_idx":     df["institution"].fillna("México").map(inst_map).tolist(),
        "inst_labels":  institutions[:20],
        "total":        len(df),
        "extras": {
            "doi":          df["doi"].fillna("").tolist(),
            "openalex_id":  df["id"].fillna("").tolist(),   # OpenAlex Work ID completo
            "year":         df["publication_year"].fillna("").astype(str).tolist(),
            "authors":      df["authors"].fillna("").tolist(),
            "journal":      df["journal"].fillna("").tolist(),
            "cluster_label": df["subfield"].fillna("").tolist(),
        }
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(data, f)
    mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"  ✅ Exportado a {out_path} ({mb:.1f} MB)")


def main(sample=None, skip_umap=False):
    client = ch_client.get_client()

    if skip_umap:
        # ── Sólo regenerar JSON desde CSV existente ──────────────────────────
        print(f"\n[Modo skip-umap] Leyendo coordenadas desde {OUT_CSV}...")
        if not os.path.exists(OUT_CSV):
            print(f"❌ No existe {OUT_CSV}. Ejecuta sin --skip-umap primero.")
            sys.exit(1)
        df = pd.read_csv(OUT_CSV)
    else:
        # ── Paso 1: Leer embeddings desde works_academic_all ─────────────────
        # Fuente única de verdad, actualizada por sync_analytics_pipeline.py
        # + embed_works.py para los embeddings
        print("\n[Paso 1] Leyendo embeddings desde works_academic_all...")
        limit_clause = f"LIMIT {sample}" if sample else ""
        q_emb = f"""
        SELECT id, embedding_nomic AS embedding,
               title, doi, publication_year, subfield, topic, source_id
        FROM works_academic_all
        WHERE length(embedding_nomic) > 0
        {limit_clause}
        """
        df_emb = client.query_df(q_emb)
        print(f"  → {len(df_emb):,} artículos con embeddings Nomic")

        if df_emb.empty:
            print("❌ No hay embeddings en works_academic_all.")
            print("   Ejecuta primero: python spatial_metrics/embed_works.py")
            sys.exit(1)

        # ── Paso 2: Proyección UMAP ───────────────────────────────────────────
        print("\n[Paso 2] Proyectando embeddings con UMAP...")
        df_coords = build_umap(df_emb, sample=None)
        df_coords = df_coords[["id", "x", "y", "subfield", "publication_year", "title", "doi", "source_id"]]

        # ── Paso 3: Autores nacionales desde paper_author_map ────────────────
        print("\n[Paso 3] Obteniendo autores nacionales...")
        q_authors = """
        SELECT paper_id AS oa_id, groupArray(academic_name) AS author_names
        FROM paper_author_map
        WHERE paper_id LIKE 'https://openalex.org/%'
        GROUP BY paper_id
        """
        df_authors = client.query_df(q_authors)
        df_authors["authors"] = df_authors["author_names"].apply(format_authors)
        df_coords = df_coords.merge(df_authors[["oa_id", "authors"]], left_on="id", right_on="oa_id", how="left")

        # ── Paso 4: Nombres de revistas ───────────────────────────────────────
        print("\n[Paso 4] Obteniendo nombres de revistas...")
        q_sources = "SELECT id AS source_id, display_name AS journal FROM sources"
        df_sources = client.query_df(q_sources).drop_duplicates(subset=["source_id"])
        df_coords = df_coords.merge(df_sources, on="source_id", how="left")

        # Columnas finales
        df_coords["institution"] = "México"
        df_coords["doi"] = df_coords["doi"].fillna("").astype(str).str.replace("https://doi.org/", "", regex=False)
        df_coords["title"] = df_coords["title"].fillna("Sin título")
        df_coords["authors"] = df_coords["authors"].fillna("")
        df_coords["journal"] = df_coords["journal"].fillna("")
        df_coords["subfield"] = df_coords["subfield"].fillna("")
        df_coords["publication_year"] = df_coords["publication_year"].fillna("").astype(str)

        df = df_coords[[
            "id", "doi", "title", "publication_year", "subfield",
            "institution", "x", "y", "authors", "journal"
        ]].copy()

        # ── Paso 6: Guardar CSV ───────────────────────────────────────────────
        os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
        df.to_csv(OUT_CSV, index=False)
        print(f"\n✅ CSV guardado: {OUT_CSV} ({len(df):,} filas)")

    # ── Paso 7: Generar JSON del mapa ─────────────────────────────────────────
    print(f"\n[Paso 7] Generando JSON del mapa...")
    build_json(df, OUT_JSON)
    print("\n🎉 ¡Mapa desde ClickHouse listo!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera mapa semántico desde ClickHouse")
    parser.add_argument("--sample", type=int, default=None,
                        help="Limitar a N embeddings (para pruebas rápidas)")
    parser.add_argument("--skip-umap", action="store_true",
                        help="Saltar UMAP y sólo regenerar JSON desde CSV existente")
    args = parser.parse_args()
    main(sample=args.sample, skip_umap=args.skip_umap)
