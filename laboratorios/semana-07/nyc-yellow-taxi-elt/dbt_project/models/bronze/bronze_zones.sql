select location_id, borough, zone, service_zone, source_sha256, loaded_at
from {{ source('raw', 'taxi_zones') }}
