"""Original rows in VARIANT plus source lineage; atomic monthly replacement."""
import os
import re
import uuid
from pathlib import Path


def connect():
    import snowflake.connector
    required = ('ACCOUNT', 'USER', 'WAREHOUSE', 'DATABASE', 'ROLE')
    settings = {key.lower(): os.environ[f'SNOWFLAKE_{key}'] for key in required}
    settings['authenticator'] = os.getenv('SNOWFLAKE_AUTHENTICATOR', 'externalbrowser')
    if settings['authenticator'] == 'snowflake':
        settings['password'] = os.environ['SNOWFLAKE_PASSWORD']
    return snowflake.connector.connect(**settings, schema='RAW', autocommit=True)


def load_month(connection, row):
    month, checksum = row['month'], row['sha256']
    if not re.fullmatch(r'20\d{2}-\d{2}', month) or not re.fullmatch(r'[a-f0-9]{64}', checksum):
        raise ValueError('Invalid month/checksum')
    filename = f'yellow_tripdata_{month}.parquet'
    file_uri = Path(row['path']).resolve().as_uri().replace("'", "''")
    stage_path = f'@TAXI_PARQUET/{month}/{checksum}'
    temporary = f'BATCH_{uuid.uuid4().hex.upper()}'
    with connection.cursor() as cursor:
        # DDL and PUT are deliberately outside the transaction.
        cursor.execute(f"PUT '{file_uri}' {stage_path} AUTO_COMPRESS=FALSE OVERWRITE=TRUE")
        cursor.execute(f'CREATE TEMPORARY TABLE {temporary} (PAYLOAD VARIANT, SOURCE_ROW NUMBER)')
        cursor.execute(f"""COPY INTO {temporary} FROM (
            SELECT $1, METADATA$FILE_ROW_NUMBER FROM {stage_path}/
        ) FILES=('{filename}') FILE_FORMAT=(TYPE=PARQUET)
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
                'SELECT COUNT(*) FROM YELLOW_TRIPS WHERE SOURCE_MONTH=%s AND SOURCE_SHA256=%s',
                (month, checksum)).fetchone()[0]
            total = cursor.execute('SELECT COUNT(*) FROM YELLOW_TRIPS WHERE SOURCE_MONTH=%s',
                                   (month,)).fetchone()[0]
            if previous == [(checksum, row['rows'])] and count == total == row['rows']:
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
