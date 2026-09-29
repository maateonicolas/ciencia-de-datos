select * from {{ ref('data_coverage') }}
where rows_bronze != rows_silver + rows_rejected + rows_duplicate
   or rows_silver != rows_gold or load_status = 'MISMATCH'
