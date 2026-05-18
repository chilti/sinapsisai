# CLICKHOUSE SCHEMAS

## Table: _processed_files
| Column | Type |
|--------|------|
| entity | String |
| file_name | String |
| processed_at | DateTime |


## Table: academics_all
| Column | Type |
|--------|------|
| id | String |
| name | String |
| institution | String |
| dependency | String |
| subdependency | String |
| snii_level | String |
| orcid | String |
| paper_count | UInt32 |
| citation_count | UInt32 |
| embedding_nomic | Array(Float32) |
| embedding_specter | Array(Float32) |
| embedding_fastrp | Array(Float32) |


## Table: authors
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |
| orcid | String |
| works_count | Int64 |
| cited_by_count | Int64 |
| updated_date | String |
| last_known_institution_name | String |
| ids | String |


## Table: authors_seed_mexico
| Column | Type |
|--------|------|
| id | String |
| display_name | String |
| orcid | String |
| ids | String |
| raw_data | String |


## Table: awards
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: concepts
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |
| level | Int32 |
| works_count | Int64 |
| cited_by_count | Int64 |


## Table: continents
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: countries
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: domains
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: embeddings_cache
| Column | Type |
|--------|------|
| id | String |
| subfield_name | LowCardinality(String) |
| publication_year | UInt16 |
| embedding_specter2 | Array(Float32) |
| embedding_scilbert | Array(Float32) |
| embedding_fastrp_cit | Array(Float32) |
| embedding_fastrp_het | Array(Float32) |
| embedding_umap_30d | Array(Float32) |
| specter2_at | Nullable(DateTime) |
| scilbert_at | Nullable(DateTime) |
| fastrp_cit_at | Nullable(DateTime) |
| fastrp_het_at | Nullable(DateTime) |
| umap_30d_at | Nullable(DateTime) |
| updated_at | DateTime |


## Table: fields
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: funders
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |
| ror | String |


## Table: institution-types
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: institutions
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |
| ror | String |
| type | String |
| works_count | Int64 |
| cited_by_count | Int64 |
| updated_date | String |
| country_code | String |


## Table: institutions_seed_mexico
| Column | Type |
|--------|------|
| id | String |
| display_name | String |
| ror | String |
| type | String |
| country_code | String |
| city | String |
| state | String |
| acronyms | Array(String) |
| parents | Array(Tuple(
    id String,
    ror String,
    display_name String,
    country_code String,
    type String,
    relationship String)) |
| parent_id | String |
| parent_name | String |
| raw_data | String |


## Table: keywords
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |


## Table: languages
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |


## Table: licenses
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |


## Table: paper_author_map
| Column | Type |
|--------|------|
| paper_id | String |
| academic_name | String |
| cvu | String |
| orcid | String |
| openalex_id | String |
| institution | String |
| institution_ror | String |
| dependency | String |
| dependency_id | String |
| subdependency | String |
| subdependency_id | String |
| paper_title | String |
| paper_year | UInt16 |
| citations | UInt32 |
| is_wos | UInt8 |
| is_scopus | UInt8 |
| is_pubmed | UInt8 |
| is_openalex | UInt8 |
| is_doaj | UInt8 |
| is_semantic_scholar | UInt8 |
| is_dimensions | UInt8 |
| is_lens | UInt8 |
| is_snii | UInt8 |
| ODS | Array(String) |
| source | String |
| audit_verdict | String |


## Table: paper_author_map_meta
| Column | Type |
|--------|------|
| sync_ts | DateTime |
| mode | String |
| rows_synced | UInt64 |
| ok | UInt8 |


## Table: paper_entity_map
| Column | Type |
|--------|------|
| paper_id | String |
| institution | String |
| institution_ror | String |
| dependency | String |
| dependency_id | String |
| subdependency | String |
| subdependency_id | String |
| paper_title | String |
| paper_year | UInt16 |
| citations | UInt32 |
| is_wos | UInt8 |
| is_scopus | UInt8 |
| is_openalex | UInt8 |
| is_dimensions | UInt8 |
| is_semantic_scholar | UInt8 |
| is_pubmed | UInt8 |
| is_doaj | UInt8 |
| is_lens | UInt8 |
| source | String |


## Table: publishers
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |
| ror | String |


## Table: sdgs
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |


## Table: source-types
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: sources
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |
| issn_l | String |
| type | String |
| works_count | Int64 |
| cited_by_count | Int64 |
| updated_date | String |
| country_code | String |


