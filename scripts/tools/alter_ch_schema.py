import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
from database.clickhouse_db import ch_client

def main():
    ch = ch_client.get_client()
    alters = [
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `raw_data` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `updated_date` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `is_xpac` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `author_names` Array(String)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `institution_rors` Array(String)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `institution_names` Array(String)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `primary_topic_id` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `subfield` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `field` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `domain` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `topic` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `country_code` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `sdg_ids` Array(String)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `awards` Array(String)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `concept_ids` Array(String)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `all_country_codes` Array(String)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `apc_paid_usd` Float64",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `apc_list_usd` Float64",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `counts_by_year` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `is_doaj_indexed` UInt8",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `is_doaj_journal` UInt8",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `is_core_journal` UInt8",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `has_repository_fulltext` UInt8",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `license` String",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `journal_is_in_doaj` UInt8",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `journal_is_core` UInt8",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `any_repository_has_fulltext` UInt8",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `embedding_nomic` Array(Float32)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `embedding_specter` Array(Float32)",
        "ALTER TABLE works_flat ADD COLUMN IF NOT EXISTS `embedding_fastrp` Array(Float32)",
    ]
    
    for query in alters:
        print(f"Ejecutando: {query}")
        try:
            ch.command(query)
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    main()
