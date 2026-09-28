"""
lib/knomap_bridge.py - Puente de Exportación e Interoperabilidad con KnoMap
Genera:
1. .bib enriquecido con todos los datos mínimos de una referencia canónica y tag annote con métricas.
2. .json canónico estandarizado.
3. .parquet normalizado compatible con bibliographic-corpus-parser.
4. Paquete de proyecto .knomap (ZIP con corpus.parquet, author_network.json, topics_matrix.parquet y manifest.json).
"""

import os
import re
import io
import json
import zipfile
import hashlib
from datetime import datetime
from typing import List, Dict, Any, Optional
import pandas as pd
from database.clickhouse_db import ch_client

def clean_latex_str(text: Any) -> str:
    """Escapa caracteres especiales para compatibilidad estricta con BibTeX."""
    if text is None:
        return ""
    if isinstance(text, (list, tuple)):
        text = ", ".join(str(x) for x in text if x)
    else:
        try:
            if pd.isna(text):
                return ""
        except Exception:
            pass
    s = str(text).strip()
    s = s.replace('&', '\\&').replace('%', '\\%').replace('#', '\\#').replace('_', '\\_')
    return s

def generate_bibtex_key(author_str: Any, year: Any, title_str: Any) -> str:
    """Genera una clave BibTeX única y descriptiva (ej. 'Jimenez2024Neural')."""
    first_author = "Author"
    if author_str is not None:
        if isinstance(author_str, (list, tuple)) and len(author_str) > 0:
            first_candidate = author_str[0]
        else:
            first_candidate = str(author_str)
        parts = re.split(r'[,;and]', str(first_candidate), flags=re.IGNORECASE)
        if parts:
            clean_p = re.sub(r'[^a-zA-Z]', '', parts[0].strip())
            if clean_p:
                first_author = clean_p.capitalize()
    
    yr = "XXXX"
    if year is not None:
        try:
            if not pd.isna(year):
                yr = str(year)
        except Exception:
            yr = str(year)
    
    first_word = "Paper"
    if title_str:
        words = [re.sub(r'[^a-zA-Z]', '', w) for w in str(title_str).split() if len(w) > 3]
        if words:
            first_word = words[0].capitalize()
            
    return f"{first_author}{yr}{first_word}"

def format_bibtex_authors(authors_val: Any) -> str:
    """Formatea la lista de autores al formato estándar de BibTeX: 'Apellido, Nombre and Apellido2, Nombre2'."""
    if authors_val is None:
        return "Unknown"
    
    if isinstance(authors_val, (list, tuple)):
        clean_authors = [str(a).strip() for a in authors_val if str(a).strip()]
        return " and ".join(clean_authors) if clean_authors else "Unknown"

    if hasattr(authors_val, '__iter__') and not isinstance(authors_val, (str, bytes)):
        clean_authors = [str(a).strip() for a in authors_val if str(a).strip()]
        return " and ".join(clean_authors) if clean_authors else "Unknown"

    try:
        if pd.isna(authors_val):
            return "Unknown"
    except Exception:
        pass
        
    s = str(authors_val).strip()
    if not s:
        return "Unknown"
    if " and " in s:
        return s
    if ";" in s:
        return " and ".join([a.strip() for a in s.split(";") if a.strip()])
    return s

