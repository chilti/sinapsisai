import csv
import re
from typing import List, Dict, Any


class ScopusCSVParser:
    """
    Parsea archivos CSV exportados desde Scopus (opción "CSV Export" con
    todos los campos disponibles o selección personalizada).

    Columnas estándar del CSV de Scopus (pueden variar según la selección):
        Authors, Author(s) ID, Title, Year, Source title, Volume, Issue,
        Art. No., Page start, Page end, Page count, Cited by, DOI, Link,
        Affiliations, Authors with affiliations, Abstract, Author Keywords,
        Index Keywords, Editors, Publisher, ISSN, ISBN, CODEN,
        PubMed ID, Language of Original Document, Abbreviated Source Title,
        Document Type, Publication Stage, Open Access, EID, Source

    El parser normaliza los nombres de columna y los mapea al esquema interno
    compartido por WoSParser y BibParser.
    """

    # Mapeo de columnas Scopus → nombres internos
    SCOPUS_FIELDS_MAP = {
        "title":                          "title",
        "authors":                        "authors_raw",
        "author(s) id":                   "scopus_author_ids",
        "year":                           "year",
        "source title":                   "journal",
        "volume":                         "volume",
        "issue":                          "issue",
        "art. no.":                       "article_number",
        "page start":                     "page_start",
        "page end":                       "page_end",
        "page count":                     "page_count",
        "cited by":                       "citations",
        "doi":                            "doi",
        "link":                           "scopus_url",
        "affiliations":                   "affiliations",
        "authors with affiliations":      "authors_with_affiliations",
        "abstract":                       "abstract",
        "author keywords":                "author_keywords",
        "index keywords":                 "index_keywords",
        "editors":                        "editors",
        "publisher":                      "publisher",
        "issn":                           "issn",
        "isbn":                           "isbn",
        "coden":                          "coden",
        "pubmed id":                      "pubmed_id",
        "language of original document":  "language",
        "abbreviated source title":       "journal_abbrev",
        "document type":                  "document_type",
        "publication stage":              "publication_stage",
        "open access":                    "open_access",
        "eid":                            "eid",
        "source":                         "source_db",
        # Alias adicionales que Scopus puede incluir en algunas versiones
        "correspondence address":         "correspondence_address",
        "funding details":                "funding_details",
        "funding texts":                  "funding_texts",
        "references":                     "references",
        "chemicals/cas":                  "chemicals_cas",
        "tradenames":                     "tradenames",
        "manufacturers":                  "manufacturers",
        "conference name":                "conference_name",
        "conference date":                "conference_date",
        "conference location":            "conference_location",
        "conference code":                "conference_code",
    }

    @staticmethod
    def parse_file(file_path: str) -> List[Dict[str, Any]]:
        """
        Lee un CSV de Scopus y devuelve una lista de registros normalizados.
        Detecta automáticamente el encoding (UTF-8-BOM es habitual en Scopus).
        """
        records = []
        # Scopus suele exportar con BOM (utf-8-sig) para compatibilidad con Excel
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                with open(file_path, "r", encoding=encoding, newline="") as fh:
                    reader = csv.DictReader(fh)
                    for raw_row in reader:
                        record = ScopusCSVParser._process_row(raw_row)
                        if record:
                            records.append(record)
                break  # Si llegó aquí, la lectura fue exitosa
            except UnicodeDecodeError:
                continue

        return records

    @staticmethod
    def _normalize_header(header: str) -> str:
        """Convierte un encabezado de Scopus a minúsculas sin espacios extras."""
        return header.strip().lower()

    @staticmethod
    def _process_row(raw_row: Dict[str, str]) -> Dict[str, Any]:
        """
        Transforma una fila cruda del CSV de Scopus en el esquema interno.
        Retorna None si la fila no tiene título ni DOI (fila vacía o de basura).
        """
        # Normalizar claves
        row = {ScopusCSVParser._normalize_header(k): (v or "").strip()
               for k, v in raw_row.items()}

        # --- Campos esenciales ---
        title = row.get("title", "")
        doi_raw = row.get("doi", "")

        # Limpiar DOI si viene como URL completa
        doi = doi_raw.strip()
        if "doi.org/" in doi:
            doi = doi.split("doi.org/")[-1].strip()

        if not title and not doi:
            return None  # Fila vacía

        # --- Año ---
        year_str = row.get("year", "0").strip()
        try:
            year = int(year_str)
        except ValueError:
            year = 0

        # --- Citaciones ---
        cited_str = row.get("cited by", "0").strip()
        try:
            citations = int(cited_str)
        except ValueError:
            citations = 0

        # --- Autores ---
        authors_raw = row.get("authors", "")
        authors = ScopusCSVParser._parse_authors(authors_raw)

        # --- Keywords → conceptos ---
        auth_kw = row.get("author keywords", "")
        idx_kw  = row.get("index keywords", "")
        concepts = ScopusCSVParser._parse_keywords(auth_kw, idx_kw)

        # --- Identificadores ---
        eid = row.get("eid", "")
        # EID tiene la forma "2-s2.0-XXXXXXXXXX" y es el ID de Scopus
        scopus_id = eid if eid else ""

        # --- paper_id ---
        paper_id = doi if doi else (eid if eid else title[:80])

        # --- Open Access ---
        oa_str = row.get("open access", "").lower()
        is_oa = oa_str in ("true", "yes", "1", "open access", "gold", "green",
                           "hybrid", "bronze", "diamond")

        # --- raw_metadata: todos los campos mapeados ---
        raw_metadata = {}
        for col_key, val in row.items():
            field_name = ScopusCSVParser.SCOPUS_FIELDS_MAP.get(col_key, col_key)
            raw_metadata[field_name] = val

        processed = {
            "paper_id":    paper_id,
            "title":       title,
            "abstract":    row.get("abstract", ""),
            "year":        year,
            "doi":         doi,
            "scopus_id":   scopus_id,
            "wos_id":      "",          # Scopus CSV no incluye UT de WoS
            "journal":     row.get("source title", ""),
            "volume":      row.get("volume", ""),
            "issue":       row.get("issue", ""),
            "language":    row.get("language of original document", ""),
            "document_type": row.get("document type", ""),
            "publisher":   row.get("publisher", ""),
            "issn":        row.get("issn", ""),
            "citations":   citations,
            "is_oa":       is_oa,
            "authors":     authors,
            "concepts":    concepts,
            "institutions": ScopusCSVParser._parse_affiliations(
                               row.get("affiliations", "")),
            "raw_metadata": raw_metadata,
        }

        return processed

    # ------------------------------------------------------------------
    # Helpers de parseo
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_authors(authors_str: str) -> List[Dict[str, str]]:
        """
        Scopus CSV separa los autores con '; '.
        Cada autor puede aparecer como 'Apellido, Nombre I.' o 'Apellido I.N.'
        """
        if not authors_str:
            return []
        parts = [a.strip() for a in authors_str.split(";") if a.strip()]
        return [{"name": p} for p in parts]

    @staticmethod
    def _parse_keywords(author_kw: str, index_kw: str) -> List[Dict[str, str]]:
        """Combina Author Keywords e Index Keywords en una lista de conceptos."""
        combined = []
        for kw_str in (author_kw, index_kw):
            if kw_str:
                combined.extend([k.strip() for k in kw_str.split(";") if k.strip()])
        # Eliminar duplicados manteniendo orden
        seen: set = set()
        unique = []
        for k in combined:
            k_lower = k.lower()
            if k_lower not in seen:
                seen.add(k_lower)
                unique.append(k)
        return [{"name": k} for k in unique]

    @staticmethod
    def _parse_affiliations(affiliations_str: str) -> List[Dict[str, str]]:
        """
        Las afiliaciones en el CSV de Scopus aparecen como texto libre separado
        por '; ' o por nueva línea.  Extrae el nombre de institución de forma
        heurística (primer elemento antes de la primera coma de cada segmento).
        """
        if not affiliations_str:
            return []
        # Separar por punto y coma o por línea nueva
        segments = re.split(r";|\n", affiliations_str)
        seen: set = set()
        institutions = []
        for seg in segments:
            seg = seg.strip()
            if not seg:
                continue
            # El nombre de la institución suele ser el primer token antes de la coma
            inst_name = seg.split(",")[0].strip()
            # Eliminar el bloque de autor entre corchetes si existe: "[Autor] Inst"
            inst_name = re.sub(r"^\[.*?\]\s*", "", inst_name).strip()
            if inst_name and inst_name.lower() not in seen:
                seen.add(inst_name.lower())
                institutions.append({"name": inst_name})
        return institutions


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        records = ScopusCSVParser.parse_file(sys.argv[1])
        print(f"Registros parseados: {len(records)}")
        if records:
            r = records[0]
            print(f"  Título  : {r['title']}")
            print(f"  DOI     : {r['doi']}")
            print(f"  Año     : {r['year']}")
            print(f"  Citas   : {r['citations']}")
            print(f"  Autores : {[a['name'] for a in r['authors'][:3]]}")
    else:
        print("Uso: python scopus_csv_parser.py <ruta_al_csv>")
