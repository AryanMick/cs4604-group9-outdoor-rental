"""Tests for adding bikes to selected sample businesses."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import add_mountain_bikes
import db_tools


class MountainBikeTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchall.side_effect = [
            [(index, address)] for index, address in enumerate(add_mountain_bikes.SHOPS.values(), 1)
        ]
        connect = patch.object(db_tools, "connect", return_value=self.connection)
        connect.start()
        self.addCleanup(connect.stop)

    def test_selected_shops_are_checked_before_inserting(self):
        self.cursor.rowcount = 4
        self.assertEqual(add_mountain_bikes.main(), 0)
        self.assertEqual(self.cursor.execute.call_count, 5)
        self.connection.commit.assert_called_once()
        self.connection.rollback.assert_not_called()
        self.connection.close.assert_called_once()

    def test_missing_or_conflicting_shop_rolls_back(self):
        for rows in ([], [(1, "Different address")], [(1, "a"), (2, "a")]):
            with self.subTest(rows=rows):
                self.connection.reset_mock()
                self.cursor.fetchall.side_effect = [rows]
                with self.assertRaisesRegex(RuntimeError, "Expected exactly one sample business"):
                    add_mountain_bikes.main()
                self.assertEqual(self.cursor.execute.call_count, 1)
                self.connection.rollback.assert_called_once()
                self.connection.commit.assert_not_called()
                self.connection.close.assert_called_once()

    def test_database_failure_rolls_back(self):
        self.cursor.execute.side_effect = pymysql.OperationalError(2003, "unavailable")
        with self.assertRaises(pymysql.MySQLError):
            add_mountain_bikes.main()
        self.connection.rollback.assert_called_once()
        self.connection.commit.assert_not_called()
        self.connection.close.assert_called_once()

    def test_seed_uses_existing_image_and_four_shops(self):
        sql = "\n".join(db_tools.sql_statements("05_mountain_bike_data.sql"))
        for name, address in add_mountain_bikes.SHOPS.items():
            self.assertIn(name, sql)
            self.assertIn(address, sql)
        self.assertIn("img/mountainBike.jpg", sql)
        self.assertTrue((db_tools.PACKAGE / "static" / "img" / "mountainBike.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
