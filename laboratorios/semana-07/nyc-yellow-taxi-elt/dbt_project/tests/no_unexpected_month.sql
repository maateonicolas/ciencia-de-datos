select distinct b.source_month
from {{ ref('bronze_trips') }} b
left join {{ ref('expected_months') }} e on b.source_month = e.source_month
where e.source_month is null
