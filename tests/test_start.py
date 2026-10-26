"""Verify that repeated launches preserve an existing project database."""
from unittest import TestCase
from unittest.mock import MagicMock, patch

import db_tools
import start


class StartupDatabaseTest(TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        for name, value in (
            ("load_config", {"database": "test_project"}),
            ("connect", self.connection),
            ("validate_server", "8.4.0"),
            ("setup", None),
        ):
            mock_patch = patch.object(db_tools, name, return_value=value)
            setattr(self, name, mock_patch.start())
            self.addCleanup(mock_patch.stop)

    def test_absent_or_empty_database_is_initialized(self):
        self.cursor.fetchall.return_value = []
        start.prepare_database(db_tools)
        self.setup.assert_called_once_with()
        self.connection.close.assert_called_once_with()

    def test_complete_database_is_preserved_without_reseeding(self):
        self.cursor.fetchall.return_value = [
            *((table, "BASE TABLE") for table in db_tools.TABLES),
            ("reservation_details", "VIEW"), ("employee_details", "VIEW"),
        ]
        start.prepare_database(db_tools)
        self.setup.assert_not_called()
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.connection.close.assert_called_once_with()

    def test_partial_database_is_rejected_without_changes(self):
        self.cursor.fetchall.return_value = [("customer", "BASE TABLE")]
        with self.assertRaisesRegex(RuntimeError, "No data was changed"):
            start.prepare_database(db_tools)
        self.setup.assert_not_called()
        self.assertEqual(self.cursor.execute.call_count, 1)
        self.connection.close.assert_called_once_with()
