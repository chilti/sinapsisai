"""
embed_works.py
==============
Genera y sincroniza embeddings para los artículos en works_academic_all
que aún no los tienen.

Fases:
  --phase nomic     Genera embedding_nomic con el modelo Nomic (LM Studio local)
  --phase specter   Copia embedding_specter desde embeddings_cache (SPECTER2) y genera en GPU los restantes
  --phase all       Ambas fases (default)

Uso:
    # Ver cuántos faltan
    python spatial_metrics/embed_works.py --dry-run

    # Procesar todo
    python spatial_metrics/embed_works.py --phase all

    # Solo Nomic, con límite de prueba
    python spatial_metrics/embed_works.py --phase nomic --limit 500 --batch 32

    # Solo copiar/calcular SPECTER2
    python spatial_metrics/embed_works.py --phase specter
"""

import os
import sys
import time
import argparse
import pandas as pd
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from database.clickhouse_db import ch_client
from lib.llm_utils import LLMConfig, get_openai_client

# ── Config ─────────────────────────────────────────────────────────────────────
TABLE         = "works_academic_all"
DEFAULT_BATCH = 64
CHUNK_SIZE    = 5_000
ACCUM_TABLE   = "tmp_embs_to_apply"


# ── Helpers ────────────────────────────────────────────────────────────────────

def build_text(row: dict) -> str:
    """Texto de entrada para el modelo: título + tema."""
    title    = (row.get("title")    or "").strip()
    topic    = (row.get("topic")    or "").strip()
    subfield = (row.get("subfield") or "").strip()
    parts = [p for p in [title, topic, subfield] if p]
    return " | ".join(parts) if parts else "unknown"


def embed_batch(client_llm, texts: list[str], model: str) -> list[list[float]]:
    resp = client_llm.embeddings.create(model=model, input=texts)
    return [r.embedding for r in resp.data]


def upsert_embeddings(client_ch, ids: list[str], vecs: list, col: str):
    """Acumula los vectores de embeddings en la tabla temporal tmp_embs_to_apply."""
    df_tmp = pd.DataFrame({
        "id": ids,
        "embedding_nomic": [v if col == "embedding_nomic" else [] for v in vecs],
        "embedding_specter": [v if col == "embedding_specter" else [] for v in vecs]
    })
    client_ch.insert_df(ACCUM_TABLE, df_tmp)


def apply_accumulated_embeddings(client_ch):
    """
    Aplica todos los embeddings acumulados en tmp_embs_to_apply a la tabla principal
    mediante un LEFT JOIN e INSERT INTO (reemplazo de tabla 100% síncrono y fiable en 30s).
    """
    # Verificar si la tabla de acumulación existe y tiene registros
    res_exists = client_ch.query(f"EXISTS TABLE {ACCUM_TABLE}").result_rows[0][0]
    if res_exists == 0:
        return

    res_count = client_ch.query(f"SELECT count() FROM {ACCUM_TABLE}").result_rows[0][0]
    if res_count == 0:
        client_ch.command(f"DROP TABLE IF EXISTS {ACCUM_TABLE}")
        return

    print(f"\n🔄 Aplicando {res_count:,} embeddings acumulados a {TABLE}...")
    t0 = time.time()

    # 1. Crear tabla temporal vacía idéntica a la principal
    client_ch.command(f"DROP TABLE IF EXISTS {TABLE}_temp")
    client_ch.command(f"CREATE TABLE {TABLE}_temp AS {TABLE}")

    # 2. Hacer la unión y volcar los datos a la tabla temporal
    client_ch.command(f"""
        INSERT INTO {TABLE}_temp
        SELECT 
            id, raw_data, doi, title, publication_year, cited_by_count, is_oa, type, updated_date, is_xpac, source_id,
            author_names, institution_rors, institution_names, primary_topic_id, institution_ids, subfield, field, domain,
            topic, language, oa_status, fwci, percentile, is_top_10, is_top_1, country_code, source_type, sdg_ids, awards,
            concept_ids, all_country_codes, apc_paid_usd, apc_list_usd, counts_by_year, is_doaj_indexed, is_doaj_journal,
            is_core_journal, is_retracted, has_repository_fulltext, license, referenced_works_count, keywords, sdgs,
            journal_is_in_doaj, journal_is_core, any_repository_has_fulltext,
            if(length(n.embedding_nomic) > 0, n.embedding_nomic, embedding_nomic) AS embedding_nomic,
            if(length(n.embedding_specter) > 0, n.embedding_specter, embedding_specter) AS embedding_specter,
            embedding_fastrp
        FROM {TABLE} AS w
        LEFT JOIN (
            SELECT 
                id,
                arrayFilter(x -> length(x) > 0, groupArray(embedding_nomic))[-1] AS embedding_nomic,
                arrayFilter(x -> length(x) > 0, groupArray(embedding_specter))[-1] AS embedding_specter
            FROM {ACCUM_TABLE}
            GROUP BY id
        ) AS n ON w.id = n.id
    """)

    # 3. Intercambiar tablas
    client_ch.command(f"DROP TABLE {TABLE}")
    client_ch.command(f"RENAME TABLE {TABLE}_temp TO {TABLE}")

    # 4. Eliminar la tabla de acumulación
    client_ch.command(f"DROP TABLE {ACCUM_TABLE}")
    print(f"✅ Reemplazo de tabla finalizado en {time.time() - t0:.2f} segundos.")


