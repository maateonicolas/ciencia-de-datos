with dates as (
    select to_date(pickup_at) as calendar_date from {{ ref('silver_trips') }}
    union
    select to_date(dropoff_at) from {{ ref('silver_trips') }}
)
select to_number(to_char(calendar_date, 'YYYYMMDD')) as date_key,
       calendar_date, year(calendar_date) as year, month(calendar_date) as month,
       day(calendar_date) as day, dayofweekiso(calendar_date) as weekday_iso
from dates
