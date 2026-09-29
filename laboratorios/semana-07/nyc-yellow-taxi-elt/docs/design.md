# Diseño implementado

## Contrato y estados

Universo fijo: enero–diciembre 2025 y enero–agosto 2026. El inventario consulta
los 20 archivos en cada ejecución; el modo piloto solo limita qué meses procesa.
Disponibilidad, descarga, carga y aceptación son estados distintos.

`available`: enlace oficial y HTTP 200/206. `pending_publication`: mes no
listado o enlace listado que responde 404. Si un mes no listado responde 403,
se conserva ese código sin afirmar inexistencia. Un fallo técnico sobre un
enlace listado o no poder leer la página produce `check_failed`.

Cada ejecución tiene ID nuevo y reportes propios. Una etapa intermedia terminada
devuelve 0, pero conserva negocio INCOMPLETE. El reporte final devuelve 0/SUCCESS
solo con 20 meses accesibles, validados y cargados, cobertura remota 20/20 y todas
las pruebas dbt aprobadas. Devuelve 2/INCOMPLETE si falta cobertura; 1/FAILED por
error técnico. Kestra no presenta cobertura incompleta como éxito.

## Ingesta e idempotencia

1. Inventario completo, con comprobación de conexión/permisos antes de descargar
   en modo ELT. La carga masiva requiere evidencia de dos pilotos iguales.
2. Caché por SHA-256: reusar únicamente si los metadatos remotos de una consulta
   nueva coinciden y el archivo local pasa SHA, tamaño, esquema y lectura completa.
   ETag no es un checksum local. `--refresh` ignora caché.
3. Descargar hasta cuatro meses simultáneamente, cada uno a su temporal;
   solo el hilo principal actualiza el reporte. Comprobar Content-Length y decodificar todos los lotes
   Parquet. Archivo vacío, truncado o sin columnas requeridas se rechaza.
   Renombrar atómicamente solo después de validarlo.
4. Antes del PUT volver a verificar los bytes locales. Una consulta consistente
   comprueba manifiesto, hash, conteo total y números físicos distintos: si la
   versión ya está cargada, no se vuelve a transferir. El stage conserva el
   Parquet original por mes/hash. COPY a tabla temporal conserva payload VARIANT,
   tipos lógicos Parquet y número físico de fila; exige conteo y filas distintas.
5. Hasta cuatro conexiones independientes preparan PUT/COPY en paralelo.
   Las transacciones de reemplazo se serializan mediante el mutex compartido:
   BEGIN → UPDATE mutex → comprobar manifiesto y conteos → omitir versión
   idéntica o DELETE+INSERT del mes y manifiesto → COMMIT. ROLLBACK ante fallo.
   No se reemplaza una carga válida por una descarga incompleta.
6. La historia automática de COPY no garantiza esta idempotencia: se usa el
   manifiesto propio. FORCE solo opera sobre una temporal nueva.
   Los duplicados de origen permanecen intactos en RAW.

El bloqueo OS local cubre cada invocación y se libera tras una interrupción.
Kestra serializa ejecuciones completas. El mutex remoto protege el reemplazo
de tablas por escritores cooperantes. No mezclar orquestadores que reconstruyan
dbt simultáneamente: dbt materializa modelos individualmente, no hay transacción
global entre todos los modelos. Si dbt falla, el reporte FAILED invalida la entrega
aunque algunos modelos hayan quedado actualizados.

## Bronze

`bronze_trips`: vista sobre RAW, una fila por fila física vigente. Clave lógica:
SHA-256 de `source_month:source_sha256:source_row`. Conserva payload, archivo,
mes de origen, hash y fecha de carga. No cambiar el mes por la fecha de pickup.
Un reemplazo de archivo produce nuevas identidades porque cambió el origen.
`bronze_zones` proyecta el CSV oficial con hash y fecha de carga.

## Silver

`silver_typed` normaliza nombres y tipos. `silver_quality` materializa reglas,
linaje, motivos de rechazo y advertencias una vez por ejecución.
`silver_trips`, `silver_rejected` y `silver_duplicate_rows` son particiones
disjuntas para reconciliación. El payload original sigue disponible en Silver.

