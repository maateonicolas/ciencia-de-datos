"""Original rows in VARIANT plus source lineage; atomic monthly replacement."""
import os
import re
import uuid
from pathlib import Path
from ingestion.pipeline import MONTHS, verify_local_file


def connection_settings():
    # Accept the user's local lowercase Snowflake config without rewriting secrets.
    for key in ('ACCOUNT', 'USER', 'PASSWORD', 'ROLE', 'WAREHOUSE', 'DATABASE', 'AUTHENTICATOR'):
        if not os.getenv(f'SNOWFLAKE_{key}') and os.getenv(key.lower()):
            os.environ[f'SNOWFLAKE_{key}'] = os.environ[key.lower()]
    required = ('ACCOUNT', 'USER', 'WAREHOUSE', 'DATABASE', 'ROLE')
    missing = [f'SNOWFLAKE_{key}' for key in required if not os.getenv(f'SNOWFLAKE_{key}')]
    if missing:
        raise ValueError('Missing environment variable names: ' + ', '.join(missing))
    settings = {key.lower(): os.environ[f'SNOWFLAKE_{key}'] for key in required}
    settings['authenticator'] = os.getenv('SNOWFLAKE_AUTHENTICATOR', 'snowflake')
    if settings['authenticator'] == 'snowflake_jwt':
        settings['private_key_file'] = os.environ['SNOWFLAKE_PRIVATE_KEY_FILE']
        if os.getenv('SNOWFLAKE_PRIVATE_KEY_PASSPHRASE'):
            settings['private_key_file_pwd'] = os.environ['SNOWFLAKE_PRIVATE_KEY_PASSPHRASE']
    if settings['authenticator'] == 'snowflake':
        settings['password'] = os.environ['SNOWFLAKE_PASSWORD']
    return settings


def connect():
    import snowflake.connector
    return snowflake.connector.connect(**connection_settings(), schema='RAW', autocommit=True,
                                       login_timeout=30, network_timeout=120,
                                       session_parameters={'TIMEZONE': 'America/New_York',
                                                           'LOCK_TIMEOUT': 60})


def load_month(connection, row):
    month, checksum = row['month'], row['sha256']
    if month not in MONTHS or not re.fullmatch(r'[a-f0-9]{64}', checksum):
        raise ValueError('Invalid month/checksum')
    verify_local_file(row)
    filename = f'yellow_tripdata_{month}.parquet'
    # Snowflake PUT takes a file:// path, not percent-encoded path characters.
    file_uri = ('file://' + Path(row['path']).resolve().as_posix()).replace("'", "''")
    stage_path = f'@TAXI_PARQUET/{month}/{checksum}'
    temporary = f'BATCH_{uuid.uuid4().hex.upper()}'
    with connection.cursor() as cursor:
        # A single consistent read avoids re-uploading a confirmed identical month.
        existing = cursor.execute('''SELECT COUNT(*) FROM LOAD_MANIFEST m
            WHERE SOURCE_MONTH=%s AND SHA256=%s AND ROW_COUNT=%s
            AND (SELECT COUNT(*) FROM YELLOW_TRIPS WHERE SOURCE_MONTH=%s)=m.ROW_COUNT
            AND (SELECT COUNT(DISTINCT SOURCE_ROW) FROM YELLOW_TRIPS
                 WHERE SOURCE_MONTH=%s AND SOURCE_SHA256=%s)=m.ROW_COUNT''',
            (month, checksum, row['rows'], month, month, checksum)).fetchone()
        if existing == (1,):
            return 'unchanged'
        # DDL and PUT are deliberately outside the transaction.
        cursor.execute(f"PUT '{file_uri}' {stage_path} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        cursor.execute(f'CREATE TEMPORARY TABLE {temporary} (PAYLOAD VARIANT, SOURCE_ROW NUMBER)')
        cursor.execute(f"""COPY INTO {temporary} FROM (
            SELECT $1, METADATA$FILE_ROW_NUMBER FROM {stage_path}/
        ) FILES=('{filename}') FILE_FORMAT=(TYPE=PARQUET USE_LOGICAL_TYPE=TRUE)
          ON_ERROR=ABORT_STATEMENT FORCE=TRUE""")
        actual = cursor.execute(f'SELECT COUNT(*), COUNT(DISTINCT SOURCE_ROW) FROM {temporary}').fetchone()
        if actual != (row['rows'], row['rows']):
            raise ValueError('Snowflake row count/row identity mismatch')
        cursor.execute('BEGIN TRANSACTION')
        try:
            # Serializes all cooperating writers, including writers on other hosts.
            cursor.execute('UPDATE INGESTION_MUTEX SET TOKEN=TOKEN+1 WHERE ID=1')
            if cursor.rowcount != 1:
                raise ValueError('Infrastructure must contain exactly one mutex row')
            previous = cursor.execute(
                'SELECT SHA256, ROW_COUNT FROM LOAD_MANIFEST WHERE SOURCE_MONTH=%s', (month,)).fetchall()
            count = cursor.execute(
                'SELECT COUNT(*), COUNT(DISTINCT SOURCE_ROW) FROM YELLOW_TRIPS WHERE SOURCE_MONTH=%s AND SOURCE_SHA256=%s',
                (month, checksum)).fetchone()
            total = cursor.execute('SELECT COUNT(*) FROM YELLOW_TRIPS WHERE SOURCE_MONTH=%s',
                                   (month,)).fetchone()[0]
            if previous == [(checksum, row['rows'])] and count == (row['rows'], row['rows']) and total == row['rows']:
                cursor.execute('COMMIT')
                return 'unchanged'
            cursor.execute('DELETE FROM YELLOW_TRIPS WHERE SOURCE_MONTH=%s', (month,))
            cursor.execute(f"""INSERT INTO YELLOW_TRIPS
                (PAYLOAD, SOURCE_FILE, SOURCE_MONTH, SOURCE_SHA256, SOURCE_ROW, LOADED_AT)
                SELECT PAYLOAD, %s, %s, %s, SOURCE_ROW, CURRENT_TIMESTAMP() FROM {temporary}""",
                           (filename, month, checksum))
            cursor.execute('DELETE FROM LOAD_MANIFEST WHERE SOURCE_MONTH=%s', (month,))
            cursor.execute('''INSERT INTO LOAD_MANIFEST
                (SOURCE_MONTH, SHA256, ROW_COUNT, LOADED_AT) VALUES (%s, %s, %s, CURRENT_TIMESTAMP())''',
                           (month, checksum, row['rows']))
            cursor.execute('COMMIT')
            return 'replaced' if previous else 'inserted'
        except BaseException:
            cursor.execute('ROLLBACK')
            raise
        finally:
            cursor.execute(f'DROP TABLE IF EXISTS {temporary}')
