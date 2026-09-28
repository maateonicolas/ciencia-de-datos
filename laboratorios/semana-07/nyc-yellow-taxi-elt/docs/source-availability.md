# Disponibilidad de los 20 archivos

Consulta directa del 28 de septiembre de 2026 (UTC). Fuente: [TLC](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page).

**19 publicados y accesibles; 1 pendiente de publicación. Estado: INCOMPLETE.**

Se consultó la página oficial y se ejecutó HEAD para cada URL. No se descargaron cuerpos Parquet. El JSON adjunto contiene hora UTC, tamaño, ETag y Last-Modified por archivo.

| Mes | Archivo | En página oficial | HTTP HEAD | Bytes | Publicación |
| --- | --- | --- | --- | --- | --- |
| 2025-01 | [yellow_tripdata_2025-01.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet) | Sí | 200 | 59158238 | Publicado |
| 2025-02 | [yellow_tripdata_2025-02.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-02.parquet) | Sí | 200 | 60343086 | Publicado |
| 2025-03 | [yellow_tripdata_2025-03.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-03.parquet) | Sí | 200 | 69964745 | Publicado |
| 2025-04 | [yellow_tripdata_2025-04.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-04.parquet) | Sí | 200 | 67352824 | Publicado |
| 2025-05 | [yellow_tripdata_2025-05.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-05.parquet) | Sí | 200 | 77837865 | Publicado |
| 2025-06 | [yellow_tripdata_2025-06.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-06.parquet) | Sí | 200 | 73542954 | Publicado |
| 2025-07 | [yellow_tripdata_2025-07.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-07.parquet) | Sí | 200 | 66943728 | Publicado |
| 2025-08 | [yellow_tripdata_2025-08.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-08.parquet) | Sí | 200 | 62293743 | Publicado |
| 2025-09 | [yellow_tripdata_2025-09.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-09.parquet) | Sí | 200 | 72432945 | Publicado |
| 2025-10 | [yellow_tripdata_2025-10.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-10.parquet) | Sí | 200 | 75267589 | Publicado |
| 2025-11 | [yellow_tripdata_2025-11.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-11.parquet) | Sí | 200 | 71134255 | Publicado |
| 2025-12 | [yellow_tripdata_2025-12.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-12.parquet) | Sí | 200 | 73701327 | Publicado |
| 2026-01 | [yellow_tripdata_2026-01.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-01.parquet) | Sí | 200 | 64165080 | Publicado |
| 2026-02 | [yellow_tripdata_2026-02.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-02.parquet) | Sí | 200 | 58683353 | Publicado |
| 2026-03 | [yellow_tripdata_2026-03.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-03.parquet) | Sí | 200 | 67891249 | Publicado |
| 2026-04 | [yellow_tripdata_2026-04.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-04.parquet) | Sí | 200 | 64818115 | Publicado |
| 2026-05 | [yellow_tripdata_2026-05.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-05.parquet) | Sí | 200 | 69699174 | Publicado |
| 2026-06 | [yellow_tripdata_2026-06.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-06.parquet) | Sí | 200 | 65465637 | Publicado |
| 2026-07 | [yellow_tripdata_2026-07.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-07.parquet) | Sí | 200 | 61685033 | Publicado |
| 2026-08 | [yellow_tripdata_2026-08.parquet](https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2026-08.parquet) | No | 403 |  | Pendiente |

Agosto de 2026 no figura en la página. Su URL devuelve 403: no se infiere que el objeto no exista, ni que 403 equivalga a 404. Se conserva la evidencia de acceso fallido y se espera su publicación oficial; no se sustituye el mes ni se reduce el total esperado.

HTTP 200 confirma accesibilidad, no integridad o esquema. Esas validaciones se ejecutan al descargar. No hay evidencia de una carga Snowflake en esta revisión.

Evidencia estructurada: [source-availability.json](source-availability.json).
