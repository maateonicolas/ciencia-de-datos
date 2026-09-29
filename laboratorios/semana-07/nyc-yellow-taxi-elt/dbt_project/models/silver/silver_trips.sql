-- Preserve distinct physical rows even if all business attributes are equal.
select * from {{ ref('silver_quality') }}
where source_occurrence = 1 and is_valid
