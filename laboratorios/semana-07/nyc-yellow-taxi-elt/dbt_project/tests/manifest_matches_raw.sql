with physical as (
 select source_month, source_sha256, count(*) as n,
        count(distinct source_row) as distinct_rows
 from {{ source('raw', 'yellow_trips') }} group by 1,2
)
select coalesce(p.source_month, m.source_month) as source_month
from physical p full outer join {{ source('raw', 'load_manifest') }} m
on p.source_month = m.source_month and p.source_sha256 = m.sha256
where p.source_month is null or m.source_month is null
   or p.n != m.row_count or p.n != p.distinct_rows or m.row_count <= 0
