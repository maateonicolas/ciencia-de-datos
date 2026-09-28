# Diseño de ingesta y modelo objetivo

## Contrato y estados

Universo fijo: `2025-01` a `2026-08`, 20 archivos Yellow Taxi. La ausencia de
agosto en el listado oficial mantiene la entrega `INCOMPLETE`.

Se registra publicación oficial, HTTP y metadatos por separado. Un 403 de un
archivo listado es `check_failed`; si no figura en la página, se registra
`pending_publication` y se conserva el 403 sin inferir que el objeto no existe.
No poder consultar o interpretar la página produce `check_failed`.

Disponibilidad: `available / pending_publication / check_failed`.
Operación: `not_started / running / downloaded / loaded / failed`.
Reportes por ID en `reports/runs/`, escritos mediante renombrado atómico.
El manifiesto Snowflake es la autoridad de cargas confirmadas; un reporte local
no demuestra la existencia de datos remotos. El comando vuelve a comprobar
conteos antes de omitir una versión idéntica.

Salida 0 significa etapa completa; 2, cobertura incompleta; 1, fallo técnico.
`pipeline_status` sigue `INCOMPLETE` incluso cuando una etapa completa 20/20:
todavía faltan dbt y sus pruebas. Esta versión nunca emite SUCCESS global.

## Idempotencia implementada

1. Verificar los 20 meses; procesar solo enlaces oficiales accesibles.
2. Descargar a `.partial`, comprobar longitud, decodificar todas las filas
   Parquet por lotes y exigir columnas mínimas. Rechazar archivos vacíos o
   estructuralmente inválidos sin filtrar valores de negocio.
3. Calcular SHA-256 y renombrar a `data/<sha256>/yellow_tripdata_YYYY-MM.parquet`.
   Cada ejecución descarga otra vez para detectar revisiones. ETag no se trata
   como checksum. La optimización HTTP condicional queda para una próxima etapa.
4. PUT del original a stage por mes/hash. COPY a tabla temporal con
   `ON_ERROR=ABORT_STATEMENT`, payload VARIANT y `METADATA$FILE_ROW_NUMBER`.
   Comparar conteo total y filas físicas distintas con PyArrow.
5. BEGIN, actualizar mutex compartido, leer manifiesto y conteos. Hash y conteos
   iguales: no insertar. Archivo nuevo, revisado o incompleto: DELETE del mes,
   INSERT de todas sus filas y sustitución del manifiesto dentro de la transacción.
6. COMMIT conjunto o ROLLBACK. PUT, DDL y COPY temporal van antes; DDL puede
   confirmar implícitamente transacciones Snowflake.

No se depende del historial automático de COPY. `FORCE=TRUE` solo carga una tabla
temporal recién creada. Los archivos revisados se conservan por hash. Duplicados
del origen permanecen en RAW/Bronze; repetir la carga no crea duplicados nuevos.

El bloqueo local evita dos procesos sobre el mismo directorio. Un cierre abrupto
puede dejar `data/pipeline.lock`: comprobar que no queda proceso antes de retirarlo.
El UPDATE de `INGESTION_MUTEX` serializa escritores que usan este protocolo,
incluso desde otro host. Ejecutar bootstrap sin concurrencia y no escribir RAW
desde procesos que omitan el mutex. No confiar en PRIMARY KEY declarativas de
tablas estándar Snowflake. Integración, concurrencia y rollback reales siguen
pendientes; los tests locales del cargador verifican el protocolo con un cursor simulado.

## Capas dbt previstas

### Bronze

Una fila por fila física del archivo vigente, identificada por
`source_month + source_sha256 + source_row`; conservar `source_file`, `loaded_at`
y payload. No deduplicar ni corregir valores. El mes corresponde al archivo,
no se recalcula con pickup: el origen puede incluir fechas fuera del período.
El original binario se conserva en stage.

### Silver

`silver_trip_quality` conservará filas, valores originales, valores tipados y
motivos de invalidez. Derivar válidos y rechazados sin eliminar silenciosamente.

| Caso | Decisión propuesta y motivo |
| --- | --- |
| Tipos/fechas | TRY_TO_*; fallo a NULL más bandera, sin inventar valores |
| Hora | TIMESTAMP_NTZ local NYC; no asumir UTC ni resolver ambigüedad DST sin evidencia |
| Formatos | TRIM, vacío a NULL y códigos canónicos, preservando el original |
| Nulos | Rechazar pickup/dropoff ausentes; pasajeros desconocidos siguen NULL, no imputar 1 |
| Duración | Rechazar dropoff anterior a pickup; marcar extremos y medirlos antes de fijar umbrales |
| Distancia | Rechazar negativos; conservar cero con bandera por posibles ajustes |
| Importes | Conservar negativos con bandera de ajuste/reembolso; no aplicar valor absoluto ni borrar automáticamente |
| Zonas/códigos | Dimensión con miembro desconocido -1; conservar también el código fuente |
| Duplicados | Comparar todas las columnas de negocio canónicas; retener uno con orden determinista y contabilizar descartados |
| Mes inconsistente | Señalar pickup fuera del mes del archivo; no mover la partición original |

No hay un ID de viaje universal. La deduplicación exacta es una hipótesis:
viajes genuinos podrían compartir atributos. Medir su impacto y evitar claves
débiles como pickup/dropoff solamente. Incluir `cbd_congestion_fee` desde 2025;
RAW preserva también columnas nuevas no proyectadas aún.

### Gold: estrella propuesta

| Tabla | Grano y clave | Atributos / métricas |
| --- | --- | --- |
| fact_trips | Un viaje válido deduplicado; trip_key hash de columnas de negocio canónicas | FKs fecha pickup, zonas pickup/dropoff, proveedor, pago y tarifa; timestamps, pasajeros, distancia, duración, fare, tip, tolls, impuestos, recargos, cbd_congestion_fee, total y linaje |
| dim_date | Un día local; date_key YYYYMMDD | Fecha, año, mes, día y día de semana |
| dim_zone | Una zona TLC; zone_key LocationID, -1 desconocido | Borough, zone, service_zone; dimensión compartida para pickup/dropoff |
| dim_vendor | Un código proveedor; vendor_key | Código y descripción oficial |
| dim_payment | Un código de pago; payment_key | Código y descripción |
| dim_rate | Un código de tarifa; rate_key | Código y descripción |

El CSV oficial de zonas es auxiliar y no sustituye ninguno de los 20 Parquet;
se verificará y registrará su checksum al implementar dimensiones. Calcular
promedios desde sumas/conteos, no promediar promedios. No asumir que tip_amount
incluye propinas en efectivo.

Pruebas dbt: `not_null` y `unique` en claves; `relationships` en cada FK,
incluidas ambas zonas; `not_null` en linaje. Reconciliar Bronze = válidos +
rechazados + duplicados descartados con categorías disjuntas; Silver válido =
hechos. Una tabla de cobertura conserva los 20 meses y etiqueta Gold parcial.
La entrega requiere 20 cargas confirmadas, `dbt build` e integración aprobados.

## Referencias

- [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)
- [Metadatos de archivos](https://docs.snowflake.com/en/user-guide/querying-metadata)
- [Transacciones y DDL](https://docs.snowflake.com/en/sql-reference/transactions)
- [Conector Python](https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-example)
