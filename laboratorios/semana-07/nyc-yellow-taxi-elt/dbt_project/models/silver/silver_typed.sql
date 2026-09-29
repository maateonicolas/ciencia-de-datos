select
    source_record_key, source_file, source_month, source_sha256, source_row, loaded_at,
    payload,
    {{ integer_value('payload:VendorID') }} as vendor_id,
    try_to_timestamp_ntz(nullif(trim(payload:tpep_pickup_datetime::varchar), '')) as pickup_at,
    try_to_timestamp_ntz(nullif(trim(payload:tpep_dropoff_datetime::varchar), '')) as dropoff_at,
    {{ integer_value('payload:passenger_count') }} as source_passenger_count,
    case when {{ integer_value('payload:passenger_count') }} >= 0
         then {{ integer_value('payload:passenger_count') }} end as passenger_count,
    try_to_decimal(payload:trip_distance::varchar, 18, 4) as trip_distance_miles,
    {{ integer_value('payload:RatecodeID') }} as rate_code_id,
    case when upper(trim(payload:store_and_fwd_flag::varchar)) in ('Y', 'N')
         then upper(trim(payload:store_and_fwd_flag::varchar)) end as store_and_forward_flag,
    {{ integer_value('payload:PULocationID') }} as pickup_location_id,
    {{ integer_value('payload:DOLocationID') }} as dropoff_location_id,
    {{ integer_value('payload:payment_type') }} as payment_type,
    try_to_decimal(payload:fare_amount::varchar, 18, 4) as fare_amount,
    try_to_decimal(payload:extra::varchar, 18, 4) as extra,
    try_to_decimal(payload:mta_tax::varchar, 18, 4) as mta_tax,
    try_to_decimal(payload:tip_amount::varchar, 18, 4) as tip_amount,
    try_to_decimal(payload:tolls_amount::varchar, 18, 4) as tolls_amount,
    try_to_decimal(payload:improvement_surcharge::varchar, 18, 4) as improvement_surcharge,
    try_to_decimal(payload:total_amount::varchar, 18, 4) as total_amount,
    try_to_decimal(payload:congestion_surcharge::varchar, 18, 4) as congestion_surcharge,
    try_to_decimal(coalesce(payload:Airport_fee, payload:airport_fee)::varchar, 18, 4) as airport_fee,
    try_to_decimal(payload:cbd_congestion_fee::varchar, 18, 4) as cbd_congestion_fee
from {{ ref('bronze_trips') }}
