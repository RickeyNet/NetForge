"""Tests for BGP advertising options in the renderer and profile parsing."""

import unittest

from netforge.render.sections import _render_bgp
from netforge.tabs.profiles import (
    _bgp_aggregates_to_text,
    _bgp_networks_to_text,
    _parse_bgp_aggregates,
    _parse_bgp_networks,
    _parse_bgp_redistribute,
)


class TestRenderBgpAdvertising(unittest.TestCase):
    def _render(self, instance, sw_inst=None):
        profile = {"bgp": {"instances": [instance]}}
        sw = {"bgp_instances": [sw_inst]} if sw_inst else {}
        return _render_bgp(profile, sw)

    def test_advertising_options_emitted(self):
        out = self._render(
            {
                "local_asn": "65001",
                "slots": [{"peer_asn": "65000", "description": "ISP-A"}],
                "networks": [{"network": "10.0.0.0", "mask": "255.0.0.0"},
                             {"network": "10.1.0.0", "mask": "255.255.0.0"}],
                "redistribute": ["connected", "ospf 1"],
                "aggregates": [{"prefix": "10.0.0.0", "mask": "255.0.0.0",
                                "summary_only": True}],
            },
            {"local_asn": "65001",
             "peer_fills": [{"peer_ip": "203.0.113.1", "password": "x"}]})
        self.assertIn(" network 10.0.0.0 mask 255.0.0.0", out)
        self.assertIn(" network 10.1.0.0 mask 255.255.0.0", out)
        self.assertIn(" redistribute connected", out)
        self.assertIn(" redistribute ospf 1", out)
        self.assertIn(" aggregate-address 10.0.0.0 255.0.0.0 summary-only",
                      out)
        self.assertIn(" neighbor 203.0.113.1 remote-as 65000", out)

    def test_aggregate_without_summary_only(self):
        out = self._render({"local_asn": "65001",
                            "aggregates": [{"prefix": "10.0.0.0",
                                            "mask": "255.0.0.0"}]})
        self.assertIn(" aggregate-address 10.0.0.0 255.0.0.0", out)
        self.assertNotIn("summary-only", out)

    def test_backward_compatible_without_new_keys(self):
        # A profile with no advertising keys emits no extra lines.
        out = self._render({"local_asn": "65001",
                            "slots": [{"peer_asn": "65000"}]})
        self.assertNotIn("redistribute", out)
        self.assertNotIn("aggregate-address", out)


class TestBgpFieldParsing(unittest.TestCase):
    def test_networks_roundtrip(self):
        text = "10.0.0.0 255.0.0.0\n192.168.1.0 255.255.255.0"
        nets = _parse_bgp_networks(text)
        self.assertEqual(nets, [
            {"network": "10.0.0.0", "mask": "255.0.0.0"},
            {"network": "192.168.1.0", "mask": "255.255.255.0"}])
        self.assertEqual(_bgp_networks_to_text(nets), text)

    def test_network_without_mask(self):
        self.assertEqual(_parse_bgp_networks("10.0.0.0"),
                         [{"network": "10.0.0.0", "mask": ""}])

    def test_redistribute_drops_blanks(self):
        self.assertEqual(
            _parse_bgp_redistribute("connected\n\n  ospf 1 \n"),
            ["connected", "ospf 1"])

    def test_aggregates_summary_only_flag(self):
        aggs = _parse_bgp_aggregates(
            "10.0.0.0 255.0.0.0 summary-only\n172.16.0.0 255.255.0.0")
        self.assertEqual(aggs, [
            {"prefix": "10.0.0.0", "mask": "255.0.0.0", "summary_only": True},
            {"prefix": "172.16.0.0", "mask": "255.255.0.0",
             "summary_only": False}])
        # Round-trips back to canonical text.
        self.assertEqual(
            _bgp_aggregates_to_text(aggs),
            "10.0.0.0 255.0.0.0 summary-only\n172.16.0.0 255.255.0.0")


if __name__ == "__main__":
    unittest.main()