## Table: subfields
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: summing_subfield_inst_metrics
| Column | Type |
|--------|------|
| subfield | String |
| year | UInt16 |
| institution_id | String |
| topic | String |
| source_id | String |
| doc_count | UInt64 |
| fwci_sum | Float64 |
| percentile_sum | Float64 |
| top_1_sum | UInt64 |
| top_10_sum | UInt64 |
| top_25_sum | UInt64 |
| citations_sum | UInt64 |
| intl_collab_count | UInt64 |
| sdg_count | UInt64 |
| award_count | UInt64 |
| review_count | UInt64 |
| gold_count | UInt64 |
| diamond_count | UInt64 |
| green_count | UInt64 |
| hybrid_count | UInt64 |
| bronze_count | UInt64 |
| closed_count | UInt64 |
| lang_en | UInt64 |
| lang_es | UInt64 |
| lang_pt | UInt64 |


## Table: summing_subfield_metrics
| Column | Type |
|--------|------|
| subfield | String |
| year | UInt16 |
| country_code | String |
| source_id | String |
| topic | String |
| doc_count | UInt64 |
| fwci_sum | Float64 |
| percentile_sum | Float64 |
| top_10_sum | UInt64 |
| top_1_sum | UInt64 |
| gold_count | UInt64 |
| diamond_count | UInt64 |
| green_count | UInt64 |
| hybrid_count | UInt64 |
| bronze_count | UInt64 |
| closed_count | UInt64 |
| lang_en | UInt64 |
| lang_es | UInt64 |
| lang_pt | UInt64 |


## Table: tmp_academic_apc
| Column | Type |
|--------|------|
| id | String |
| apc_paid | Float64 |
| apc_list | Float64 |


## Table: tmp_apc_2006_4
| Column | Type |
|--------|------|
| id | String |
| apc_paid | Float64 |
| apc_list | Float64 |


## Table: tmp_work_embs
| Column | Type |
|--------|------|
| id | String |
| specter | Array(Float32) |
| fastrp | Array(Float32) |


## Table: topics
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| display_name | String |
| level | Int32 |
| works_count | Int64 |
| cited_by_count | Int64 |


## Table: work-types
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |


## Table: works
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| doi | String |
| title | String |
| publication_year | Int32 |
| cited_by_count | Int64 |
| is_oa | String |
| type | String |
| updated_date | String |
| is_xpac | String |
| source_id | String |
| author_names | Array(String) |
| institution_rors | Array(String) |
| institution_names | Array(String) |
| primary_topic_id | String |
| institution_ids | Array(String) |
| subfield | String |
| field | String |
| domain | String |
| topic | String |
| language | String |
| oa_status | String |
| fwci | Float32 |
| percentile | Float32 |
| is_top_10 | UInt8 |
| is_top_1 | UInt8 |
| country_code | String |
| source_type | String |
| sdg_ids | Array(String) |
| awards | Array(String) |
| concept_ids | Array(String) |
| all_country_codes | Array(String) |
| openalex_institution_ids | Array(String) |
| author_ids | Array(String) |
| topic_ids | Array(String) |
| primary_subfield_id | String |
| primary_field_id | String |
| primary_domain_id | String |


## Table: works_academic_all

Esta tabla contiene los articulos de los académicos mexicanos. Se creó para que los cálculos de la smétricas no utilicen works_flat (que contiene la producción mundial). works_academic_allse diferencia de works_seed_mexico en que puede tener articulos con afiliaciones extranjeras.

| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| doi | String |
| title | String |
| publication_year | Int32 |
| cited_by_count | Int64 |
| is_oa | String |
| type | String |
| updated_date | String |
| is_xpac | String |
| source_id | String |
| author_names | Array(String) |
| institution_rors | Array(String) |
| institution_names | Array(String) |
| primary_topic_id | String |
| institution_ids | Array(String) |
| subfield | String |
| field | String |
| domain | String |
| topic | String |
| language | String |
| oa_status | String |
| fwci | Float32 |
| percentile | Float32 |
| is_top_10 | UInt8 |
| is_top_1 | UInt8 |
| country_code | String |
| source_type | String |
| sdg_ids | Array(String) |
| awards | Array(String) |
| concept_ids | Array(String) |
| all_country_codes | Array(String) |
| apc_paid_usd | Float64 |
| apc_list_usd | Float64 |
| counts_by_year | String |
| is_doaj_indexed | UInt8 |
| is_doaj_journal | UInt8 |
| is_core_journal | UInt8 |
| is_retracted | UInt8 |
| has_repository_fulltext | UInt8 |
| license | String |
| referenced_works_count | UInt32 |
| keywords | Array(String) |
| sdgs | Array(String) |
| journal_is_in_doaj | UInt8 |
| journal_is_core | UInt8 |
| any_repository_has_fulltext | UInt8 |
| embedding_nomic | Array(Float32) |
| embedding_specter | Array(Float32) |
| embedding_fastrp | Array(Float32) |


