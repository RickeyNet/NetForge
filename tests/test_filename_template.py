"""Tests for netforge.ui.filename_template."""

import unittest
from datetime import date
from unittest.mock import patch

from netforge.ui.filename_template import apply_filename_template


class TestFilenameTemplate(unittest.TestCase):
    @patch("netforge.ui.filename_template.date")
    def test_expands_placeholders(self, mock_date):
        mock_date.today.return_value = date(2026, 5, 29)
        result = apply_filename_template(
            "{{ hostname }}_{{ model }}_{{ date }}",
            hostname="sw1",
            model="C9300",
        )
        self.assertEqual(result, "sw1_C9300_2026-05-29")

    def test_strips_invalid_filename_chars(self):
        result = apply_filename_template(
            'bad<>name',
            hostname="sw/1",
        )
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)

    def test_empty_result_becomes_config(self):
        self.assertEqual(apply_filename_template(""), "config")


if __name__ == "__main__":
    unittest.main()
