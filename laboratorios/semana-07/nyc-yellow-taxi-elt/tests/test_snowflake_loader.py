"""SQL protocol tests with a fake cursor; these do not replace Snowflake integration."""
import unittest
from unittest.mock import MagicMock
from ingestion.snowflake_loader import load_month


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.execute.return_value = self.cursor
        self.cursor.rowcount = 1
        self.cursor.fetchone.side_effect = [(2, 2), (0,), (0,)]
        self.cursor.fetchall.return_value = []
        self.row = dict(month='2025-01', sha256='a' * 64, rows=2, path='fixture.parquet')

    def sql(self):
        return [call.args[0] for call in self.cursor.execute.call_args_list]

    def test_identical_month_is_not_inserted(self):
        self.cursor.fetchone.side_effect = [(2, 2), (2,), (2,)]
        self.cursor.fetchall.return_value = [('a' * 64, 2)]
        self.assertEqual(load_month(self.connection, self.row), 'unchanged')
        self.assertFalse(any(sql.startswith('INSERT') for sql in self.sql()))

    def test_changed_month_replaces_in_one_transaction(self):
        self.cursor.fetchall.return_value = [('b' * 64, 2)]
        self.assertEqual(load_month(self.connection, self.row), 'replaced')
        statements = self.sql()
        begin, commit = statements.index('BEGIN TRANSACTION'), statements.index('COMMIT')
        inside = statements[begin + 1:commit]
        self.assertTrue(any(sql.startswith('DELETE FROM YELLOW_TRIPS') for sql in inside))
        self.assertTrue(any(sql.startswith('INSERT INTO YELLOW_TRIPS') for sql in inside))
        self.assertFalse(any(sql.startswith(('CREATE', 'DROP', 'PUT')) for sql in inside))

    def test_insert_failure_rolls_back_instead_of_committing(self):
        def execute(sql, *args):
            if sql.startswith('INSERT INTO YELLOW_TRIPS'):
                raise RuntimeError('injected failure')
            return self.cursor
        self.cursor.execute.side_effect = execute
        with self.assertRaises(RuntimeError):
            load_month(self.connection, self.row)
        self.assertIn('ROLLBACK', self.sql())
        self.assertNotIn('COMMIT', self.sql())

    def test_copy_count_mismatch_cannot_replace_existing_month(self):
        self.cursor.fetchone.side_effect = [(1, 1)]
        with self.assertRaises(ValueError):
            load_month(self.connection, self.row)
        self.assertNotIn('BEGIN TRANSACTION', self.sql())


if __name__ == '__main__':
    unittest.main()