## Table: works_flat
| Column | Type |
|--------|------|
| id | String |
| doi | String |
| title | String |
| abstract | String |
| publication_year | UInt16 |
| publication_date | Date |
| type | LowCardinality(String) |
| language | LowCardinality(String) |
| cited_by_count | UInt32 |
| fwci | Float32 |
| percentile | Float32 |
| is_top_10 | UInt8 |
| is_top_1 | UInt8 |
| referenced_works_count | UInt32 |
| source_id | LowCardinality(String) |
| source_type | LowCardinality(String) |
| is_oa | UInt8 |
| oa_status | LowCardinality(String) |
| topic_id | LowCardinality(String) |
| subfield_id | LowCardinality(String) |
| subfield_name | LowCardinality(String) |
| field_name | LowCardinality(String) |
| domain_name | LowCardinality(String) |
| author_ids | Array(String) |
| institution_ids | Array(String) |
| institution_types | Array(LowCardinality(String)) |
| country_codes | Array(LowCardinality(String)) |
| referenced_works | Array(String) |
| concepts | Array(LowCardinality(String)) |
| pmid | String |
| mag_id | String |
| is_retracted | UInt8 |
| is_paratext | UInt8 |
| volume | String |
| issue | String |
| first_page | String |
| last_page | String |
| all_topics | Array(LowCardinality(String)) |
| keywords | Array(String) |
| mesh | Array(String) |
| funder_ids | Array(String) |
| funder_names | Array(String) |
| sdgs | Array(LowCardinality(String)) |
| raw_data | String |
| updated_date | String |
| is_xpac | String |
| author_names | Array(String) |
| institution_rors | Array(String) |
| institution_names | Array(String) |
| primary_topic_id | String |
| subfield | String |
| field | String |
| domain | String |
| topic | String |
| country_code | String |
| sdg_ids | Array(String) |
| awards | Array(String) |
| concept_ids | Array(String) |
| all_country_codes | Array(String) |
| apc_paid_usd | Float64 |
| apc_list_usd | Float64 |
| counts_by_year | String |
| is_doaj_indexed | UInt8 |
| is_doaj_journal | UInt8 |
| is_core_journal | UInt8 |
| has_repository_fulltext | UInt8 |
| license | String |
| journal_is_in_doaj | UInt8 |
| journal_is_core | UInt8 |
| any_repository_has_fulltext | UInt8 |


## Table: works_flat_mv
| Column | Type |
|--------|------|
| id | String |
| doi | String |
| title | String |
| abstract | String |
| publication_year | UInt16 |
| publication_date | DateTime |
| type | String |
| language | String |
| cited_by_count | UInt32 |
| fwci | Float32 |
| percentile | Float64 |
| is_top_10 | UInt8 |
| is_top_1 | UInt8 |
| referenced_works_count | UInt32 |
| source_id | String |
| source_type | String |
| is_oa | UInt8 |
| oa_status | String |
| topic_id | String |
| subfield_id | String |
| subfield_name | String |
| field_name | String |
| domain_name | String |
| author_ids | Array(String) |
| institution_ids | Array(String) |
| institution_types | Array(String) |
| country_codes | Array(String) |
| referenced_works | Array(String) |
| concepts | Array(String) |
| pmid | String |
| mag_id | String |
| is_retracted | UInt8 |
| is_paratext | UInt8 |
| volume | String |
| issue | String |
| first_page | String |
| last_page | String |
| all_topics | Array(String) |
| keywords | Array(String) |
| mesh | Array(String) |
| funder_ids | Array(String) |
| funder_names | Array(String) |
| sdgs | Array(String) |
| raw_data | String |
| updated_date | String |
| is_xpac | String |
| author_names | Array(String) |
| institution_rors | Array(String) |
| institution_names | Array(String) |
| primary_topic_id | String |
| subfield | String |
| field | String |
| domain | String |
| topic | String |
| country_code | String |
| sdg_ids | Array(String) |
| awards | Array(String) |
| concept_ids | Array(String) |
| all_country_codes | Array(String) |
| apc_paid_usd | Float64 |
| apc_list_usd | Float64 |
| counts_by_year | String |
| is_doaj_indexed | UInt8 |
| is_core_journal | UInt8 |
| is_doaj_journal | UInt8 |
| has_repository_fulltext | UInt8 |
| license | String |
| journal_is_in_doaj | UInt8 |
| journal_is_core | UInt8 |
| any_repository_has_fulltext | UInt8 |


