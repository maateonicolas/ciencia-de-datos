# Laboratorio Integrador I — NYC Yellow Taxi ELT

Trabajo exclusivo en `lab/semana-07-nyc-taxi` y esta carpeta. Período fijo:
enero–diciembre de 2025 y enero–agosto de 2026 (20 meses).

## Estado actual

Al 28 de septiembre de 2026: **19/20 archivos publicados y accesibles; agosto de
2026 pendiente de publicación. INCOMPLETE.** La URL de agosto devuelve 403;
no se interpreta como prueba de que el objeto no exista.

- [Inventario de los 20 archivos](docs/source-availability.md) y
  [evidencia HTTP con hora UTC](docs/source-availability.json).
- Implementado: verificación, descarga automática con validación Parquet y
  SHA-256, cargador Snowflake con reemplazo mensual transaccional, infraestructura SQL.
- [Diseño de idempotencia y capas](docs/design.md),
  [arquitectura](diagrams/architecture.md) y [estrella](diagrams/star-schema.md).
- Pendiente: ejecutar integración real en Snowflake e implementar modelos/pruebas
  dbt Bronze → Silver → Gold. No se ha cargado ningún dato real en Snowflake.

## Ejecutar desde cero

Requisitos: Git, Python 3.12, acceso HTTPS a NYC TLC/PyPI y, para `load`, una cuenta
Snowflake y un rol con permisos sobre los objetos del laboratorio. Ejecutar desde
la raíz del repositorio:

```powershell
git switch lab/semana-07-nyc-taxi
cd laboratorios/semana-07/nyc-yellow-taxi-elt
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

En Linux/macOS usar `.venv/bin/python` en lugar de `.venv/Scripts/python.exe`.
Las versiones del lock corresponden al entorno validado Python 3.12 en Windows;
verificar compatibilidad al cambiar de plataforma.

### 1. Verificar publicación (sin credenciales ni descarga de Parquet)

```powershell
.venv/Scripts/python.exe -m ingestion.pipeline verify
$LASTEXITCODE
```

Genera `reports/availability.json`, `reports/verify.json` y un reporte con ID en
`reports/runs/`. Esperado en la fecha de revisión: 19/20, `INCOMPLETE`, código 2.
Los reportes de ejecución están ignorados por Git; el inventario histórico en
`docs/` no se sobrescribe al ejecutar. HEAD usa GET Range como alternativa cuando
HEAD no está permitido; no se lee el cuerpo en esa comprobación.

### 2. Descargar y validar originales

```powershell
.venv/Scripts/python.exe -m ingestion.pipeline download
```

Procesa los meses publicados aun si falta agosto. Descarga de nuevo para detectar
revisiones, valida longitud y decodifica Parquet por lotes; exige columnas mínimas
pero conserva los valores originales. Guarda bajo `data/<sha256>/` y elimina
archivos parciales ante error. No se usa una descarga local como evidencia de carga.

### 3. Preparar Snowflake

Ejecutar `infrastructure/bootstrap.sql` en una worksheet de Snowsight con el rol
seleccionado. Crea warehouse XSMALL con suspensión automática, base NYC_TAXI,
esquemas RAW/BRONZE/SILVER/GOLD, stage y tablas de control. Ejecutar el bootstrap
sin concurrencia. No reemplaza tablas existentes ni incluye usuarios/contraseñas.

Completar `.env` con cuenta, usuario y rol. El rol de ejecución necesita USAGE en
warehouse/base/esquema, READ/WRITE sobre el stage, SELECT/INSERT/DELETE en las tablas,
UPDATE en el mutex y CREATE TABLE en RAW para las temporales. Para este laboratorio
puede utilizarse el mismo rol propietario del bootstrap. La autenticación por
defecto es `externalbrowser`; las variables de entorno prevalecen sobre `.env`.

### 4. Cargar originales

```powershell
.venv/Scripts/python.exe -m ingestion.pipeline load
```

Incluye verificación y descarga. PUT preserva el Parquet original en stage;
COPY carga cada fila en VARIANT con su número físico. El conteo debe coincidir
con PyArrow. El reemplazo mensual y el manifiesto se confirman en una única
transacción, protegida por un mutex común. Una repetición idéntica no añade filas;
una revisión del origen reemplaza el mes completo y conserva versiones en stage.

Los duplicados que ya vienen del origen permanecen en RAW. No se confunden con
los duplicados por reejecución: Silver tratará los primeros con reglas documentadas.

Códigos de salida: 0 = etapa completa; 2 = cobertura incompleta; 1 = error técnico.
`pipeline_status` permanece `INCOMPLETE` hasta implementar y validar dbt, incluso
si una etapa llega a 20/20. No se declara SUCCESS global en esta versión.

### 5. Pruebas locales

```powershell
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Incluyen un Parquet sintético temporal, truncamiento, esquema inválido, archivo
vacío, repetición de descarga, cobertura incompleta y protocolo transaccional.
Las pruebas del cargador usan un cursor simulado: no certifican integración o
concurrencia en Snowflake. No requieren credenciales ni datos reales.

### 6. Próximas etapas

1. Integración Snowflake: cargar un mes, repetirlo, comprobar conteos y probar
   rollback/revisión de archivo/concurrencia contra el servicio real.
2. dbt Bronze: proyección próxima al origen con archivo, período, fila y carga.
3. Silver: tipos, nulos, duplicados y registros inválidos; conservar rechazos y
   reconciliar conteos según `docs/design.md`.
4. Gold: hecho de viajes y dimensiones fecha, zona, proveedor, pago y tarifa.
5. dbt `not_null`, `unique`, `relationships`, pruebas de reglas/reconciliación y
   `dbt build`. Publicar métricas con cobertura explícita; aprobar la entrega
   únicamente con los 20 meses cargados y todas las pruebas aprobadas.

## Estructura y operación

`ingestion/`: CLI y cargador; `infrastructure/`: bootstrap SQL; `dbt_project/`:
estructura reservada; `tests/`: pruebas; `docs/`: decisiones y evidencia;
`diagrams/`: Mermaid. `requirements.txt` define dependencias directas y
`requirements.lock.txt` fija el entorno completo validado.

Un proceso terminado abruptamente puede dejar `data/pipeline.lock`: verificar
que ya no existe un proceso activo antes de retirar ese archivo. Nunca iniciar
escritores que omitan el mutex de Snowflake. Los fallos se reportan por clase de
excepción para evitar registrar credenciales. Mantener los reportes locales de
cada ejecución para auditar intentos; LOAD_MANIFEST es la autoridad de cargas.

## Higiene Git

No versionar `.env`, perfiles locales, credenciales, Parquet, `data/`, `reports/`,
`.venv/`, volúmenes o artefactos dbt. `.gitignore` no protege archivos ya rastreados.
Antes de preparar un commit, revisar solo las rutas de este proyecto:

```powershell
git status --short -- .
git diff --check -- .
git diff -- .
git diff --cached -- .
git check-ignore .env data/example.parquet dbt_project/profiles.yml
```
