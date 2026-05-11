import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database.clickhouse_db import ch_client

def main():
    ch = ch_client.get_client()
    
    # 1. Eliminar columnas de embeddings de works_flat (Polite metadata operation)
    for col in ['embedding_nomic', 'embedding_specter', 'embedding_fastrp']:
        try:
            ch.command(f"ALTER TABLE rag.works_flat DROP COLUMN IF EXISTS `{col}`")
            print(f"Dropped {col} from works_flat")
        except Exception as e:
            print(f"Error dropping {col}: {e}")

    # 2. Recrear MV sin los embeddings
    ch.command("DROP TABLE IF EXISTS rag.works_flat_mv")
    
    create_mv_query = """
    CREATE MATERIALIZED VIEW rag.works_flat_mv TO rag.works_flat
    AS SELECT
        id,
        JSONExtractString(raw_data, 'doi') AS doi,
        JSONExtractString(raw_data, 'title') AS title,
        arrayStringConcat(arrayMap(x -> (x.1), arraySort(x -> (x.2), arrayFlatten(arrayMap((k, v) -> arrayMap(p -> (k, p), v), mapKeys(JSONExtract(raw_data, 'abstract_inverted_index', 'Map(String, Array(Int32))')), mapValues(JSONExtract(raw_data, 'abstract_inverted_index', 'Map(String, Array(Int32))')))))), ' ') AS abstract,
        toUInt16(JSONExtractInt(raw_data, 'publication_year')) AS publication_year,
        parseDateTimeBestEffortOrZero(JSONExtractString(raw_data, 'publication_date')) AS publication_date,
        JSONExtractString(raw_data, 'type') AS type,
        JSONExtractString(raw_data, 'language') AS language,
        toUInt32(JSONExtractInt(raw_data, 'cited_by_count')) AS cited_by_count,
        toFloat32(JSONExtractFloat(raw_data, 'fwci')) AS fwci,
        toFloat32(JSONExtractFloat(raw_data, 'citation_normalized_percentile', 'value')) * 100 AS percentile,
        toUInt8(JSONExtractBool(raw_data, 'citation_normalized_percentile', 'is_in_top_10_percent')) AS is_top_10,
        toUInt8(JSONExtractBool(raw_data, 'citation_normalized_percentile', 'is_in_top_1_percent')) AS is_top_1,
        toUInt32(JSONExtractInt(raw_data, 'referenced_works_count')) AS referenced_works_count,
        JSONExtractString(raw_data, 'primary_location', 'source', 'id') AS source_id,
        JSONExtractString(raw_data, 'primary_location', 'source', 'type') AS source_type,
        toUInt8(JSONExtractBool(raw_data, 'open_access', 'is_oa')) AS is_oa,
        JSONExtractString(raw_data, 'open_access', 'oa_status') AS oa_status,
        JSONExtractString(raw_data, 'primary_topic', 'id') AS topic_id,
        JSONExtractString(raw_data, 'primary_topic', 'subfield', 'id') AS subfield_id,
        JSONExtractString(raw_data, 'primary_topic', 'subfield', 'display_name') AS subfield_name,
        JSONExtractString(raw_data, 'primary_topic', 'field', 'display_name') AS field_name,
        JSONExtractString(raw_data, 'primary_topic', 'domain', 'display_name') AS domain_name,
        tupleElement(tupleElement(JSONExtract(raw_data, 'authorships', 'Array(Tuple(author Tuple(id String)))'), 'author'), 'id') AS author_ids,
        arrayFlatten(tupleElement(tupleElement(JSONExtract(raw_data, 'authorships', 'Array(Tuple(institutions Array(Tuple(id String))))'), 'institutions'), 'id')) AS institution_ids,
        arrayFlatten(tupleElement(tupleElement(JSONExtract(raw_data, 'authorships', 'Array(Tuple(institutions Array(Tuple(type String))))'), 'institutions'), 'type')) AS institution_types,
        arrayDistinct(arrayFlatten(tupleElement(JSONExtract(raw_data, 'authorships', 'Array(Tuple(countries Array(String)))'), 'countries'))) AS country_codes,
        JSONExtract(raw_data, 'referenced_works', 'Array(String)') AS referenced_works,
        tupleElement(JSONExtract(raw_data, 'concepts', 'Array(Tuple(display_name String))'), 'display_name') AS concepts,
        JSONExtractString(raw_data, 'ids', 'pmid') AS pmid,
        JSONExtractString(raw_data, 'ids', 'mag') AS mag_id,
        toUInt8(JSONExtractBool(raw_data, 'is_retracted')) AS is_retracted,
        toUInt8(JSONExtractBool(raw_data, 'is_paratext')) AS is_paratext,
        JSONExtractString(raw_data, 'biblio', 'volume') AS volume,
        JSONExtractString(raw_data, 'biblio', 'issue') AS issue,
        JSONExtractString(raw_data, 'biblio', 'first_page') AS first_page,
        JSONExtractString(raw_data, 'biblio', 'last_page') AS last_page,
        tupleElement(JSONExtract(raw_data, 'topics', 'Array(Tuple(id String))'), 'id') AS all_topics,
        tupleElement(JSONExtract(raw_data, 'keywords', 'Array(Tuple(display_name String))'), 'display_name') AS keywords,
        tupleElement(JSONExtract(raw_data, 'mesh', 'Array(Tuple(descriptor_name String))'), 'descriptor_name') AS mesh,
        tupleElement(JSONExtract(raw_data, 'funders', 'Array(Tuple(id String))'), 'id') AS funder_ids,
        tupleElement(JSONExtract(raw_data, 'funders', 'Array(Tuple(display_name String))'), 'display_name') AS funder_names,
        tupleElement(JSONExtract(raw_data, 'sustainable_development_goals', 'Array(Tuple(id String))'), 'id') AS sdgs,
        
        -- NUVAS COLUMNAS (Sin Embeddings) --
        raw_data AS raw_data,
        JSONExtractString(raw_data, 'updated_date') AS updated_date,
        JSONExtractString(raw_data, 'is_xpac') AS is_xpac,
        tupleElement(tupleElement(JSONExtract(raw_data, 'authorships', 'Array(Tuple(author Tuple(display_name String)))'), 'author'), 'display_name') AS author_names,
        arrayFlatten(tupleElement(tupleElement(JSONExtract(raw_data, 'authorships', 'Array(Tuple(institutions Array(Tuple(ror String))))'), 'institutions'), 'ror')) AS institution_rors,
        arrayFlatten(tupleElement(tupleElement(JSONExtract(raw_data, 'authorships', 'Array(Tuple(institutions Array(Tuple(display_name String))))'), 'institutions'), 'display_name')) AS institution_names,
        JSONExtractString(raw_data, 'primary_topic', 'id') AS primary_topic_id,
        JSONExtractString(raw_data, 'primary_topic', 'subfield', 'display_name') AS subfield,
        JSONExtractString(raw_data, 'primary_topic', 'field', 'display_name') AS field,
        JSONExtractString(raw_data, 'primary_topic', 'domain', 'display_name') AS domain,
        JSONExtractString(raw_data, 'primary_topic', 'display_name') AS topic,
        '' AS country_code,
        tupleElement(JSONExtract(raw_data, 'sustainable_development_goals', 'Array(Tuple(id String))'), 'id') AS sdg_ids,
        tupleElement(JSONExtract(raw_data, 'grants', 'Array(Tuple(award_id String))'), 'award_id') AS awards,
        tupleElement(JSONExtract(raw_data, 'concepts', 'Array(Tuple(id String))'), 'id') AS concept_ids,
        arrayDistinct(arrayFlatten(tupleElement(JSONExtract(raw_data, 'authorships', 'Array(Tuple(countries Array(String)))'), 'countries'))) AS all_country_codes,
        toFloat64(JSONExtractFloat(raw_data, 'apc_paid', 'value_usd')) AS apc_paid_usd,
        toFloat64(JSONExtractFloat(raw_data, 'apc_list', 'value_usd')) AS apc_list_usd,
        JSONExtractString(raw_data, 'counts_by_year') AS counts_by_year,
        toUInt8(JSONExtractBool(raw_data, 'primary_location', 'source', 'is_in_doaj')) AS is_doaj_indexed,
        toUInt8(JSONExtractBool(raw_data, 'primary_location', 'source', 'is_core_journal')) AS is_core_journal,
        toUInt8(JSONExtractBool(raw_data, 'primary_location', 'source', 'is_in_doaj')) AS is_doaj_journal,
        toUInt8(JSONExtractBool(raw_data, 'open_access', 'any_repository_has_fulltext')) AS has_repository_fulltext,
        JSONExtractString(raw_data, 'primary_location', 'license') AS license,
        toUInt8(JSONExtractBool(raw_data, 'primary_location', 'source', 'is_in_doaj')) AS journal_is_in_doaj,
        toUInt8(JSONExtractBool(raw_data, 'primary_location', 'source', 'is_core')) AS journal_is_core,
        toUInt8(JSONExtractBool(raw_data, 'open_access', 'any_repository_has_fulltext')) AS any_repository_has_fulltext
    FROM rag.works
    """
    ch.command(create_mv_query)
    print("Created new MV without embeddings.")

if __name__ == '__main__':
    main()