def export_author_bibtex(df_papers: pd.DataFrame, author_name: str = "") -> str:
    """
    Genera un archivo BibTeX riguroso con todos los campos mínimos de una referencia canónica:
    - author, title, journal, year, volume, number, pages, doi, issn, publisher, url, abstract
    - annote con métricas bibliométricas (FWCI, Citas, OA, Top 10%, ODS, Tópico).
    """
    if df_papers.empty:
        return "% No hay publicaciones para exportar.\n"

    # Intentar enriquecer datos biblio (volume, pages, publisher) desde ClickHouse si hay paper_ids
    biblio_meta = {}
    paper_ids = []
    if "paper_id" in df_papers.columns:
        paper_ids = [p for p in df_papers["paper_id"].dropna().unique() if "openalex.org/W" in str(p)]
    
    if paper_ids:
        try:
            client = ch_client.get_client()
            res = client.query(
                "SELECT id, raw_data FROM works WHERE id IN %(pids)s",
                {"pids": paper_ids[:300]}
            ).result_rows
            for r in res:
                wid, raw_str = r[0], r[1]
                if raw_str:
                    try:
                        raw_j = json.loads(raw_str)
                        bib = raw_j.get("biblio") or {}
                        loc = raw_j.get("primary_location") or {}
                        src = loc.get("source") or {}
                        biblio_meta[wid] = {
                            "volume": bib.get("volume"),
                            "issue": bib.get("issue"),
                            "first_page": bib.get("first_page"),
                            "last_page": bib.get("last_page"),
                            "publisher": src.get("publisher") or src.get("host_organization_name"),
                            "issn": ", ".join(src.get("issn") or []) if isinstance(src.get("issn"), list) else None,
                            "abstract": raw_j.get("abstract") or raw_j.get("abstract_inverted_index")
                        }
                    except Exception:
                        pass
        except Exception as e:
            print(f"[knomap_bridge] Advertencia al enriquecer biblio desde ClickHouse: {e}")

    entries = []
    header = f"""% =========================================================================
% Archivo BibTeX generado por SNII Info TlachIA (SinapsisAI)
% Investigador: {author_name or 'Académico'}
% Fecha de Exportación: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
% Total de Publicaciones: {len(df_papers)}
% =========================================================================\n\n"""
    entries.append(header)

    seen_keys = set()

    for idx, row in df_papers.iterrows():
        title = row.get("Title") or row.get("title") or "Sin Título"
        year = row.get("year") or row.get("Year") or row.get("publication_year")
        authors = row.get("_formatted_authors") or row.get("authors") or row.get("academic_name") or author_name
        journal = row.get("Source") or row.get("journal_name") or row.get("journal") or "Revista Científica"
        doi = row.get("doi") or row.get("DOI") or ""
        clean_doi = str(doi).replace("https://doi.org/", "").strip() if pd.notna(doi) else ""
        pid = row.get("paper_id")

        # Datos enriquecidos
        enriched = biblio_meta.get(pid, {})
        volume = enriched.get("volume")
        issue = enriched.get("issue")
        f_page = enriched.get("first_page")
        l_page = enriched.get("last_page")
        pages = f"{f_page}--{l_page}" if f_page and l_page else (f_page or "")
        publisher = enriched.get("publisher")
        issn = enriched.get("issn")
        abstract = enriched.get("abstract")

        # Métricas analíticas
        cites = row.get("citations") or 0
        fwci = row.get("fwci") or "N/A"
        oa_status = row.get("oa_status") or "No declarado"
        topic = row.get("topic") or ""
        ods = row.get("ODS_Nombre") or row.get("sdg_names") or ""
        top10 = "Sí" if row.get("is_top_10") == 1 else "No"

        # Generar clave única
        base_key = generate_bibtex_key(authors, year, title)
        key = base_key
        counter = 1
        while key in seen_keys:
            key = f"{base_key}_{counter}"
            counter += 1
        seen_keys.add(key)

        annote_parts = [f"Citas: {cites}"]
        if fwci != "N/A": annote_parts.append(f"FWCI: {fwci}")
        if oa_status: annote_parts.append(f"OA: {oa_status}")
        if top10 == "Sí": annote_parts.append("Top10Pct: True")
        if topic: annote_parts.append(f"Tópico: {topic}")
        if ods: annote_parts.append(f"ODS: {ods}")
        annote_str = "; ".join(annote_parts)

        # Construir entrada
        entry_lines = [
            f"@article{{{key},",
            f"  author    = {{{format_bibtex_authors(authors)}}},",
            f"  title     = {{{clean_latex_str(title)}}},",
            f"  journal   = {{{clean_latex_str(journal)}}},",
            f"  year      = {{{year if pd.notna(year) else ''}}},"
        ]

        if volume: entry_lines.append(f"  volume    = {{{clean_latex_str(volume)}}},")
        if issue: entry_lines.append(f"  number    = {{{clean_latex_str(issue)}}},")
        if pages: entry_lines.append(f"  pages     = {{{clean_latex_str(pages)}}},")
        if clean_doi: 
            entry_lines.append(f"  doi       = {{{clean_doi}}},")
            entry_lines.append(f"  url       = {{https://doi.org/{clean_doi}}},")
        if issn: entry_lines.append(f"  issn      = {{{clean_latex_str(issn)}}},")
        if publisher: entry_lines.append(f"  publisher = {{{clean_latex_str(publisher)}}},")
        if abstract and isinstance(abstract, str) and len(abstract) > 20:
            entry_lines.append(f"  abstract  = {{{clean_latex_str(abstract[:1500])}}},")
            
        entry_lines.append(f"  annote    = {{{clean_latex_str(annote_str)}}}")
        entry_lines.append("}\n")

        entries.append("\n".join(entry_lines))

    return "\n".join(entries)

def export_author_json(df_papers: pd.DataFrame, author_name: str = "") -> str:
    """Exporta las obras en formato JSON canónico estandarizado."""
    records = df_papers.to_dict(orient="records")
    clean_records = []
    for r in records:
        clean_r = {}
        for k, v in r.items():
            if v is None:
                clean_r[k] = None
            elif isinstance(v, (list, tuple)):
                clean_r[k] = list(v)
            elif isinstance(v, dict):
                clean_r[k] = dict(v)
            else:
                try:
                    if pd.isna(v):
                        clean_r[k] = None
                    elif isinstance(v, (int, float, str, bool)):
                        clean_r[k] = v
                    else:
                        clean_r[k] = str(v)
                except Exception:
                    clean_r[k] = str(v)
        clean_records.append(clean_r)

    payload = {
        "metadata": {
            "academic_name": author_name,
            "exported_at": datetime.now().isoformat(),
            "total_records": len(clean_records),
            "source": "SNII Info TlachIA (SinapsisAI)"
        },
        "publications": clean_records
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)

