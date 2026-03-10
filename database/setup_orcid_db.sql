-- setup_orcid_db.sql
-- Definición de la tabla para el dump masivo de ORCID

CREATE TABLE IF NOT EXISTS orcid_records (
    orcid String,
    given_names String,
    family_name String,
    credit_name String,
    emails Array(String),
    last_affiliation String,
    last_affiliation_city String,
    last_affiliation_country String,
    source_id String,
    last_modified DateTime DEFAULT now()
) ENGINE = MergeTree()
ORDER BY (family_name, orcid)
COMMENT 'Tabla para almacenar el dump público de ORCID 2024/2025';

-- Índice experimental para búsqueda rápida de nombres
-- (Opcional, se puede añadir después si la tabla es lenta)
-- ALTER TABLE orcid_records ADD INDEX idx_names (given_names, family_name) TYPE minmax GRANULARITY 8;
