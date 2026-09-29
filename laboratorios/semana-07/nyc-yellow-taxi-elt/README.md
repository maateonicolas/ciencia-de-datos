# Laboratorio Integrador I — NYC Yellow Taxi ELT

Kestra → descarga/validación → Snowflake RAW → dbt Bronze → Silver → Gold.
Rama exclusiva: `lab/semana-07-nyc-taxi`. Todo el código y estado local del
laboratorio permanece en esta carpeta.

## Estado de la entrega

**INCOMPLETE.** La consulta oficial del 28 de septiembre de 2026 confirma
19/20 archivos: enero–diciembre de 2025 y enero–julio de 2026. Agosto no aparece
en el listado y responde 403; ese código no demuestra inexistencia.

- [Inventario de los 20 meses](docs/source-availability.md) y [evidencia HTTP](docs/source-availability.json).
- **Meses cargados realmente en Snowflake: 19/20.** Recuentos por mes/capa,
  resultados dbt e idempotencia en [validación](docs/validation.md).
- Piloto remoto aprobado: 14 modelos, 66 pruebas dbt y repetición sin duplicados.
- Los 19 Parquet publicados fueron descargados y validados: 75.089.241 filas originales.
- Kestra y PostgreSQL se iniciaron con Compose. El flujo registrado ejecutó el
  piloto `2025-01`: carga `unchanged`, 14 modelos y 66 pruebas dbt aprobadas.
  La evidencia conserva `INCOMPLETE` para la cobertura 19/20; el ajuste del YAML
  debe sincronizarse en la instancia autenticada para que ese estado no aparezca
  como un fallo técnico de Kestra.
- [.env.example](.env.example) contiene solo campos vacíos y nombres de ejemplo;
  credenciales, Parquet y artefactos locales están excluidos de Git.

## Qué corre dónde

| Lugar | Componentes / trabajo |
| --- | --- |
| Docker local | Kestra 1.0.0, PostgreSQL 16.10 solo para metadatos de Kestra; Python 3.12.9 administrado por uv; dbt CLI |
| Disco local | Parquet, caché, reportes por ejecución, perfiles generados y estado de contenedores, excluidos de Git |
| Snowflake | Warehouse XSMALL, stage de originales, RAW/control, vistas Bronze, calidad Silver materializada, dimensiones/hechos Gold y ejecución de SQL/pruebas dbt |

No se simula Snowflake en PostgreSQL. El Process runner ejecuta Python dentro del
contenedor Kestra y no necesita montar el socket Docker. La UI escucha solo en
localhost. Ejecutar una sola tubería por base Snowflake; el flujo tiene concurrencia 1.

## Preparación desde cero

Requisitos: Git, Python 3.12 para CLI local, Docker Desktop/Engine con Compose v2
para Kestra y una cuenta Snowflake. El lock es universal para Windows/Linux.

Desde la raíz del repositorio, en PowerShell:

```powershell
git switch lab/semana-07-nyc-taxi
cd laboratorios/semana-07/nyc-yellow-taxi-elt
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Force secrets, data, reports, .runtime | Out-Null
```

Linux/macOS: usar `.venv/bin/python`. El contenedor instala solo
`requirements.lock.txt`; `requirements-dev.txt` añade el analizador SQL de tests.

Completar localmente `.env`; no pegar secretos en Git ni en logs:

- `SNOWFLAKE_ACCOUNT`: identificador de cuenta, sin https ni dominio.
- `SNOWFLAKE_USER`, `SNOWFLAKE_ROLE`, `SNOWFLAKE_DATABASE` y `SNOWFLAKE_WAREHOUSE`.
  El bootstrap CLI usa estos nombres; `NYC_TAXI` y `NYC_TAXI_WH` son valores sugeridos.
  Se aceptan también las claves locales minúsculas `account`, `user`, `password`,
  `role`, `database` y `warehouse`, sin modificar el archivo de secretos.
- Autenticación `snowflake` y `SNOWFLAKE_PASSWORD` si la política de la cuenta lo
  permite; o `snowflake_jwt` con clave privada local en `secrets/snowflake.p8`
  y su clave pública previamente registrada en Snowflake.
