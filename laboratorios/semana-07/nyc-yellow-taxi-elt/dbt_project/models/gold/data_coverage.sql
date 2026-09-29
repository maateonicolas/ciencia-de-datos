with bronze as (
    select source_month, count(*) as rows_bronze from {{ ref('bronze_trips') }} group by 1
), silver as (
    select source_month, count(*) as rows_silver from {{ ref('silver_trips') }} group by 1
), rejected as (
    select source_month, count(*) as rows_rejected from {{ ref('silver_rejected') }} group by 1
), duplicates as (
    select source_month, count(*) as rows_duplicate from {{ ref('silver_duplicate_rows') }} group by 1
), gold as (
    select source_month, count(*) as rows_gold from {{ ref('fact_trips') }} group by 1
)
select e.source_month, m.sha256, m.row_count as manifest_rows,
       coalesce(b.rows_bronze, 0) as rows_bronze,
       coalesce(s.rows_silver, 0) as rows_silver,
       coalesce(r.rows_rejected, 0) as rows_rejected,
       coalesce(d.rows_duplicate, 0) as rows_duplicate,
       coalesce(g.rows_gold, 0) as rows_gold,
       case when m.source_month is null then 'NOT_LOADED'
            when m.row_count = b.rows_bronze and m.row_count > 0 then 'LOADED'
            else 'MISMATCH' end as load_status
from {{ ref('expected_months') }} e
left join {{ source('raw', 'load_manifest') }} m on e.source_month = m.source_month
left join bronze b on e.source_month = b.source_month
left join silver s on e.source_month = s.source_month
left join rejected r on e.source_month = r.source_month
left join duplicates d on e.source_month = d.source_month
left join gold g on e.source_month = g.source_month
