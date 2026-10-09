import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.server.__main__ import roles


class AnalystRoleTests(unittest.TestCase):
    def test_analyst_can_read_signal_context_without_mutating_signals(self):
        statements = []
        database = MagicMock()
        connection = database.engine.begin.return_value.__enter__.return_value
        cursor = connection.connection.driver_connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        cursor.execute.side_effect = lambda statement, *args: statements.append(
            statement.as_string() if hasattr(statement, 'as_string') else statement
        )
        with patch('apps.server.__main__.secret_file', return_value='synthetic-test-password'):
            roles(database, Path('/synthetic-role-secrets'))
        self.assertIn('GRANT SELECT ON TABLE "signals" TO "scanner_codex"', statements)
        self.assertNotIn('GRANT INSERT, UPDATE, DELETE ON TABLE "signals" TO "scanner_codex"', statements)
        self.assertIn('GRANT INSERT, UPDATE, DELETE ON TABLE "signals" TO "scanner_scanner"', statements)
        self.assertIn('GRANT SELECT ON TABLE "imports" TO "scanner_codex"', statements)
        self.assertNotIn('GRANT INSERT, UPDATE, DELETE ON TABLE "imports" TO "scanner_codex"', statements)
