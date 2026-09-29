# Arquitectura implementada

```mermaid
flowchart LR
  subgraph local["Docker local"]
    K["Kestra: concurrency 1"] --> I["Inventario 20 meses"]
    PG["PostgreSQL: metadatos Kestra"] --- K
    I --> D["Descarga / caché SHA-256 / validación Parquet"]
    D --> L["Carga Python"]
    L --> DBT["dbt seed → run → test"]
    DBT --> E["Conteos, huellas y consulta Gold"]
    E --> R["SUCCESS solo 20/20; INCOMPLETE o FAILED"]
    F["Archivos y reportes ignorados por Git"] --- D
  end
  TLC["TLC Parquet + catálogo de zonas"] --> I
  TLC --> D
  subgraph cloud["Snowflake"]
    ST["Stage: originales por mes/hash"] --> TMP["COPY temporal"]
    TMP --> RAW["RAW.YELLOW_TRIPS + LOAD_MANIFEST"]
    MUT["INGESTION_MUTEX"] --- RAW
    Z["RAW.TAXI_ZONES"] --> BZ["BRONZE.BRONZE_ZONES"]
    RAW --> B["BRONZE.BRONZE_TRIPS"]
    B --> T["SILVER.SILVER_TYPED"]
    T --> Q["SILVER.SILVER_QUALITY"]
    Q --> V["SILVER_TRIPS"]
    Q --> X["SILVER_REJECTED / SILVER_DUPLICATE_ROWS"]
    V --> G["GOLD: FACT_TRIPS + DIM_*"]
    BZ --> G
    G --> C["GOLD.DATA_COVERAGE"]
    RAW --> C
    X --> C
  end
  L --> ST
  L --> Z
  DBT --> B
  DBT --> G
  C --> E
```

Python y dbt CLI ejecutan localmente; datos, transformaciones y tests SQL corren
en Snowflake. No hay base Snowflake dentro de Docker. PostgreSQL solo almacena
la orquestación. dbt no proporciona publicación atómica de toda la estrella;
el estado final y sus pruebas determinan si la ejecución es aceptable.
