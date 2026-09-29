select column1::number as rate_key, column2::varchar as rate_name
from values (-1, 'Unknown code'), (1, 'Standard'), (2, 'JFK'), (3, 'Newark'),
    (4, 'Nassau or Westchester'), (5, 'Negotiated'), (6, 'Group'), (99, 'Null/unknown')
