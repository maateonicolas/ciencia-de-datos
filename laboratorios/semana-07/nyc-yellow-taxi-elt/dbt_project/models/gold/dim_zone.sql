select location_id as zone_key, borough, zone, service_zone, source_sha256
from {{ ref('bronze_zones') }}
union all
select -1, 'Unknown', 'Unknown', 'Unknown', 'not_applicable'
