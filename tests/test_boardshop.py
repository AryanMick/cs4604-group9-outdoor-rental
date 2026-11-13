"""Tests for adding the sample boardshop to existing databases."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import add_boardshop
import db_tools


class BoardshopTests(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        self.cursor.fetchall.return_value = []
        connect = patch.object(db_tools, "connect", return_value=self.connection)
        connect.start()
        self.addCleanup(connect.stop)

    def test_new_and_existing_shop_use_same_seed_and_commit(self):
        for shops in ([], [(21, add_boardshop.SHOP_ADDRESS)]):
            with self.subTest(shops=shops):
                self.connection.reset_mock()
                self.cursor.fetchall.return_value = shops
                self.assertEqual(add_boardshop.main(), 0)
                self.assertEqual(self.cursor.execute.call_count, 3)
                self.connection.commit.assert_called_once()
                self.connection.rollback.assert_not_called()
                self.connection.close.assert_called_once()

    def test_conflicting_business_is_not_modified(self):
        for shops in ([(21, "Different address")], [(21, add_boardshop.SHOP_ADDRESS), (22, add_boardshop.SHOP_ADDRESS)]):
            with self.subTest(shops=shops):
                self.connection.reset_mock()
                self.cursor.fetchall.return_value = shops
                with self.assertRaisesRegex(RuntimeError, "different or duplicate"):
                    add_boardshop.main()
                self.assertEqual(self.cursor.execute.call_count, 1)
                self.connection.rollback.assert_called_once()
                self.connection.commit.assert_not_called()
                self.connection.close.assert_called_once()

    def test_database_failure_rolls_back(self):
        self.cursor.execute.side_effect = pymysql.OperationalError(2003, "unavailable")
        with self.assertRaises(pymysql.MySQLError):
            add_boardshop.main()
        self.connection.rollback.assert_called_once()
        self.connection.commit.assert_not_called()
        self.connection.close.assert_called_once()

    def test_seed_images_are_bundled(self):
        sql = "\n".join(db_tools.sql_statements("04_boardshop_data.sql"))
        for image in ("mountainBike.jpg", "skis.jpg", "snowboard.jpg", "snowHelmet.jpg"):
            self.assertIn("img/" + image, sql)
            self.assertTrue((db_tools.PACKAGE / "static" / "img" / image).is_file())


if __name__ == "__main__":
    unittest.main()
