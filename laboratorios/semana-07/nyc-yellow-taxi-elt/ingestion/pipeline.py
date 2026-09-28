"""Run from project root: python -m ingestion.pipeline verify|download|load."""
import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = 'https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page'
BASE = 'https://d37ci6vzurychx.cloudfront.net/trip-data'
MONTHS = tuple([f'2025-{m:02}' for m in range(1, 13)] +
               [f'2026-{m:02}' for m in range(1, 9)])


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.urls.update(value for key, value in attrs if key == 'href' and value)


def request(url, method='GET', headers=None):
    """Bounded retry for transient failures; never retry an unavailable month forever."""
    for attempt in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(
                url, method=method, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; NYC-Taxi-Lab/1.0)',
                    **(headers or {})}), timeout=30)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
        time.sleep(2 ** attempt)


def classify(listed, code):
    # Absence from a successfully retrieved official listing is publication pending.
    # The independent HTTP code is retained: 403 is NOT evidence of nonexistence.
    if listed is None:
        return 'check_failed'
    if not listed:
        return 'pending_publication'
    if code in (200, 206):
        return 'available'
    if code == 404:
        return 'pending_publication'
    return 'check_failed'


def verify():
    page_error = None
    try:
        with request(PAGE) as response:
            parser = Links()
            parser.feed(response.read().decode('utf-8'))
        # Reject unexpected/error HTML instead of classifying all months as pending.
        if not any('yellow_tripdata_' in link for link in parser.urls):
            raise ValueError('Official page contains no Yellow Taxi links')
        links = parser.urls
    except Exception as exc:
        links, page_error = None, type(exc).__name__
    rows = []
    for month in MONTHS:
        url = f'{BASE}/yellow_tripdata_{month}.parquet'
        row = dict(month=month, url=url, checked_at=now(),
                   listed=None if links is None else url in links,
                   http_status=None, size=None, etag=None, last_modified=None)
        if page_error:
            row['page_error'] = page_error
        try:
            try:
                response = request(url, 'HEAD')
            except urllib.error.HTTPError as exc:
                if exc.code not in (405, 501):
                    raise
                response = request(url, headers={'Range': 'bytes=0-3'})
            # No response body is read, even if a server ignores Range.
            with response:
                row['http_status'] = response.status
                row['size'] = (response.headers.get('Content-Range', '').split('/')[-1]
                               if response.status == 206 else response.headers.get('Content-Length'))
                row['etag'] = response.headers.get('ETag')
                row['last_modified'] = response.headers.get('Last-Modified')
        except urllib.error.HTTPError as exc:
            row['http_status'] = exc.code
        except Exception as exc:
            row['error'] = type(exc).__name__
        row['availability'] = classify(row['listed'], row['http_status'])
        rows.append(row)
    return rows


def validate_parquet(path):
    import pyarrow.parquet as pq
    required = {'tpep_pickup_datetime', 'tpep_dropoff_datetime', 'PULocationID',
                'DOLocationID', 'trip_distance', 'total_amount', 'cbd_congestion_fee'}
    # Explicitly own the handle: even a constructor failure must release it on Windows.
    with path.open('rb') as source:
        parquet = pq.ParquetFile(source)
        if not required.issubset(parquet.schema_arrow.names):
            raise ValueError('Missing required source columns')
        count = sum(batch.num_rows for batch in parquet.iter_batches(batch_size=65536))
        if count == 0 or count != parquet.metadata.num_rows:
            raise ValueError('Empty or inconsistent Parquet')
    return count


def download(row, directory):
    """Always recheck source content; ETag is not treated as a content checksum."""
    directory.mkdir(parents=True, exist_ok=True)
    temporary = directory / f"{row['month']}.partial"
    digest = hashlib.sha256()
    size = 0
    try:
        with request(row['url']) as response, temporary.open('wb') as output:
            if response.status != 200:
                raise ValueError('Full download must return HTTP 200')
            expected_size = response.headers.get('Content-Length')
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
        if expected_size and size != int(expected_size):
            raise ValueError('Truncated download')
        count = validate_parquet(temporary)
        checksum = digest.hexdigest()
        target = directory / checksum / f"yellow_tripdata_{row['month']}.parquet"
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.replace(target)
        return dict(path=str(target), sha256=checksum, rows=count, bytes=size)
    finally:
        temporary.unlink(missing_ok=True)


def summarize(rows, phase):
    if len(rows) != 20 or {r['month'] for r in rows} != set(MONTHS):
        raise ValueError('Expected exactly the 20 contracted months')
    failed = any(r['availability'] == 'check_failed' or
                 r.get('operation') == 'failed' for r in rows)
    field = {'verify': 'available', 'download': 'downloaded', 'load': 'loaded'}[phase]
    complete = sum((r['availability'] == field if phase == 'verify' else
                    r.get('operation') == field) for r in rows)
    # These are stage outcomes, never the final ELT/dbt acceptance status.
    status = 'FAILED' if failed else ('COMPLETE' if complete == 20 else 'INCOMPLETE')
    return dict(phase=phase, status=status, completed=complete, expected=20,
                pipeline_status='FAILED' if failed else 'INCOMPLETE', checked_at=now(), files=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('verify', 'download', 'load'))
    args = parser.parse_args()
    # Download/load need external dependencies; verification and tests use stdlib.
    if args.phase != 'verify':
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
    data = ROOT / 'data'
    data.mkdir(exist_ok=True)
    lock = data / 'pipeline.lock'
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        parser.exit(1, 'Another run or stale data/pipeline.lock exists; inspect before retrying.\n')
    os.close(descriptor)
    connection = None
    rows = []
    run_id = uuid.uuid4().hex

    def save(result):
        result['run_id'] = run_id
        write_json(ROOT / 'reports' / 'runs' / f'{run_id}.json', result)
        write_json(ROOT / 'reports' / f'{args.phase}.json', result)

    try:
        rows = verify()
        for row in rows:
            row['operation'] = 'not_started'
        write_json(ROOT / 'reports' / 'availability.json', rows)
        save(summarize(rows, args.phase))
        if args.phase == 'load' and any(r['availability'] == 'available' for r in rows):
            from ingestion.snowflake_loader import connect
            connection = connect()
        for row in rows:
            if args.phase == 'verify' or row['availability'] != 'available':
                continue
            try:
                row['operation'] = 'running'
                save(summarize(rows, args.phase))
                row.update(download(row, data))
                row['operation'] = 'downloaded'
                if args.phase == 'load':
                    from ingestion.snowflake_loader import load_month
                    row['load_action'] = load_month(connection, row)
                    row['operation'] = 'loaded'
            except Exception as exc:
                # Do not serialize connector messages: they may contain account details.
                row['operation'], row['error'] = 'failed', type(exc).__name__
            save(summarize(rows, args.phase))
        result = summarize(rows, args.phase)
        save(result)
        print(json.dumps({k: v for k, v in result.items() if k != 'files'}))
        return {'COMPLETE': 0, 'INCOMPLETE': 2, 'FAILED': 1}[result['status']]
    except Exception as exc:
        result = dict(phase=args.phase, status='FAILED', pipeline_status='FAILED',
                      error=type(exc).__name__, expected=20, files=rows, checked_at=now())
        save(result)
        print(json.dumps({k: v for k, v in result.items() if k != 'files'}))
        return 1
    finally:
        try:
            if connection:
                connection.close()
        finally:
            lock.unlink(missing_ok=True)


if __name__ == '__main__':
    raise SystemExit(main())
