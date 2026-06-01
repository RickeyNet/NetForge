"""Tests for netforge.data.iface."""

import unittest

from netforge.data.iface import (
    _canon_iface,
    expand_port_groups_for_stack,
    expand_range_iface,
)


class TestExpandRangeIface(unittest.TestCase):
    def test_single_port(self):
        self.assertEqual(expand_range_iface("Gi1/0/1"), ["Gi1/0/1"])

    def test_range(self):
        self.assertEqual(
            expand_range_iface("range Gi1/0/1-3"),
            ["Gi1/0/1", "Gi1/0/2", "Gi1/0/3"],
        )

    def test_invalid_range_passthrough(self):
        self.assertEqual(expand_range_iface("range bad"), ["range bad"])


class TestExpandPortGroups(unittest.TestCase):
    def test_stack_one_unchanged(self):
        groups = [{"prefix": "Gi1/0/", "start": 1, "end": 4}]
        self.assertEqual(expand_port_groups_for_stack(groups, 1), groups)

    def test_stack_two_expands(self):
        groups = [{"prefix": "GigabitEthernet1/0/", "start": 1, "end": 2}]
        out = expand_port_groups_for_stack(groups, 2)
        prefixes = {g["prefix"] for g in out}
        self.assertEqual(prefixes, {"GigabitEthernet1/0/", "GigabitEthernet2/0/"})

    def test_pre_expanded_not_duplicated(self):
        groups = [
            {"prefix": "GigabitEthernet1/0/", "start": 1, "end": 2},
            {"prefix": "GigabitEthernet2/0/", "start": 1, "end": 2},
        ]
        self.assertEqual(expand_port_groups_for_stack(groups, 2), groups)


class TestCanonIface(unittest.TestCase):
    def test_normalizes_range_spacing(self):
        self.assertEqual(_canon_iface("range  Gi1/0/1-3"), "range Gi1/0/1-3")


if __name__ == "__main__":
    unittest.main()