# ── Fase Nomic ─────────────────────────────────────────────────────────────────

def phase_nomic(client_ch, client_llm, model, limit=None, batch_size=DEFAULT_BATCH, dry_run=False):
    if not dry_run:
        client_ch.command(f"""
            CREATE TABLE IF NOT EXISTS {ACCUM_TABLE} (
                id String,
                embedding_nomic Array(Float32) DEFAULT [],
                embedding_specter Array(Float32) DEFAULT []
            ) ENGINE = MergeTree
            ORDER BY id
        """)

    r = client_ch.query(f"SELECT count() FROM {TABLE} WHERE length(embedding_nomic) = 0")
    pending = r.result_rows[0][0]
    print(f"\n📊 [Nomic] Sin embedding_nomic: {pending:,}")
    if dry_run or pending == 0:
        return

    if limit:
        pending = min(pending, limit)
        print(f"  ⚠️  Procesando solo {limit:,} por --limit")

    processed = 0
    t_start = time.time()

    while processed < pending:
        n = min(CHUNK_SIZE, pending - processed)
        df_chunk = client_ch.query_df(
            f"SELECT id, title, topic, subfield FROM {TABLE} "
            f"WHERE length(embedding_nomic) = 0 "
            f"AND id NOT IN (SELECT id FROM {ACCUM_TABLE} WHERE length(embedding_nomic) > 0) "
            f"LIMIT {n}"
        )
        if df_chunk.empty:
            break

        rows = df_chunk.to_dict("records")
        ids_out, vecs_out = [], []

        for start in range(0, len(rows), batch_size):
            sub = rows[start: start + batch_size]
            ids_sub = [r["id"] for r in sub]
            texts   = [build_text(r) for r in sub]
            try:
                vecs = embed_batch(client_llm, texts, model)
                ids_out.extend(ids_sub)
                vecs_out.extend(vecs)
            except Exception as e:
                print(f"\n  ⚠️  Error sub-lote: {e}")
                continue

        if ids_out:
            upsert_embeddings(client_ch, ids_out, vecs_out, "embedding_nomic")
            processed += len(ids_out)
            elapsed = time.time() - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (pending - processed) / rate / 60 if rate > 0 else 0
            print(f"  ✅ Nomic {processed:,}/{pending:,} | {rate:.0f} art/s | ETA ≈{eta:.0f} min", end="\r", flush=True)

    elapsed_total = time.time() - t_start
    print(f"\n\n🎉 Nomic terminado. {processed:,} embeddings listos para aplicar.")


# ── Fase SPECTER2 ──────────────────────────────────────────────────────────────

