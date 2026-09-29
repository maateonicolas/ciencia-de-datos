-- Only repeated physical identity; never deduplicate by timestamps/fares.
select * from {{ ref('silver_quality') }}
where source_occurrence > 1
