-- Defensive dedup does not hide an ingestion integrity error.
select source_record_key from {{ ref('silver_duplicate_rows') }}
