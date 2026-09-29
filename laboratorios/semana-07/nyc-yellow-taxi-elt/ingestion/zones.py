"""Official lookup is auxiliary: it never counts as one of the 20 trip files."""
import csv
import hashlib
import io
from ingestion.pipeline import request, write_json

URL = 'https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv'


def download_zones(directory):
    with request(URL) as response:
        content = response.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise ValueError('Zone catalog unexpectedly large')
    reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
    if reader.fieldnames != ['LocationID', 'Borough', 'Zone', 'service_zone']:
        raise ValueError('Unexpected zone catalog schema')
    rows = [(int(r['LocationID']), r['Borough'].strip(), r['Zone'].strip(),
             r['service_zone'].strip()) for r in reader]
    ids = [r[0] for r in rows]
    if not ids or len(ids) != len(set(ids)) or min(ids) <= 0 or any(not r[2] for r in rows):
        raise ValueError('Invalid or duplicated zone identity')
    checksum = hashlib.sha256(content).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'zones-{checksum}.csv'
    path.write_bytes(content)
    metadata = dict(url=URL, path=str(path), sha256=checksum, rows=len(rows))
    write_json(directory / 'zones.json', metadata)
    return metadata


def load_zones(connection, metadata):
    from pathlib import Path
    content = Path(metadata['path']).read_bytes()
    if hashlib.sha256(content).hexdigest() != metadata['sha256']:
        raise ValueError('Zone checksum mismatch')
    rows = [(int(r['LocationID']), r['Borough'], r['Zone'], r['service_zone'], metadata['sha256'])
            for r in csv.DictReader(io.StringIO(content.decode('utf-8-sig')))]
    if len(rows) != metadata['rows'] or len({r[0] for r in rows}) != len(rows):
        raise ValueError('Zone row count mismatch')
    with connection.cursor() as cursor:
        cursor.execute('BEGIN TRANSACTION')
        try:
            cursor.execute('UPDATE INGESTION_MUTEX SET TOKEN=TOKEN+1 WHERE ID=1')
            if cursor.rowcount != 1:
                raise ValueError('Expected one mutex')
            count = cursor.execute('SELECT COUNT(*) FROM TAXI_ZONES WHERE SOURCE_SHA256=%s',
                                   (metadata['sha256'],)).fetchone()[0]
            total = cursor.execute('SELECT COUNT(*) FROM TAXI_ZONES').fetchone()[0]
            if count != total or count != len(rows):
                cursor.execute('DELETE FROM TAXI_ZONES')
                cursor.executemany('''INSERT INTO TAXI_ZONES
                    (LOCATION_ID, BOROUGH, ZONE, SERVICE_ZONE, SOURCE_SHA256, LOADED_AT)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP())''', rows)
            cursor.execute('COMMIT')
        except BaseException:
            cursor.execute('ROLLBACK')
            raise
