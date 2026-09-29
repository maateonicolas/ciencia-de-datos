select * from {{ ref('silver_quality') }}
where source_occurrence = 1 and not is_valid
