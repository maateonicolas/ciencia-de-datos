select count(*) as n from {{ ref('expected_months') }} having count(*) != 20
