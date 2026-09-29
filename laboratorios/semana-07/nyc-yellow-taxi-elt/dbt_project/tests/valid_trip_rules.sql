select trip_key from {{ ref('fact_trips') }}
where pickup_at is null or dropoff_at is null or dropoff_at < pickup_at
   or trip_distance_miles is null or trip_distance_miles < 0 or total_amount is null
