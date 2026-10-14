#!/usr/bin/env python3
"""Regressões do filtro por nome e traceroute controlado de NodeInfo."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import traffic_analyzer_web as web


class MapAndNodeInfoTests(unittest.TestCase):
    def test_node_aliases_retained_across_renames(self):
        old = {"nodeNum": 12345, "longName": "Meshtastic 8F7A", "shortName": "MESH",
               "name": "Nome de fábrica", "state": "identified"}
        new = {"nodeNum": 12345, "longName": "PT2VHF Brasília", "shortName": "VHF3",
               "name": "Nome personalizado", "state": "identified"}
        merged, _ = web._history_merge_node_json(old, new, int(time.time() * 1000))
        self.assertIn("Nome de fábrica", merged["nameAliases"])
        self.assertIn("Nome personalizado", merged["nameAliases"])
        self.assertIn("Meshtastic 8F7A", merged["nameAliases"])
        self.assertIn("PT2VHF Brasília", merged["nameAliases"])
        self.assertIn("MESH", merged["nameAliases"])
        self.assertIn("VHF3", merged["nameAliases"])
        again, _ = web._history_merge_node_json(merged, {}, int(time.time() * 1000))
        self.assertEqual(again["nameAliases"], merged["nameAliases"])

    def test_nodeinfo_active_trace_requires_real_local_tx_and_is_rate_limited(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "traffic.db"
            original_db, original_global, original_dest = (
                web.TRAFFIC_ARCHIVE_DB, web._nodeinfo_last_trace_global,
                web._nodeinfo_last_trace_destinations)
            try:
                web.TRAFFIC_ARCHIVE_DB = db
                web._nodeinfo_last_trace_global = 0
                web._nodeinfo_last_trace_destinations = {}
                web._archive_init()
                timestamp = int(time.time() * 1000)
                with web._archive_connect() as conn:
                    for packet_id, direction in ((111, "tx"), (112, "rx")):
                        conn.execute(
                            """INSERT INTO packets(archive_key,source_id,packet_id,timestamp,
                               archived_at,direction,to_node,channel,portnum_name)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (f"test-{packet_id}", web.MM_SOURCE, packet_id, timestamp,
                             timestamp, direction, 12345, 0, "NODEINFO_APP"),
                        )
                with patch.object(web, "_request_node_query", return_value={"success": True, "action": "traceroute"}) as query:
                    body = web._nodeinfo_trace_request({"packetId": 111, "nodeNum": 12345})
                    self.assertTrue(body["success"])
                    query.assert_called_once_with(12345, "traceroute")
                    with self.assertRaisesRegex(ValueError, "Limite de RF"):
                        web._nodeinfo_trace_request({"packetId": 111, "nodeNum": 12345})
                    with self.assertRaisesRegex(ValueError, "TX local"):
                        web._nodeinfo_trace_request({"packetId": 112, "nodeNum": 12345})
                    with self.assertRaisesRegex(ValueError, "TX local"):
                        web._nodeinfo_trace_request({"packetId": 111, "nodeNum": 99999})
            finally:
                web.TRAFFIC_ARCHIVE_DB = original_db
                web._nodeinfo_last_trace_global = original_global
                web._nodeinfo_last_trace_destinations = original_dest

    def test_map_search_and_nodeinfo_ui_source(self):
        html = web.HTML
        source = Path(web.__file__).read_text(encoding="utf-8")
        for name in ("mapSearchToggle", "mapSearchInput", "mapSearchClear", "mapSearchCount",
                     "nodeInfoToastEnabled", "nodeInfoAutoTraceEnabled", "nodeInfoTraceNow"):
            self.assertIn('id="' + name + '"', html)
        self.assertIn("function mapSearchMatches()", html)
        self.assertIn("function updateMapSearch(", html)
        self.assertIn("nameAliases", html)
        self.assertIn("if(mapSearchActive && !mapSearchAllowed.has(Number(n.nodeNum))) continue;", html)
        self.assertIn("if(mapSearchActive && (!mapSearchAllowed.has(Number(e.a))", html)
        self.assertIn("function nodeInfoTraceEligible(p)", html)
        self.assertIn("function requestNodeInfoTrace(p)", html)
        self.assertNotIn("drawLogicalNodeInfoLine", source)
        self.assertIn("if(!nodeHasValidMapPosition(n)) return null;", html)
        self.assertIn('if(mapSearchText.trim())params.set(\'busca\',mapSearchText.trim());', html)


if __name__ == "__main__":
    unittest.main()
