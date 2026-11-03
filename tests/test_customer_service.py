"""Unit tests for the pure booking rules; no database is needed. Run: python -m unittest discover tests"""
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import customer_service as cs  # noqa: E402

NOW = datetime(2026, 11, 3, 12, 0)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute)


class PriceTests(unittest.TestCase):
    def test_day_rate_counts_whole_days(self):
        self.assertEqual(cs.calculate_price(Decimal("18.00"), "DAY", at(5, 9), at(8, 9)), Decimal("54.00"))

    def test_hourly_rate_is_prorated_by_half_hour(self):
        self.assertEqual(cs.calculate_price(Decimal("12.00"), "HOUR", at(5, 9), at(5, 10, 30)), Decimal("18.00"))
        self.assertEqual(cs.calculate_price(Decimal("15.00"), "HOUR", at(5, 9), at(5, 9, 30)), Decimal("7.50"))

    def test_duration_text(self):
        self.assertEqual(cs.describe_duration("DAY", at(5, 9), at(6, 9)), "1 day")
        self.assertEqual(cs.describe_duration("DAY", at(5, 9), at(8, 9)), "3 days")
        self.assertEqual(cs.describe_duration("HOUR", at(5, 9), at(5, 10, 30)), "1.5 hours")
        self.assertEqual(cs.describe_duration("HOUR", at(5, 9), at(5, 10)), "1 hour")


class WindowRuleTests(unittest.TestCase):
    def check(self, unit, status, start, end):
        cs.validate_window(unit, status, start, end, NOW)

    def test_valid_windows(self):
        self.check("DAY", "AVAILABLE", at(5, 9), at(7, 9))
        self.check("HOUR", "AVAILABLE", at(5, 9), at(5, 9, 30))

    def test_rejections(self):
        cases = (
            ("DAY", "MAINTENANCE", at(5, 9), at(6, 9), "maintenance"),
            ("DAY", "RETIRED", at(5, 9), at(6, 9), "not available"),
            ("HOUR", "AVAILABLE", at(5, 9, 15), at(5, 10), "half hour"),
            ("HOUR", "AVAILABLE", at(2, 9), at(2, 10), "passed"),
            ("HOUR", "AVAILABLE", at(5, 10), at(5, 9), "after the start"),
            ("DAY", "AVAILABLE", at(5, 9), at(5, 21), "24-hour"),
            ("DAY", "AVAILABLE", at(5, 9), at(6, 10), "24-hour"),
        )
        for unit, status, start, end, fragment in cases:
            with self.subTest(unit=unit, status=status, start=start, end=end):
                with self.assertRaises(cs.BookingError) as raised:
                    self.check(unit, status, start, end)
                self.assertIn(fragment, str(raised.exception))

    def test_parse_datetime(self):
        self.assertEqual(cs.parse_datetime("2026-11-05 09:30"), at(5, 9, 30))
        with self.assertRaises(cs.BookingError):
            cs.parse_datetime("tomorrow")


class CoverageTests(unittest.TestCase):
    def test_free_partial_and_blocked(self):
        start, end = at(5, 9), at(5, 17)
        self.assertEqual(cs.coverage([], start, end), "free")
        self.assertEqual(cs.coverage([(at(4, 9), at(5, 9))], start, end), "free")
        self.assertEqual(cs.coverage([(at(5, 12), at(5, 13))], start, end), "partial")
        self.assertEqual(cs.coverage([(at(5, 8), at(5, 13)), (at(5, 13), at(5, 18))], start, end), "blocked")
        self.assertEqual(cs.coverage([(at(5, 8), at(5, 12)), (at(5, 14), at(5, 20))], start, end), "partial")

    def test_overlapping_blocks_are_merged(self):
        start, end = at(5, 9), at(5, 11)
        blocked = [(at(5, 9), at(5, 10)), (at(5, 9, 30), at(5, 11))]
        self.assertEqual(cs.coverage(blocked, start, end), "blocked")


class CardFieldTests(unittest.TestCase):
    def test_last_four_digits_only(self):
        self.assertEqual(cs._parse_card_fields("4242 4242-4242 1234", "2028-05", "123"), "1234")

    def test_expiry_formats(self):
        self.assertEqual(cs._parse_card_fields("12345", "05/28", "9"), "2345")

    def test_non_numeric_fields_rejected(self):
        for card, expiry, code in (("abcd", "2028-05", "123"), ("4242", "soon", "123"), ("4242", "2028-05", "12a")):
            with self.subTest(card=card, expiry=expiry, code=code):
                with self.assertRaises(cs.BookingError):
                    cs._parse_card_fields(card, expiry, code)


if __name__ == "__main__":
    unittest.main()
