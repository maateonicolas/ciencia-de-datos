select
    sha2(source_month || ':' || source_sha256 || ':' || source_row::varchar, 256) as source_record_key,
    payload, source_file, source_month, source_sha256, source_row, loaded_at
from {{ source('raw', 'yellow_trips') }}