## Table: works_seed_mexico
| Column | Type |
|--------|------|
| id | String |
| raw_data | String |
| doi | String |
| title | String |
| publication_year | Int32 |
| cited_by_count | Int64 |
| is_oa | String |
| type | String |
| updated_date | String |
| is_xpac | String |
| source_id | String |
| author_names | Array(String) |
| institution_rors | Array(String) |
| institution_names | Array(String) |
| primary_topic_id | String |
| institution_ids | Array(String) |
| subfield | String |
| field | String |
| domain | String |
| topic | String |
| language | String |
| oa_status | String |
| fwci | Float32 |
| percentile | Float32 |
| is_top_10 | UInt8 |
| is_top_1 | UInt8 |
| country_code | String |
| source_type | String |
| sdg_ids | Array(String) |
| awards | Array(String) |
| concept_ids | Array(String) |
| all_country_codes | Array(String) |
| apc_paid_usd | Float64 |
| apc_list_usd | Float64 |
| counts_by_year | String |
| is_doaj_indexed | UInt8 |
| is_doaj_journal | UInt8 |
| is_core_journal | UInt8 |
| is_retracted | UInt8 |
| has_repository_fulltext | UInt8 |
| license | String |
| referenced_works_count | UInt32 |
| keywords | Array(String) |
| sdgs | Array(String) |
| journal_is_in_doaj | UInt8 |
| journal_is_core | UInt8 |
| any_repository_has_fulltext | UInt8 |


# NEO4J SCHEMAS

## Node Labels and Properties
### `Paper`
**Properties:** citations, doi, fwci, id, openalex_id, sources, title, year

### `Author`
**Properties:** cvu, fullname, id, is_snii, orcid, scopus_id

### `Institution`
**Properties:** name

### `Concept`
**Properties:** 

### `Academic`
**Properties:** 

### `Topic`
**Properties:** id, name

### `SDG`
**Properties:** name

### `Funder`
**Properties:** 

### `Award`
**Properties:** 

### `SNII`
**Properties:** cvu, fullname, id, is_snii, orcid, scopus_id

### `Subdependency`
**Properties:** id, name

### `Dependency`
**Properties:** id, name

### `User`
**Properties:** 

### `Person`
**Properties:** cvu, fullname, id, is_snii, orcid, scopus_id

### `KnowledgeArea`
**Properties:** name

### `Discipline`
**Properties:** 

### `Subdiscipline`
**Properties:** 

### `Specialty`
**Properties:** 

### `TopicSubfield`
**Properties:** id, name

### `TopicField`
**Properties:** id, name

### `TopicDomain`
**Properties:** name

## Relationship Types and Hierarchies
### `[:AFFILIATED_TO]`
- (Author, SNII, Person) -> (:AFFILIATED_TO) -> (Subdependency)
- (Author, SNII, Person) -> (:AFFILIATED_TO) -> (Dependency)


### `[:HAS_TOPIC]`
- (Paper) -> (:HAS_TOPIC) -> (Topic)


### `[:PART_OF]`
- (Topic) -> (:PART_OF) -> (TopicSubfield)


### `[:SPECIALIZED_IN]`
- (Author, SNII, Person) -> (:SPECIALIZED_IN) -> (KnowledgeArea)


### `[:CONTRIBUTES_TO]`
- (Paper) -> (:CONTRIBUTES_TO) -> (SDG)


### `[:AUTHOR_OF]`
- (Author, SNII, Person) -> (:AUTHOR_OF) -> (Paper)


### `[:CREDITED_TO]`
- (Paper) -> (:CREDITED_TO) -> (Subdependency)
- (Paper) -> (:CREDITED_TO) -> (Dependency)