def phase_specter(client_ch, dry_run=False, limit=None, batch_size=DEFAULT_BATCH):
    """
    1. Copia embedding_specter2 desde embeddings_cache hacia la tabla temporal.
    2. Genera en la GPU localmente usando SPECTER2 para los que queden vacíos.
    """
    if not dry_run:
        client_ch.command(f"""
            CREATE TABLE IF NOT EXISTS {ACCUM_TABLE} (
                id String,
                embedding_nomic Array(Float32) DEFAULT [],
                embedding_specter Array(Float32) DEFAULT []
            ) ENGINE = MergeTree
            ORDER BY id
        """)

    # ── 1. Copiar desde embeddings_cache ──
    r = client_ch.query(
        f"SELECT count() FROM {TABLE} WHERE length(embedding_specter) = 0"
        " AND id IN (SELECT id FROM embeddings_cache WHERE length(embedding_specter2) > 0)"
    )
    pending_cache = r.result_rows[0][0]
    print(f"\n📊 [SPECTER2] Disponibles en embeddings_cache para copiar: {pending_cache:,}")

    if not dry_run and pending_cache > 0:
        print("  ⏳ Copiando desde embeddings_cache hacia la tabla de acumulación...")
        # Crear la tabla de acumulación
        client_ch.command(f"""
            CREATE TABLE IF NOT EXISTS {ACCUM_TABLE} (
                id String,
                embedding_nomic Array(Float32) DEFAULT [],
                embedding_specter Array(Float32) DEFAULT []
            ) ENGINE = MergeTree
            ORDER BY id
        """)
        # Insertar los registros desde la cache directamente
        client_ch.command(f"""
            INSERT INTO {ACCUM_TABLE} (id, embedding_specter)
            SELECT id, embedding_specter2
            FROM embeddings_cache
            WHERE length(embedding_specter2) > 0
              AND id IN (SELECT id FROM {TABLE} WHERE length(embedding_specter) = 0)
        """)
        print("  ✅ Copia de caché finalizada.")

    # ── 2. Calcular localmente en GPU para los restantes ──
    r2 = client_ch.query(f"SELECT count() FROM {TABLE} WHERE length(embedding_specter) = 0")
    pending_gen = r2.result_rows[0][0]
    # Restamos los que ya copiamos en el acumulador en esta corrida si no hemos aplicado aún
    if not dry_run:
        pending_gen = max(0, pending_gen - pending_cache)

    print(f"📊 [SPECTER2] Restantes sin embedding_specter (para calcular localmente en GPU): {pending_gen:,}")

    if dry_run or pending_gen == 0:
        return

    if limit:
        pending_gen = min(pending_gen, limit)
        print(f"  ⚠️  Procesando solo {limit:,} por --limit")

    print("🧠 Cargando modelo SPECTER2 local (SentenceTransformer en GPU)...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('allenai/specter2_base')

    processed = 0
    t_start = time.time()

    while processed < pending_gen:
        n = min(CHUNK_SIZE, pending_gen - processed)
        df_chunk = client_ch.query_df(
            f"SELECT id, title, topic, subfield FROM {TABLE} "
            f"WHERE length(embedding_specter) = 0 "
            f"AND id NOT IN (SELECT id FROM {ACCUM_TABLE} WHERE length(embedding_specter) > 0) "
            f"LIMIT {n}"
        )
        if df_chunk.empty:
            break

        rows = df_chunk.to_dict("records")
        ids_out, vecs_out = [], []

        for start in range(0, len(rows), batch_size):
            sub = rows[start: start + batch_size]
            ids_sub = [r["id"] for r in sub]
            texts   = [build_text(r) for r in sub]
            try:
                # model.encode corre en CUDA automáticamente si está disponible
                vecs = model.encode(texts, convert_to_numpy=True).tolist()
                ids_out.extend(ids_sub)
                vecs_out.extend(vecs)
            except Exception as e:
                print(f"\n  ⚠️  Error sub-lote SPECTER2: {e}")
                continue

        if ids_out:
            upsert_embeddings(client_ch, ids_out, vecs_out, "embedding_specter")
            processed += len(ids_out)
            elapsed = time.time() - t_start
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (pending_gen - processed) / rate / 60 if rate > 0 else 0
            print(f"  ✅ SPECTER2 {processed:,}/{pending_gen:,} | {rate:.0f} art/s | ETA ≈{eta:.0f} min", end="\r", flush=True)

    elapsed_total = time.time() - t_start
    print(f"\n\n🎉 SPECTER2 terminado. {processed:,} embeddings listos para aplicar.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main(phase="all", dry_run=False, limit=None, batch_size=DEFAULT_BATCH):
    client_ch = ch_client.get_client()

    # Limpiar tabla de acumulación previa en caso de fallos anteriores
    if not dry_run:
        client_ch.command(f"DROP TABLE IF EXISTS {ACCUM_TABLE}")

    if phase in ("nomic", "all"):
        client_llm = get_openai_client(async_mode=False)
        model = LLMConfig.get_embedding_model_name()
        print(f"🤖 Modelo Nomic: {model}")
        phase_nomic(client_ch, client_llm, model,
                    limit=limit, batch_size=batch_size, dry_run=dry_run)

    if phase in ("specter", "all"):
        phase_specter(client_ch, dry_run=dry_run, limit=limit, batch_size=batch_size)

    # Aplicar todos los cambios acumulados de forma síncrona y eficiente
    if not dry_run:
        apply_accumulated_embeddings(client_ch)

    if dry_run:
        print("\n(--dry-run: no se procesaron embeddings)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera/sincroniza embeddings en works_academic_all")
    parser.add_argument("--phase", choices=["nomic", "specter", "all"], default="all",
                        help="Modelo a procesar (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar cuántos faltan, sin procesar")
    parser.add_argument("--limit", type=int, default=None,
                        help="Procesar solo N artículos (para pruebas)")
    parser.add_argument("--batch", type=int, default=DEFAULT_BATCH,
                        help=f"Textos por llamada al modelo (default: {DEFAULT_BATCH})")
    args = parser.parse_args()
    main(phase=args.phase, dry_run=args.dry_run, limit=args.limit, batch_size=args.batch)
