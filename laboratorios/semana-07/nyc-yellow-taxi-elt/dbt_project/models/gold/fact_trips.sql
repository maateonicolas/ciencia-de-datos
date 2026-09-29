select
    t.source_record_key as trip_key,
    to_number(to_char(t.pickup_at, 'YYYYMMDD')) as pickup_date_key,
    to_number(to_char(t.dropoff_at, 'YYYYMMDD')) as dropoff_date_key,
    coalesce(p.zone_key, -1) as pickup_zone_key,
    coalesce(d.zone_key, -1) as dropoff_zone_key,
    coalesce(v.vendor_key, -1) as vendor_key,
    coalesce(pm.payment_key, -1) as payment_key,
    coalesce(r.rate_key, -1) as rate_key,
    t.pickup_at, t.dropoff_at, t.passenger_count,
    t.trip_distance_miles, t.duration_seconds,
    t.fare_amount, t.extra, t.mta_tax, t.tip_amount, t.tolls_amount,
    t.improvement_surcharge, t.total_amount, t.congestion_surcharge,
    t.airport_fee, t.cbd_congestion_fee, t.store_and_forward_flag,
    t.pickup_location_id as source_pickup_location_id,
    t.dropoff_location_id as source_dropoff_location_id,
    t.vendor_id as source_vendor_id, t.payment_type as source_payment_type,
    t.rate_code_id as source_rate_code_id, t.quality_flags, t.identical_payload_count,
    t.source_record_key, t.source_file, t.source_month, t.source_sha256, t.source_row, t.loaded_at
from {{ ref('silver_trips') }} t
left join {{ ref('dim_zone') }} p on t.pickup_location_id = p.zone_key
left join {{ ref('dim_zone') }} d on t.dropoff_location_id = d.zone_key
left join {{ ref('dim_vendor') }} v on t.vendor_id = v.vendor_key
left join {{ ref('dim_payment') }} pm on t.payment_type = pm.payment_key
left join {{ ref('dim_rate') }} r on t.rate_code_id = r.rate_key
