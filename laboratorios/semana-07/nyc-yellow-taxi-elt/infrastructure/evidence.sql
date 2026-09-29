-- Run after dbt run + dbt test. Coverage is source-file month, not pickup month.
select * from NYC_TAXI.GOLD.DATA_COVERAGE order by source_month;
select source_month, count(*) as trips,
       sum(total_amount) as total_amount, sum(trip_distance_miles) as miles,
       sum(duration_seconds) as duration_seconds,
       hash_agg(hash(trip_key, total_amount, trip_distance_miles, duration_seconds)) as fingerprint
from NYC_TAXI.GOLD.FACT_TRIPS group by 1 order by 1;
-- Gold example; missing months remain visible in DATA_COVERAGE.
select d.year, d.month, z.borough, count(*) as trips,
       sum(f.total_amount) as billed_amount,
       avg(f.trip_distance_miles) as average_miles
from NYC_TAXI.GOLD.FACT_TRIPS f
join NYC_TAXI.GOLD.DIM_DATE d on f.pickup_date_key = d.date_key
join NYC_TAXI.GOLD.DIM_ZONE z on f.pickup_zone_key = z.zone_key
group by 1,2,3 order by 1,2,3;
