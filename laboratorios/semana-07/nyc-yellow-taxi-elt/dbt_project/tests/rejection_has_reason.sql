select source_record_key from {{ ref('silver_rejected') }}
where array_size(rejection_reasons) = 0