| Caso | Regla implementada / motivo |
| --- | --- |
| Fechas | TRY_TO_TIMESTAMP_NTZ de la representación lógica; valor vacío/inválido pasa a NULL |
| Zona horaria | Semántica local NYC, sin convertir a UTC ni inventar una resolución DST |
| IDs enteros | Aceptar enteros y representaciones como 1.0; rechazar decimales fraccionarios, sin redondearlos a otro código |
| Pasajeros | Nulo, fraccionario o negativo se deja desconocido; no imputar 1 ni eliminar el viaje |
| Métricas | TRY_TO_DECIMAL(18,4), distancias en millas e importes en USD; no sustituir nulos por cero |
| Aeropuerto | Admitir Airport_fee observado en enero 2025 y airport_fee; nombre final airport_fee |
| Store flag | TRIM + mayúsculas; solo Y/N, demás NULL y advertencia |
| Rechazo | Pickup/dropoff inválidos o ausentes, duración negativa, distancia inválida/ausente/negativa, total inválido/ausente |
| Importe negativo | Conservar como posible ajuste/reembolso con bandera, no aplicar valor absoluto |
| Distancia cero | Conservar con advertencia, sin asumir que es un viaje inexistente |
| Mes fuera del archivo | Marcar, mantener mes de origen y fecha real por separado |
| Código desconocido | Conservar código original, usar dimensión -1; no eliminar viaje |
| Valores iguales | Contabilizar grupos hash(payload), sin deduplicar por esos valores |
| Identidad física repetida | Conservar una ocurrencia para vistas de consumo, exponer resto por separado y hacer fallar prueba de integridad |

No existe ID universal de viaje en TLC. **No se eliminan dos filas físicas por
compartir todos sus atributos de negocio.** El hash de payload es diagnóstico,
puede tener colisiones y no es la clave del hecho. Los duplicados de ingesta se
previenen con carga mensual atómica y se detectan con pruebas de identidad física.

Los campos monetarios opcionales inválidos permanecen NULL; el payload permite
auditar su valor original. No se impone un umbral arbitrario de duración, velocidad
o precio. Esas reglas requerirían un análisis adicional y decisiones documentadas.

## Gold y claves lógicas

| Modelo | Grano / PK | Atributos, FKs y métricas |
| --- | --- | --- |
| fact_trips | Una fila física de viaje válido; trip_key = source_record_key | FKs pickup_date_key, dropoff_date_key, pickup_zone_key, dropoff_zone_key, vendor_key, payment_key, rate_key; pasajeros, distancia, segundos, importes/desglose, timestamps y linaje |
| dim_date | Una fecha local presente en viajes válidos; date_key YYYYMMDD | calendar_date, year, month, day, weekday_iso; roles pickup/dropoff |
| dim_zone | Una LocationID del catálogo, más -1; zone_key | borough, zone, service_zone, hash del catálogo; roles pickup/dropoff |
| dim_vendor | Un código de proveedor más -1 | nombre oficial; códigos 1,2,6,7 |
| dim_payment | Un código de pago más -1 | códigos 0–6 y descripción |
| dim_rate | Un código de tarifa más -1 | códigos 1–6,99 y descripción |
| data_coverage | Un mes esperado, siempre 20 filas | hash, manifiesto, conteos Bronze/Silver/rechazados/duplicados/Gold y estado de carga |

Son PK/FK lógicas comprobadas por dbt, no restricciones físicas garantizadas por
Snowflake. Las dimensiones de códigos usan el diccionario TLC del 18/03/2025.
El catálogo de 265 zonas es auxiliar y no cuenta como el archivo mensual 20.
CSV validado por cabeceras, IDs positivos/únicos, nombres y checksum, cargado con
reemplazo transaccional. La dimensión incluye un miembro -1 adicional.

SUM(total_amount) es importe registrado, puede incluir ajustes negativos y no
representa necesariamente efectivo cobrado. tip_amount excluye propinas en
efectivo. AVG se calcula desde viajes individuales, no promediando promedios.
No asumir que fecha de pickup y mes del archivo coinciden.

## Pruebas y evidencia

dbt: not_null/unique en claves; relationships para las siete FKs del hecho,
incluidas las dos fechas/zonas, y para su linaje; conteos reconciliados:
Bronze = Silver válido + rechazados + identidades repetidas; válido = Gold.
El manifiesto debe coincidir con RAW y no hay meses fuera del contrato.
Las pruebas unitarias SQL cubren viajes distintos con valores iguales, rechazos,
nulos opcionales y reembolsos. Solo ejecutarlas en Snowflake constituye evidencia remota.

El reporte consulta conteos y huellas por mes en RAW/Bronze/Silver/rechazados/Gold,
huellas de dimensiones y consulta analítica Gold. `compare` exige resultados
idénticos y carga repetida sin cambio. El gate de cobertura es externo a dbt:
19 meses consistentes pueden pasar dbt sin convertir la entrega de 20 meses en éxito.

## Referencias oficiales

- [TLC y catálogo](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
- [Diccionario Yellow Taxi](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf)
- [COPY INTO](https://docs.snowflake.com/en/sql-reference/sql/copy-into-table)
- [Transacciones y DDL](https://docs.snowflake.com/en/sql-reference/transactions)
- [Kestra Compose](https://kestra.io/docs/installation/docker-compose)
- [Process runner](https://kestra.io/plugins/core/runner/io.kestra.plugin.core.runner.process)
- [dbt Snowflake](https://docs.getdbt.com/docs/local/connect-data-platform/snowflake-setup)
