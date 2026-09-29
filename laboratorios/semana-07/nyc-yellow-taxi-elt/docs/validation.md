# Validación observada — 28 de septiembre de 2026

**Estado global: INCOMPLETE.** Agosto de 2026 no figura en el listado TLC; su HTTP 403 no demuestra inexistencia.

La evidencia estructurada sanitizada está en [validation-evidence.json](validation-evidence.json).
Los reportes completos, perfiles, logs y Parquet permanecen localmente fuera de Git.

## Ejecutado realmente

- Conexión y bootstrap Snowflake con las credenciales locales, sin mostrarlas.
- Pilotos `snowflake-pilot-02` y `snowflake-pilot-03`: 14 modelos y 66 pruebas dbt aprobadas en cada uno.
- Comparación del piloto: PASS; mismos conteos, huellas, dimensiones y consulta Gold; carga repetida unchanged.
- 23 tests Python aprobados. Incluyen servicios simulados; no equivalen a pruebas remotas.
- dbt parse sin conexión, análisis SQL Snowflake y esquema JSON de Compose aprobados.
- pip check sin incompatibilidades. Documentación de columnas cotejada con los 14 modelos reales.
- Se corrigió el alias reservado ROWS del informe. El intento fallido snowflake-pilot-01 se conserva.
- Los intentos secuenciales snowflake-available-01/02 se interrumpieron y quedaron FAILED; se reutilizaron caché válida y meses confirmados.
- .env.example fue saneado antes del commit; auditoría del commit inicial sin coincidencias de la contraseña local.
- Kestra ejecutó el flujo registrado `lab.semana07.nyc-yellow-taxi-elt` con `2025-01` (ejecución `1l89w7BQgKIZOnlz6ZRASm`). Inventario, descarga, carga `unchanged`, 14 modelos y 66 pruebas terminaron correctamente. El reporte confirmó 19/20 y `INCOMPLETE`.
- El YAML ajustado conserva ese estado de negocio como salida y convierte solamente el código 2 esperado de cobertura incompleta en éxito técnico de la tarea. Los errores técnicos siguen devolviendo código 1.

## Recuentos remotos por mes de archivo

Ejecución de referencia: `snowflake-available-03`. Meses realmente cargados: **19/20**.

| Mes | RAW / Bronze | Silver válido | Rechazados | Duplicados físicos | Gold | Estado |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 2025-01 | 3475226 | 3475102 | 124 | 0 | 3475102 | LOADED |
| 2025-02 | 3577543 | 3577450 | 93 | 0 | 3577450 | LOADED |
| 2025-03 | 4145257 | 4145176 | 81 | 0 | 4145176 | LOADED |
| 2025-04 | 3970553 | 3970390 | 163 | 0 | 3970390 | LOADED |
| 2025-05 | 4591845 | 4591744 | 101 | 0 | 4591744 | LOADED |
| 2025-06 | 4322960 | 4322729 | 231 | 0 | 4322729 | LOADED |
| 2025-07 | 3898963 | 3898962 | 1 | 0 | 3898962 | LOADED |
| 2025-08 | 3574091 | 3574089 | 2 | 0 | 3574089 | LOADED |
| 2025-09 | 4251015 | 4251015 | 0 | 0 | 4251015 | LOADED |
| 2025-10 | 4428699 | 4428697 | 2 | 0 | 4428697 | LOADED |
| 2025-11 | 4181444 | 4180009 | 1435 | 0 | 4180009 | LOADED |
| 2025-12 | 4305006 | 4305004 | 2 | 0 | 4305004 | LOADED |
| 2026-01 | 3724889 | 3724888 | 1 | 0 | 3724888 | LOADED |
| 2026-02 | 3399866 | 3399864 | 2 | 0 | 3399864 | LOADED |
| 2026-03 | 3952451 | 3952449 | 2 | 0 | 3952449 | LOADED |
| 2026-04 | 3831240 | 3831240 | 0 | 0 | 3831240 | LOADED |
| 2026-05 | 4090836 | 4090836 | 0 | 0 | 4090836 | LOADED |
| 2026-06 | 3837248 | 3837247 | 1 | 0 | 3837247 | LOADED |
| 2026-07 | 3530109 | 3530108 | 1 | 0 | 3530108 | LOADED |
| 2026-08 | 0 | 0 | 0 | 0 | 0 | NOT_LOADED |

RAW coincide con el manifiesto y Bronze mediante pruebas dbt. No se deduplican viajes distintos por compartir atributos.

## Resultados dbt e idempotencia

| Ejecución | Modelos | Pruebas aprobadas | Estado de negocio |
| --- | ---: | ---: | --- |
| snowflake-pilot-03 | 14 | 66 | INCOMPLETE |
| snowflake-available-03 | 14 | 66 | INCOMPLETE |

Comparación `snowflake-pilot-02` → `snowflake-pilot-03`: **PASS**.

## Consulta Gold observada

La consulta de `infrastructure/evidence.sql` agrupa por fecha de recogida y borough, no por mes del archivo.
Enero de 2025, Manhattan: **3089233 viajes**, importe registrado **USD 67089101.4300**, distancia media **4.4438805360 millas**.
Los importes pueden incluir ajustes y no equivalen necesariamente a efectivo cobrado. El JSON conserva resultados y huellas.

## Comandos ejecutados

Desde la carpeta del laboratorio:

```powershell
.venv/Scripts/python.exe -m ingestion.workflow check-env
.venv/Scripts/python.exe -m ingestion.workflow bootstrap
.venv/Scripts/python.exe -m ingestion.workflow run --run-id snowflake-pilot-02 --month 2025-01
.venv/Scripts/python.exe -m ingestion.workflow run --run-id snowflake-pilot-03 --month 2025-01
.venv/Scripts/python.exe -m ingestion.workflow compare --baseline snowflake-pilot-02 --run-id snowflake-pilot-03
.venv/Scripts/python.exe -m ingestion.workflow run --run-id snowflake-available-03 --month all
.venv/Scripts/python.exe -m unittest discover -s tests -q
.venv/Scripts/python.exe -m ingestion.workflow parse --run-id offline-parse
.venv/Scripts/python.exe -m pip check
```

Las ejecuciones con cobertura parcial terminan con código 2, no 0. Fallos técnicos terminan con 1.

## Pendiente

- El YAML ajustado quedó sincronizado como revisión 2 y Kestra fue reiniciado sin ejecuciones activas; su representación ejecutable coincide con el archivo versionado. Falta iniciar el nuevo piloto desde una sesión autenticada de Kestra para confirmar que la ejecución técnica queda en SUCCESS mientras conserva `business_status=INCOMPLETE`.
- Esperar la publicación verificable de agosto de 2026; ejecutar de nuevo los 20 meses y sus pruebas.
- No se declara el laboratorio completo ni se inventan datos del mes pendiente.
