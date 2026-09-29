import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from ingestion.pipeline import MONTHS, cached_download
from ingestion.workflow import acceptance, directory, require_predecessor
from ingestion import workflow


class AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.state = dict(selected_months=list(MONTHS),
            files=[dict(month=m, availability='available', operation='loaded') for m in MONTHS],
            dbt_test=dict(returncode=0, nodes=[dict(status='pass')]))
        self.coverage = [dict(SOURCE_MONTH=m, LOAD_STATUS='LOADED') for m in MONTHS]

    def test_success_requires_twenty_and_passing_tests(self):
        self.assertEqual(acceptance(self.state, self.coverage), 'SUCCESS')
        for field in ('files', 'dbt_test'):
            state = copy.deepcopy(self.state)
            if field == 'files':
                state['files'][-1]['operation'] = 'downloaded'
            else:
                state['dbt_test']['nodes'][0]['status'] = 'warn'
            self.assertEqual(acceptance(state, self.coverage), 'INCOMPLETE' if field == 'files' else 'FAILED')

    def test_missing_august_is_incomplete_even_with_passing_dbt(self):
        self.state['files'][-1].update(availability='pending_publication', operation='not_started')
        self.coverage[-1]['LOAD_STATUS'] = 'NOT_LOADED'
        self.assertEqual(acceptance(self.state, self.coverage), 'INCOMPLETE')

    def test_failure_is_not_hidden_by_previous_loaded_data(self):
        self.state['files'][0]['operation'] = 'failed'
        self.assertEqual(acceptance(self.state, self.coverage), 'FAILED')

    def test_stage_order_and_run_id_are_enforced(self):
        with self.assertRaises(ValueError):
            require_predecessor({'completed_phases': ['inventory']}, 'dbt-run')
        for invalid in ('../escape', 'x;command', '', '/absolute'):
            with self.assertRaises(ValueError):
                directory(invalid)


class CacheTests(unittest.TestCase):
    def test_corrupt_cache_falls_back_to_new_validated_download(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index').mkdir()
            row = dict(month='2025-01', url='https://example.test/file', etag='tag', last_modified='date', size=4)
            (root / 'index/2025-01.json').write_text(json.dumps(row))
            fresh = dict(path='valid.parquet', sha256='a' * 64, rows=2, bytes=4)
            with patch('ingestion.pipeline.verify_local_file', side_effect=ValueError('corrupt')), \
                 patch('ingestion.pipeline.download', return_value=fresh) as fetch:
                self.assertEqual(cached_download(row, root), fresh)
                fetch.assert_called_once()

    def test_matching_metadata_still_requires_local_integrity_check(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'index').mkdir()
            row = dict(month='2025-01', url='https://example.test/file', etag='tag', last_modified='date', size=4)
            local = dict(path='valid.parquet', sha256='a' * 64, rows=2, bytes=4)
            (root / 'index/2025-01.json').write_text(json.dumps({**row, **local}))
            with patch('ingestion.pipeline.verify_local_file') as integrity, \
                 patch('ingestion.pipeline.download') as fetch:
                self.assertEqual(cached_download(row, root), local)
                integrity.assert_called_once()
                fetch.assert_not_called()


class StageIntegrationTests(unittest.TestCase):
    """Exercise the real stage state machine with only external services mocked."""

    def test_invalid_download_blocks_load_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(workflow, 'REPORTS', root / 'reports'), \
                 patch.object(workflow, 'DATA', root / 'data'), \
                 patch.object(workflow, 'verify', return_value=[dict(month='2025-01', availability='available')]), \
                 patch.object(workflow, 'connect', return_value=MagicMock()), \
                 patch.object(workflow, 'connection_identity', return_value='connection-hash'), \
                 patch.object(workflow, 'cached_download', side_effect=ValueError('truncated Parquet')), \
                 patch.object(workflow, 'load_month') as loader:
                self.assertEqual(workflow.stage('inventory', 'invalid'), 0)
                self.assertEqual(workflow.stage('download', 'invalid'), 1)
                self.assertNotIn('download', workflow.load_state('invalid')['completed_phases'])
                self.assertEqual(workflow.stage('load', 'invalid'), 1)
                self.assertEqual(workflow.load_state('invalid')['status'], 'FAILED')
                loader.assert_not_called()

    def test_pilot_reports_incomplete_then_comparison_unlocks_bulk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = [dict(month=m, availability='available' if m != '2026-08' else 'pending_publication')
                         for m in MONTHS]
            coverage = [dict(SOURCE_MONTH=m, LOAD_STATUS='LOADED' if m == '2025-01' else 'NOT_LOADED')
                        for m in MONTHS]
            observed = dict(coverage=coverage, layers={'raw': [{'ROW_COUNT': 2}]},
                            dimensions={'DIM_ZONE': [{'ROW_COUNT': 266}]}, gold_example=[])
            with patch.object(workflow, 'REPORTS', root / 'reports'), \
                 patch.object(workflow, 'DATA', root / 'data'), \
                 patch.object(workflow, 'verify', side_effect=lambda: copy.deepcopy(inventory)), \
                 patch.object(workflow, 'connection_identity', return_value='connection-hash'), \
                 patch.object(workflow, 'connect', return_value=MagicMock()), \
                 patch.object(workflow, 'cached_download', return_value={'rows': 2, 'sha256': 'a' * 64}), \
                 patch.object(workflow, 'download_zones', return_value={'rows': 265}), \
                 patch.object(workflow, 'load_zones'), \
                 patch.object(workflow, 'load_month', side_effect=['inserted', 'unchanged']), \
                 patch.object(workflow, 'invoke', return_value={'returncode': 0, 'nodes': [{'status': 'pass'}]}), \
                 patch.object(workflow, 'evidence', return_value=observed):
                for run_id in ('pilot-a', 'pilot-b'):
                    for phase in workflow.PHASES:
                        self.assertEqual(workflow.stage(phase, run_id), 2 if phase == 'report' else 0)
                workflow.compare('pilot-b', 'pilot-a')
                self.assertTrue((root / 'reports/pilot_verified.json').exists())
                self.assertEqual(workflow.load_state('pilot-b')['status'], 'INCOMPLETE')

    def test_bulk_download_requires_pilot_before_fetching_any_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(workflow, 'REPORTS', root / 'reports'), \
                 patch.object(workflow, 'DATA', root / 'data'), \
                 patch.object(workflow, 'verify', return_value=[dict(month=m, availability='available') for m in MONTHS]), \
                 patch.object(workflow, 'connection_identity', return_value='connection-hash'), \
                 patch.object(workflow, 'connect', return_value=MagicMock()), \
                 patch.object(workflow, 'cached_download') as fetch:
                self.assertEqual(workflow.stage('inventory', 'bulk', month='all'), 0)
                self.assertEqual(workflow.stage('download', 'bulk'), 1)
                fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
