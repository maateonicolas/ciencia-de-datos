{% macro integer_value(expression) -%}
case when regexp_like(trim({{ expression }}::varchar), '^-?[0-9]+([.]0+)?$')
then try_to_number({{ expression }}::varchar, 38, 0) end
{%- endmacro %}

{% macro valid_trip() -%}
pickup_at is not null and dropoff_at is not null
and dropoff_at >= pickup_at
and trip_distance_miles is not null and trip_distance_miles >= 0
and total_amount is not null
{%- endmacro %}