- Para clave privada, `SNOWFLAKE_PRIVATE_KEY_FILE` es una ruta absoluta en CLI
  local. Compose la sustituye por `/opt/nyc-taxi/secrets/snowflake.p8`.
  La contraseña de la clave es opcional. No generar ni registrar claves automáticamente.
- `externalbrowser` se admite solo en CLI local, no en Kestra desatendido.
- Elegir `KESTRA_POSTGRES_PASSWORD` local para Compose. Evitar espacios/saltos
  de línea en este valor porque se incorpora a configuración YAML.

```powershell
.venv/Scripts/python.exe -m ingestion.workflow check-env
```

Este comando solo muestra nombres de variables ausentes; no prueba permisos.
Los perfiles dbt se generan en reportes ignorados, contienen referencias a
variables de entorno, y nunca se versionan. Las variables del proceso prevalecen
sobre `.env`.

## Orden de validación: primero un mes

### 1. Inventario sin credenciales

```powershell
.venv/Scripts/python.exe -m ingestion.pipeline verify
$LASTEXITCODE
```

Esperado hoy: 19/20, `INCOMPLETE`, código 2. Consulta siempre los 20 meses.
HEAD/GET Range comprueba acceso; nunca considera un 403 como evidencia definitiva
de inexistencia. Un fallo técnico del listado produce `FAILED`.

Opcional, solo prueba local del Parquet de enero sin conexión Snowflake:

```powershell
.venv/Scripts/python.exe -m ingestion.workflow run --run-id download-check-01 --month 2025-01 --download-only
```

Este modo termina después de descargar/validar; **no es una carga ni una ejecución
ELT completa**. Cada intento necesita un `run-id` nuevo.

### 2. Infraestructura remota

Con un rol autorizado a crear los objetos:

```powershell
.venv/Scripts/python.exe -m ingestion.workflow bootstrap
```

El CLI adapta los identificadores de base y warehouse a la configuración local
(solo nombres simples). También puede ejecutarse `infrastructure/bootstrap.sql`
en Snowsight adaptando esos dos nombres. No contiene
credenciales ni reemplaza tablas. Un administrador puede usar
`infrastructure/grants.sql` para dar permisos a un rol existente.
El bootstrap se ejecuta una vez a la vez. Mantener el mismo rol propietario de
modelos dbt en ejecuciones posteriores; las tablas estándar no imponen PK/UK.

### 3. Piloto completo y repetición por CLI local

```powershell
.venv/Scripts/python.exe -m ingestion.workflow run --run-id pilot-01 --month 2025-01
.venv/Scripts/python.exe -m ingestion.workflow run --run-id pilot-02 --month 2025-01
.venv/Scripts/python.exe -m ingestion.workflow compare --baseline pilot-01 --run-id pilot-02
```

Cada `run` hace inventario → descarga → carga → dbt seed/run → dbt test → evidencia.
Antes de descargar en modo ELT prueba conexión y acceso al manifiesto.
El código final **2 es esperado** si las etapas pasan pero faltan meses; un código
**1 es fallo técnico** y debe investigarse antes de continuar.
La comparación exige tests aprobados, iguales conteos/huellas por capa y dimensión,
misma consulta analítica y `load_action=unchanged`; escribe `pilot_verified.json`.
No compara tiempos de ejecución como si fueran datos de negocio.

### 4. Levantar Kestra y ejecutar el flujo

```powershell
docker compose config --quiet
docker compose build
docker compose up -d
docker compose ps
```

