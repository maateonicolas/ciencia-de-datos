# Esquema estrella implementado

```mermaid
erDiagram
    DIM_DATE ||--o{ FACT_TRIPS : pickup_date_key
    DIM_DATE ||--o{ FACT_TRIPS : dropoff_date_key
    DIM_ZONE ||--o{ FACT_TRIPS : pickup_zone_key
    DIM_ZONE ||--o{ FACT_TRIPS : dropoff_zone_key
    DIM_VENDOR ||--o{ FACT_TRIPS : vendor_key
    DIM_PAYMENT ||--o{ FACT_TRIPS : payment_key
    DIM_RATE ||--o{ FACT_TRIPS : rate_key
    FACT_TRIPS {
        string trip_key PK
        int pickup_date_key FK
        int dropoff_date_key FK
        int pickup_zone_key FK
        int dropoff_zone_key FK
        int vendor_key FK
        int payment_key FK
        int rate_key FK
        timestamp pickup_at
        timestamp dropoff_at
        number passenger_count
        number trip_distance_miles
        number duration_seconds
        number total_amount
        number tip_amount
        number cbd_congestion_fee
        string source_record_key
        string source_month
        string source_file
        string source_sha256
        int source_row
        timestamp loaded_at
    }
    DIM_DATE {
        int date_key PK
        date calendar_date
        int year
        int month
        int day
        int weekday_iso
    }
    DIM_ZONE {
        int zone_key PK
        string borough
        string zone
        string service_zone
        string source_sha256
    }
    DIM_VENDOR {
        int vendor_key PK
        string vendor_name
    }
    DIM_PAYMENT {
        int payment_key PK
        string payment_name
    }
    DIM_RATE {
        int rate_key PK
        string rate_name
    }
```

Grano del hecho: **una fila física válida de viaje**, aunque otra comparta sus
atributos de negocio. PK/FK son lógicas y tienen pruebas dbt. Fecha y zona tienen
dos roles. Los códigos desconocidos se conservan como atributos originales y se
asocian a -1 en sus dimensiones. Métricas adicionales y reglas en docs/design.md.
GOLD.DATA_COVERAGE es una tabla auxiliar de 20 meses; no cambia el grano del hecho.
