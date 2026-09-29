{{ config(materialized='table') }}
select *,
    datediff('second', pickup_at, dropoff_at) as duration_seconds,
    row_number() over (partition by source_record_key order by loaded_at, source_file) as source_occurrence,
    count(*) over (partition by hash(payload)) as identical_payload_count,
    coalesce({{ valid_trip() }}, false) as is_valid,
    array_construct_compact(
        iff(pickup_at is null, 'missing_or_invalid_pickup', null),
        iff(dropoff_at is null, 'missing_or_invalid_dropoff', null),
        iff(dropoff_at < pickup_at, 'negative_duration', null),
        iff(trip_distance_miles is null, 'missing_or_invalid_distance', null),
        iff(trip_distance_miles < 0, 'negative_distance', null),
        iff(total_amount is null, 'missing_or_invalid_total', null)
    ) as rejection_reasons,
    array_construct_compact(
        iff(passenger_count is null, 'unknown_passengers', null),
        iff(trip_distance_miles = 0, 'zero_distance', null),
        iff(total_amount < 0 or fare_amount < 0, 'possible_refund', null),
        iff(to_char(pickup_at, 'YYYY-MM') != source_month, 'pickup_outside_file_month', null),
        iff(store_and_forward_flag is null, 'unknown_store_flag', null),
        iff(vendor_id is null or payment_type is null or rate_code_id is null,
            'missing_or_invalid_code', null),
        iff(pickup_location_id is null or dropoff_location_id is null, 'unknown_location', null)
    ) as quality_flags
from {{ ref('silver_typed') }}