Abrir [Kestra local](http://localhost:8080), crear un Flow y pegar el contenido de
`kestra/nyc-yellow-taxi.yml` en su editor. Guardar y ejecutar con `month=2025-01`.
Para importar por API en Kestra 1.0 también puede usarse, desde esta carpeta:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/v1/main/flows' -ContentType 'application/x-yaml' -InFile 'kestra/nyc-yellow-taxi.yml'
```

Si la instancia tiene autenticación habilitada, usar su UI autenticada.
El código de cada tarea es el mismo de la CLI, con `execution.id` como ID de reporte.
Ver los seis pasos en la UI. `report` imprime `business_status=INCOMPLETE` y la
cobertura cuando faltan meses. El adaptador del flujo conserva esa evidencia, pero
traduce solo el código 2 de cobertura incompleta en tarea técnica exitosa; los
errores técnicos (código 1) siguen fallando la ejecución.

Para validar idempotencia con dos ejecuciones Kestra, copiar sus IDs de la UI:

```powershell
docker compose exec kestra python -m ingestion.workflow compare --baseline ID_PRIMERA_EJECUCION --run-id ID_REPETICION
```

### 5. Meses disponibles, después del piloto

Ejecutar el flujo Kestra con `month=all`; el código exige el comprobante del piloto.
Alternativa con las mismas etapas, si aún no se usa Kestra:

```powershell
.venv/Scripts/python.exe -m ingestion.workflow run --run-id available-01 --month all
.venv/Scripts/python.exe -m ingestion.workflow run --run-id available-02 --month all
.venv/Scripts/python.exe -m ingestion.workflow compare --baseline available-01 --run-id available-02
```

No reducir el denominador a 19, fabricar agosto ni elegir otro mes.
Cuando se publique agosto, una ejecución nueva vuelve a consultar las 20 URLs.
Se descargan como máximo cuatro archivos simultáneos; las cargas mensuales
usan hasta cuatro conexiones independientes para PUT/COPY; el mutex serializa
los reemplazos transaccionales. La caché evita transferencias innecesarias solo si ETag, Last-Modified, tamaño,
SHA-256 local y validación Parquet coinciden. `--refresh` fuerza la descarga.

## Artefactos y pruebas

`reports/executions/<id>/state.json` contiene inventario, acciones por mes,
estado de cada etapa, resultados dbt, cobertura y consulta Gold.
`target/run_results.json`, `dbt-test.json` y `logs/` conservan evidencia local.
Un intento fallido conserva clase/código del error; no imprime secretos.

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe -m ingestion.workflow parse --run-id offline-parse
.venv/Scripts/python.exe -m pip check
```

`parse` usa un perfil ficticio solo para analizar dbt sin conexión.
**Parse y análisis SQL local no equivalen a dbt test sobre Snowflake.**
Las pruebas dbt incluyen `not_null`, `unique`, `relationships`, reconciliación,
manifiesto vs RAW, reglas de viajes y casos unitarios para conservar viajes iguales.
Una cobertura parcial no se disfraza como fallo de integridad de los meses ya
cargados: el requisito 20/20 lo verifica el reporte final.

Consulta de ejemplo: `infrastructure/evidence.sql` (adaptar `NYC_TAXI` si se
configuró otra base). El reporte ejecuta
conteos por mes/capa, huellas independientes del orden y un ejemplo Gold por
mes y borough. Los resultados remotos observados se conservan en `docs/validation.md` y
`docs/validation-evidence.json`, separados de las pruebas locales.

## Modelo y operación

- [Diseño y decisiones de calidad](docs/design.md)
- [Arquitectura](diagrams/architecture.md)
- [Esquema estrella](diagrams/star-schema.md)
- RAW conserva payload/Parquet; Bronze añade identidad física y linaje.
- Silver tipa y separa rechazos; conserva filas de negocio idénticas.
- Gold tiene `fact_trips`, cinco dimensiones (fecha, zona, proveedor, pago, tarifa)
  y `data_coverage`. Fecha y zona cumplen dos roles: recogida y destino.

La carga mensual valida antes de tocar RAW y reemplaza mes/manifiesto dentro de
una transacción con mutex. Un fallo revierte ambos. DDL y COPY temporal ocurren
fuera de esa transacción. Los originales históricos se guardan por hash.
No ejecutar escritores que omitan ese protocolo ni dos orquestadores distintos
simultáneamente sobre la misma base. El bloqueo local se libera al morir el proceso.
Los fallos no se reanudan sobrescribiendo un reporte: crear un ID nuevo reutiliza
caché y manifiesto de manera segura.

Para detener los componentes locales: `docker compose down`. Los datos remotos
y los directorios de persistencia no se eliminan.

## Git

Solo versionar código, SQL, configuración pública, documentación y evidencia
sanitizada. Excluidos: `.env`, `secrets/`, perfiles privados, Terraform state,
Parquet, `.venv/`, `data/`, `reports/`, `.runtime/` y salidas dbt.
No ejecutar `git add .` desde la raíz del repositorio si hay cambios ajenos.
El código inicial quedó guardado en `97d2466`; no se hace merge a main.
