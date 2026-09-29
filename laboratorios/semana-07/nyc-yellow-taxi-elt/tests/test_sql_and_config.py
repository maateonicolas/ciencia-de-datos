"""Offline syntax/config checks, not Snowflake execution."""
import unittest
from pathlib import Path
import jinja2
import sqlglot
import yaml
from ingestion.pipeline import ROOT


class ModelTests(unittest.TestCase):
    def test_all_models_and_singular_tests_parse_as_snowflake(self):
        environment = jinja2.Environment()
        environment.globals.update(ref=lambda x: x, source=lambda a, b: f'{a}.{b}',
                                   config=lambda **kwargs: '')
        macros = (ROOT / 'dbt_project/macros/quality.sql').read_text()
        for path in list((ROOT / 'dbt_project/models').rglob('*.sql')) + list((ROOT / 'dbt_project/tests').glob('*.sql')):
            with self.subTest(path=path.name):
                sql = environment.from_string(macros + '\n' + path.read_text()).render()
                self.assertIsNotNone(sqlglot.parse_one(sql, read='snowflake'))

    def test_kestra_stages_match_workflow_and_do_not_interpolate_shell_inputs(self):
        flow = yaml.safe_load((ROOT / 'kestra/nyc-yellow-taxi.yml').read_text())
        self.assertEqual(flow['concurrency']['limit'], 1)
        self.assertEqual([t['id'] for t in flow['tasks']],
                         ['inventory', 'download', 'load', 'dbt_run', 'dbt_test', 'report'])
        for task in flow['tasks']:
            self.assertEqual(task['taskRunner']['type'], 'io.kestra.plugin.core.runner.Process')
            self.assertNotIn('{{', task['commands'][0])

    def test_compose_does_not_expose_postgres_or_mount_docker_socket(self):
        compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
        self.assertNotIn('ports', compose['services']['postgres'])
        for port in compose['services']['kestra']['ports']:
            self.assertTrue(port.startswith('127.0.0.1:'))
        self.assertNotIn('docker.sock', str(compose))


if __name__ == '__main__':
    unittest.main()
