# Estrella propuesta (implementación dbt pendiente)

```mermaid
erDiagram
    DIM_DATE ||--o{ FACT_TRIPS : pickup_date_key
    DIM_ZONE ||--o{ FACT_TRIPS : pickup_zone_key
    DIM_ZONE ||--o{ FACT_TRIPS : dropoff_zone_key
    DIM_VENDOR ||--o{ FACT_TRIPS : vendor_key
    DIM_PAYMENT ||--o{ FACT_TRIPS : payment_key
    DIM_RATE ||--o{ FACT_TRIPS : rate_key
    FACT_TRIPS {
        string trip_key PK
        int pickup_date_key FK
        int pickup_zone_key FK
        int dropoff_zone_key FK
        int vendor_key FK
        int payment_key FK
        int rate_key FK
        timestamp pickup_at
        timestamp dropoff_at
        number distance
        number duration_seconds
        number total_amount
        number tip_amount
        number cbd_congestion_fee
        string source_file
    }
    DIM_DATE {
        int date_key PK
        date calendar_date
        int year
        int month
    }
    DIM_ZONE {
        int zone_key PK
        string borough
        string zone
        string service_zone
    }
    DIM_VENDOR {
        int vendor_key PK
        string description
    }
    DIM_PAYMENT {
        int payment_key PK
        string description
    }
    DIM_RATE {
        int rate_key PK
        string description
    }
```

Grano: un viaje válido tras deduplicación exacta. Las dos zonas utilizan la misma
dimensión. Métricas, atributos adicionales y claves se describen en `docs/design.md`.