def export_author_knomap_bundle(df_papers: pd.DataFrame, author_name: str = "") -> bytes:
    """
    Genera un paquete .knomap (ZIP estructurado) listo para ser abierto en KnoMap.
    Contiene:
    1. corpus.parquet (tabla canónica estandarizada).
    2. author_network.json (red de coautoría).
    3. topics_matrix.parquet (distribución de tópicos).
    4. manifest.json (manifiesto de proyecto con hash SHA256).
    """
    zip_buffer = io.BytesIO()

    # 1. Preparar DataFrame canónico para KnoMap (corpus.parquet)
    cols_map = {
        "paper_id": "id",
        "Title": "title",
        "title": "title",
        "year": "year",
        "Year": "year",
        "Source": "journal",
        "journal_name": "journal",
        "doi": "doi",
        "citations": "citations",
        "fwci": "fwci",
        "oa_status": "oa_status",
        "topic": "topic",
        "authors": "authors",
        "_formatted_authors": "authors"
    }
    df_corpus = df_papers.copy()
    existing_cols = {c: cols_map[c] for c in df_corpus.columns if c in cols_map}
    df_corpus = df_corpus[list(existing_cols.keys())].rename(columns=existing_cols)
    if "authors" not in df_corpus.columns:
        df_corpus["authors"] = author_name
    else:
        df_corpus["authors"] = df_corpus["authors"].apply(format_bibtex_authors)
    if "abstract" not in df_corpus.columns:
        df_corpus["abstract"] = ""

    corpus_buf = io.BytesIO()
    df_corpus.to_parquet(corpus_buf, index=False)
    corpus_bytes = corpus_buf.getvalue()

    # 2. Construir red de coautoría básica ego-centrada (author_network.json)
    nodes = [{"id": author_name or "Ego", "name": author_name or "Ego", "papers_count": len(df_papers), "is_ego": True}]
    edges = []
    seen_coauthors = {}

    for _, row in df_papers.iterrows():
        auts = row.get("authors") or row.get("_formatted_authors") or ""
        if isinstance(auts, str):
            p_coauthors = [a.strip() for a in auts.split("and") if a.strip() and a.strip() != author_name]
        elif isinstance(auts, (list, tuple)):
            p_coauthors = [str(a).strip() for a in auts if str(a).strip() != author_name]
        else:
            p_coauthors = []

        for ca in p_coauthors[:10]: # Limitar coautores por paper
            seen_coauthors[ca] = seen_coauthors.get(ca, 0) + 1

    for ca_name, count in sorted(seen_coauthors.items(), key=lambda x: x[1], reverse=True)[:30]:
        nodes.append({"id": ca_name, "name": ca_name, "papers_count": count, "is_ego": False})
        edges.append({"source": author_name or "Ego", "target": ca_name, "weight": count})

    network_data = {"nodes": nodes, "edges": edges}
    network_bytes = json.dumps(network_data, ensure_ascii=False, indent=2).encode('utf-8')

    # 3. Matriz de Frecuencia de Tópicos (topics_matrix.parquet)
    topic_series = df_papers.get("topic") if "topic" in df_papers.columns else pd.Series(dtype=object)
    if topic_series is not None and not topic_series.empty:
        df_top = topic_series.dropna().value_counts().reset_index()
        df_top.columns = ["topic", "paper_count"]
    else:
        df_top = pd.DataFrame([{"topic": "Ciencia General", "paper_count": len(df_papers)}])
    
    top_buf = io.BytesIO()
    df_top.to_parquet(top_buf, index=False)
    topics_bytes = top_buf.getvalue()

    # 4. Manifiesto del Paquete
    manifest = {
        "project_name": f"KnoMap_{re.sub(r'[^a-zA-Z0-9]', '_', author_name or 'Academic')}",
        "version": "1.0",
        "created_at": datetime.now().isoformat(),
        "academic_name": author_name,
        "total_works": len(df_papers),
        "generator": "SNII Info TlachIA (SinapsisAI) - KnoMap Bridge",
        "files": {
            "corpus.parquet": hashlib.sha256(corpus_bytes).hexdigest(),
            "author_network.json": hashlib.sha256(network_bytes).hexdigest(),
            "topics_matrix.parquet": hashlib.sha256(topics_bytes).hexdigest()
        }
    }
    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')

    # Empaquetar todo en el ZIP .knomap
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("corpus.parquet", corpus_bytes)
        zf.writestr("author_network.json", network_bytes)
        zf.writestr("topics_matrix.parquet", topics_bytes)
        zf.writestr("manifest.json", manifest_bytes)

    return zip_buffer.getvalue()
