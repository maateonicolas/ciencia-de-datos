import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ingestion.pipeline import MONTHS, classify, download, summarize, validate_parquet


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, size=None):
        super().__init__(body)
        self.headers = {'Content-Length': str(len(body) if size is None else size)}


class CoverageTests(unittest.TestCase):
    def rows(self):
        return [dict(month=m, availability='available', operation='loaded') for m in MONTHS]

    def test_missing_august_never_succeeds(self):
        rows = self.rows()
        rows[-1].update(availability='pending_publication', operation='not_started')
        result = summarize(rows, 'load')
        self.assertEqual((result['status'], result['completed'], result['expected']),
                         ('INCOMPLETE', 19, 20))
        rows[-1].update(availability='available', operation='loaded')
        result = summarize(rows, 'load')
        self.assertEqual(result['status'], 'COMPLETE')
        self.assertEqual(result['pipeline_status'], 'INCOMPLETE')  # dbt not yet run

    def test_errors_are_not_pending_or_success(self):
        self.assertEqual(classify(True, 403), 'check_failed')
        self.assertEqual(classify(None, 200), 'check_failed')
        self.assertEqual(classify(False, 403), 'pending_publication')
        rows = self.rows()
        rows[0]['operation'] = 'failed'
        self.assertEqual(summarize(rows, 'load')['status'], 'FAILED')

    def test_denominator_cannot_shrink(self):
        with self.assertRaises(ValueError):
            summarize(self.rows()[:-1], 'load')


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.row = dict(month='2025-01', url='https://example.test/file.parquet')

    def test_truncated_response_is_not_published(self):
        with patch('ingestion.pipeline.request', return_value=Response(b'PAR1', 100)):
            with self.assertRaisesRegex(ValueError, 'Truncated'):
                download(self.row, self.directory)
        self.assertEqual(list(self.directory.rglob('*')), [])

    def test_invalid_parquet_is_not_published(self):
        with patch('ingestion.pipeline.request', return_value=Response(b'not parquet')):
            with self.assertRaises(Exception):
                download(self.row, self.directory)
        self.assertFalse(list(self.directory.rglob('*.parquet')))
        self.assertFalse(list(self.directory.rglob('*.partial')))

    def test_real_parquet_validation_and_repeat_download(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        columns = ['tpep_pickup_datetime', 'tpep_dropoff_datetime', 'PULocationID',
                   'DOLocationID', 'trip_distance', 'total_amount', 'cbd_congestion_fee']
        source = self.directory / 'fixture.parquet'
        pq.write_table(pa.table({name: [1, 2] for name in columns}), source)
        self.assertEqual(validate_parquet(source), 2)
        body = source.read_bytes()
        source.unlink()
        results = []
        for _ in range(2):
            with patch('ingestion.pipeline.request', return_value=Response(body)):
                results.append(download(self.row, self.directory))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(list(self.directory.rglob('*.parquet'))), 1)

    def test_missing_columns_and_zero_rows_rejected(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        target = self.directory / 'fixture.parquet'
        pq.write_table(pa.table({'unrelated': [1]}), target)
        with self.assertRaisesRegex(ValueError, 'Missing'):
            validate_parquet(target)
        names = ['tpep_pickup_datetime', 'tpep_dropoff_datetime', 'PULocationID',
                 'DOLocationID', 'trip_distance', 'total_amount', 'cbd_congestion_fee']
        pq.write_table(pa.table({name: pa.array([], type=pa.int64()) for name in names}), target)
        with self.assertRaisesRegex(ValueError, 'Empty'):
            validate_parquet(target)


if __name__ == '__main__':
    unittest.main()
