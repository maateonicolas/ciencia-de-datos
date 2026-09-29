"""Stage CLI shared by Kestra and local runs; no secret values in stdout."""
import argparse
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from filelock import FileLock
from ingestion.pipeline import (ROOT, MONTHS, verify, cached_download, write_json, now)
from ingestion.snowflake_loader import connect, connection_settings, load_month
from ingestion.zones import download_zones, load_zones
from ingestion.dbt_runner import invoke

REPORTS = ROOT / 'reports' / 'executions'
DATA = ROOT / 'data'
PHASES = ('inventory', 'download', 'load', 'dbt-run', 'dbt-test', 'report')
LAYERS = {'raw': ('RAW.YELLOW_TRIPS', 'SOURCE_ROW'),
          'bronze': ('BRONZE.BRONZE_TRIPS', 'SOURCE_RECORD_KEY'),
          'silver': ('SILVER.SILVER_TRIPS', 'SOURCE_RECORD_KEY'),
          'rejected': ('SILVER.SILVER_REJECTED', 'SOURCE_RECORD_KEY'),
          'gold': ('GOLD.FACT_TRIPS', 'TRIP_KEY')}


def directory(run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', run_id):
        raise ValueError('Run ID must be alphanumeric, dash or underscore')
    return REPORTS / run_id


def load_state(run_id):
    return json.loads((directory(run_id) / 'state.json').read_text(encoding='utf-8'))


def save(state):
    write_json(directory(state['run_id']) / 'state.json', state)


def selected(state):
    return [r for r in state['files'] if r['month'] in state['selected_months']]


def acceptance(state, coverage):
    if state.get('error') or any(r.get('operation') == 'failed' for r in selected(state)):
        return 'FAILED'
    tests = state.get('dbt_test', {})
    if tests.get('returncode', 0) != 0 or any(node['status'] != 'pass' for node in tests.get('nodes', [])):
        return 'FAILED'
    tested = bool(tests.get('nodes')) and tests.get('returncode') == 0 and all(
        node['status'] == 'pass' for node in tests['nodes'])
    loaded = {r['SOURCE_MONTH'] for r in coverage if r['LOAD_STATUS'] == 'LOADED'}
    fresh = len(state['files']) == 20 and {r['month'] for r in state['files']} == set(MONTHS) and all(
        r['availability'] == 'available' and r.get('operation') == 'loaded' for r in state['files'])
    if tested and loaded == set(MONTHS) and len(coverage) == 20 and fresh:
        return 'SUCCESS'
    return 'INCOMPLETE'


def query(cursor, sql):
    cursor.execute(sql)
    keys = [col[0] for col in cursor.description]
    return [dict(zip(keys, row)) for row in cursor.fetchall()]


def evidence(connection):
    with connection.cursor() as cursor:
        coverage = query(cursor, 'SELECT * FROM GOLD.DATA_COVERAGE ORDER BY SOURCE_MONTH')
        layers = {}
        for name, (table, key) in LAYERS.items():
            # HASH_AGG is order independent; metadata timestamps excluded intentionally.
            expression = (f'HASH({key}, SOURCE_SHA256, PAYLOAD)' if name in ('raw', 'bronze') else
                          f'HASH({key}, SOURCE_SHA256, TOTAL_AMOUNT, TRIP_DISTANCE_MILES, PICKUP_AT, DROPOFF_AT)')
            layers[name] = query(cursor, f'SELECT SOURCE_MONTH, COUNT(*) AS ROW_COUNT, '
                                f'HASH_AGG({expression}) AS FINGERPRINT FROM {table} GROUP BY 1 ORDER BY 1')
        dimensions = {name: query(cursor, f'SELECT COUNT(*) AS ROW_COUNT, HASH_AGG(*) AS FINGERPRINT FROM GOLD.{name}')
                      for name in ('DIM_DATE', 'DIM_ZONE', 'DIM_VENDOR', 'DIM_PAYMENT', 'DIM_RATE')}
        example = query(cursor, """SELECT D.YEAR, D.MONTH, Z.BOROUGH, COUNT(*) AS TRIPS,
            SUM(F.TOTAL_AMOUNT) AS BILLED_AMOUNT, AVG(F.TRIP_DISTANCE_MILES) AS AVERAGE_MILES
            FROM GOLD.FACT_TRIPS F JOIN GOLD.DIM_DATE D ON F.PICKUP_DATE_KEY=D.DATE_KEY
            JOIN GOLD.DIM_ZONE Z ON F.PICKUP_ZONE_KEY=Z.ZONE_KEY
            GROUP BY 1,2,3 ORDER BY 1,2,3 LIMIT 20""")
    # Decimal/timestamps are serialized without float rounding.
    return json.loads(json.dumps(dict(coverage=coverage, layers=layers, dimensions=dimensions,
                                     gold_example=example), default=str))


def require_predecessor(state, phase):
    position = PHASES.index(phase)
    if position and PHASES[position - 1] not in state['completed_phases']:
        raise ValueError('Predecessor stage has not completed')


def connection_identity():
    settings = connection_settings()
    context = {k: settings[k] for k in ('account', 'user', 'role', 'database', 'warehouse')}
    return hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()


def load_isolated(row):
    # PUT/COPY may overlap, but load_month serializes committed replacements via mutex.
    connection = connect()
    try:
        return load_month(connection, row)
    finally:
        connection.close()


def stage(phase, run_id, month='2025-01', refresh=False, download_only=False):
    run_dir = directory(run_id)
    if phase == 'inventory':
        if (run_dir / 'state.json').exists():
            raise ValueError('Use a new run ID; previous evidence is immutable')
        if month != 'all' and month not in MONTHS:
            raise ValueError('Month outside the 20-month contract')
        state = dict(run_id=run_id, started_at=now(), month=month,
                     selected_months=list(MONTHS) if month == 'all' else [month],
                     completed_phases=[], files=verify(), status='INCOMPLETE')
        for row in state['files']:
            row['operation'] = 'not_started'
        save(state)
    else:
        state = load_state(run_id)
    try:
        require_predecessor(state, phase)
        if phase in state['completed_phases']:
            raise ValueError('Stage already completed; use a new run ID for repeat validation')
        if phase == 'inventory':
            if any(r['availability'] == 'check_failed' for r in state['files']):
                raise RuntimeError('Source inventory has technical errors')
        elif phase == 'download':
            # Check authentication BEFORE transferring a whole dataset in normal ELT mode.
            if not download_only:
                connection = connect()
                try:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT COUNT(*) FROM RAW.LOAD_MANIFEST')
                finally:
                    connection.close()
                state['connection_identity'] = connection_identity()
                if state['month'] == 'all':
                    pilot_path = REPORTS / 'pilot_verified.json'
                    if not pilot_path.exists():
                        raise ValueError('First validate and compare two one-month runs')
                    pilot = json.loads(pilot_path.read_text(encoding='utf-8'))
                    if pilot.get('connection_identity') != state['connection_identity']:
                        raise ValueError('Pilot belongs to a different Snowflake connection')
            downloads = [row for row in selected(state) if row['availability'] == 'available']
            for row in downloads:
                row['operation'] = 'downloading'
            save(state)
            # Each month owns its temporary/cache path; only the main thread writes state.
            with ThreadPoolExecutor(max_workers=4) as pool:
                pending = {pool.submit(cached_download, row, DATA, refresh): row for row in downloads}
                for future in as_completed(pending):
                    row = pending[future]
                    row.update(future.result())
                    row['operation'] = 'downloaded'
                    save(state)
                    print(json.dumps(dict(month=row['month'], operation='validated', rows=row['rows'])), flush=True)
            state['zones'] = download_zones(DATA / 'zones')
        elif phase == 'load':
            identity = connection_identity()
            if state.get('connection_identity', identity) != identity:
                raise ValueError('Snowflake connection changed between stages')
            state['connection_identity'] = identity
            batches = [row for row in selected(state) if row['availability'] == 'available']
            if any(row['operation'] != 'downloaded' for row in batches):
                raise ValueError('Cannot load an unvalidated file')
            with ThreadPoolExecutor(max_workers=4) as pool:
                pending = {pool.submit(load_isolated, row): row for row in batches}
                for future in as_completed(pending):
                    row = pending[future]
                    row['load_action'] = future.result()
                    row['operation'] = 'loaded'
                    save(state)
                    print(json.dumps(dict(month=row['month'], operation='loaded',
                                          action=row['load_action'], rows=row['rows'])), flush=True)
            connection = connect()
            try:
                load_zones(connection, state['zones'])
            finally:
                connection.close()
        elif phase == 'dbt-run':
            state['dbt_seed'] = invoke('seed', run_dir)
            state['dbt_run'] = invoke('run', run_dir)
        elif phase == 'dbt-test':
            state['dbt_test'] = invoke('test', run_dir)
        elif phase == 'report':
            connection = connect()
            try:
                state['evidence'] = evidence(connection)
            finally:
                connection.close()
            state['status'] = acceptance(state, state['evidence']['coverage'])
            state['finished_at'] = now()
        state['completed_phases'].append(phase)
        save(state)
        print(json.dumps(dict(phase=phase, run_id=run_id, business_status=state['status'],
                              selected_months=state['selected_months'])))
        if phase == 'report':
            print('::' + json.dumps({'outputs': {'business_status': state['status'],
                  'loaded_months': sum(r['LOAD_STATUS'] == 'LOADED' for r in state['evidence']['coverage']),
                  'expected_months': 20}}) + '::')
            return {'SUCCESS': 0, 'INCOMPLETE': 2, 'FAILED': 1}[state['status']]
        # Stage OK does not mean ELT success. Final report is the strict coverage gate.
        return 0
    except Exception as exc:
        state['status'], state['error'], state['failed_phase'] = 'FAILED', type(exc).__name__, phase
        state['error_code'] = getattr(exc, 'errno', None)
        state['sqlstate'] = getattr(exc, 'sqlstate', None)
        save(state)
        print(json.dumps(dict(phase=phase, business_status='FAILED', error=type(exc).__name__)))
        return 1


def compare(run_id, baseline):
    current, previous = load_state(run_id), load_state(baseline)
    for state in (current, previous):
        if 'report' not in state['completed_phases'] or state.get('error'):
            raise ValueError('Both runs must finish reporting and testing')
        if not state.get('dbt_test', {}).get('nodes') or any(
                r['status'] != 'pass' for r in state['dbt_test']['nodes']):
            raise ValueError('Both runs must pass dbt tests')
    if current['selected_months'] != previous['selected_months']:
        raise ValueError('Cannot compare different selected months')
    if not current.get('connection_identity') or current['connection_identity'] != previous.get('connection_identity'):
        raise ValueError('Cannot compare different Snowflake connections')
    # All loaded layers must have equal counts AND order-independent fingerprints.
    if current['evidence']['layers'] != previous['evidence']['layers']:
        raise ValueError('Repeat changed layer counts or fingerprints')
    if current['evidence']['coverage'] != previous['evidence']['coverage']:
        raise ValueError('Repeat changed monthly coverage')
    if current['evidence']['dimensions'] != previous['evidence']['dimensions']:
        raise ValueError('Repeat changed dimension contents')
    if current['evidence']['gold_example'] != previous['evidence']['gold_example']:
        raise ValueError('Repeat changed the analytical query result')
    active = [r for r in selected(current) if r['availability'] == 'available']
    if not active or any(r.get('load_action') != 'unchanged' for r in active):
        raise ValueError('Repeat did not preserve all selected source versions')
    result = dict(status='PASS', baseline=baseline, repeat=run_id,
                  checked_at=now(), selected_months=current['selected_months'],
                  connection_identity=current['connection_identity'])
    write_json(directory(run_id) / 'idempotency.json', result)
    if len(current['selected_months']) == 1:
        if any(r['LOAD_STATUS'] != 'LOADED' for r in current['evidence']['coverage']
               if r['SOURCE_MONTH'] in current['selected_months']):
            raise ValueError('Pilot month was not loaded')
        write_json(REPORTS / 'pilot_verified.json', result)
    print(json.dumps(result))


def bootstrap():
    import snowflake.connector
    settings = connection_settings()
    for key in ('database', 'warehouse'):
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', settings[key]):
            raise ValueError('Bootstrap requires simple unquoted database/warehouse identifiers')
    sql = (ROOT / 'infrastructure/bootstrap.sql').read_text(encoding='utf-8')
    names = {'NYC_TAXI_WH': settings['warehouse'], 'NYC_TAXI': settings['database']}
    sql = re.sub(r'\b(?:NYC_TAXI_WH|NYC_TAXI)\b', lambda match: names[match.group()], sql)
    settings.pop('database')
    settings.pop('warehouse')
    with snowflake.connector.connect(**settings, autocommit=True) as connection:
        for cursor in connection.execute_string(sql):
            cursor.close()
    print('Bootstrap completed')


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    load_dotenv(ROOT / '.env', override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=(*PHASES, 'run', 'compare', 'bootstrap', 'parse', 'failure', 'check-env'))
    parser.add_argument('--run-id', default='pilot')
    parser.add_argument('--month', default='2025-01', choices=(*MONTHS, 'all'))
    parser.add_argument('--baseline')
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--download-only', action='store_true',
                        help='Explicit local download validation without Snowflake; never marks loaded')
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    # OS-backed lock releases after crash; includes dbt and reporting, not just ingestion.
    with FileLock(str(DATA / 'workflow.lock'), timeout=0):
        try:
            if args.phase == 'check-env':
                try:
                    connection_settings()  # Normalize local lowercase aliases, if present.
                except (KeyError, ValueError):
                    pass
                required = ['ACCOUNT', 'USER', 'ROLE', 'DATABASE', 'WAREHOUSE']
                auth = os.getenv('SNOWFLAKE_AUTHENTICATOR', 'snowflake')
                required += ['PRIVATE_KEY_FILE'] if auth == 'snowflake_jwt' else (['PASSWORD'] if auth == 'snowflake' else [])
                missing = ['SNOWFLAKE_' + key for key in required if not os.getenv('SNOWFLAKE_' + key)]
                if missing:
                    print(json.dumps({'configuration': 'MISSING', 'variable_names': missing}))
                    return 1
                connection_settings()
                print('Required connection variables are present (values hidden)')
                return 0
            if args.phase == 'bootstrap':
                bootstrap()
                return 0
            if args.phase == 'parse':
                invoke('parse', directory(args.run_id), offline=True)
                return 0
            if args.phase == 'compare':
                compare(args.run_id, args.baseline)
                return 0
            if args.phase == 'failure':
                state = load_state(args.run_id)
                if 'report' not in state['completed_phases']:
                    state['status'] = 'FAILED'
                    save(state)
                print(json.dumps(dict(business_status=state['status'], run_id=args.run_id)))
                return 0
            if args.phase == 'run':
                for phase in PHASES:
                    code = stage(phase, args.run_id, args.month, args.refresh, args.download_only)
                    if code or (args.download_only and phase == 'download'):
                        return code
                return 0
            return stage(args.phase, args.run_id, args.month, args.refresh, args.download_only)
        except Exception as exc:
            print(json.dumps(dict(business_status='FAILED', error=type(exc).__name__)))
            return 1


if __name__ == '__main__':
    raise SystemExit(main())
