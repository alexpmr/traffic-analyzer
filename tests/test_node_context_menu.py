import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import traffic_analyzer_web as web


class NodeContextMenuTests(unittest.TestCase):
    def test_context_menu_is_wired_to_map_and_nodes(self):
        html = web.HTML
        self.assertIn("showNodeContextMenu(n", html)
        self.assertIn("marker.on('contextmenu'", html)
        self.assertIn("tr.addEventListener('contextmenu'", html)
        for label in [
            "Enviar mensagem privada",
            "Solicitar Node Info",
            "Solicitar posição",
            "Executar Traceroute",
            "Executar Ping",
            "Ver tráfego deste nó",
            "Copiar todas as informações",
            "Excluir nó do banco local",
        ]:
            self.assertIn(label, html)

    def test_delete_local_node_removes_node_related_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_db = web.TRAFFIC_ARCHIVE_DB
            old_source = web.MM_SOURCE
            try:
                web.TRAFFIC_ARCHIVE_DB = Path(tmp) / "traffic.db"
                web.MM_SOURCE = "default"
                web._archive_init()
                with web._archive_connect() as conn:
                    node = {"nodeNum": 10, "nodeId": "!0000000a", "name": "A"}
                    conn.execute(
                        "INSERT INTO topology_nodes(source_id,node_num,first_seen_ms,last_seen_ms,position_seen_ms,node_json) VALUES(?,?,?,?,?,?)",
                        ("default", 10, 1, 2, 2, json.dumps(node)),
                    )
                    conn.execute(
                        "INSERT INTO positions(position_key,source_id,node_num,node_id,node_name,timestamp,latitude,longitude,archived_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        ("p1", "default", 10, "!0000000a", "A", 2, -15.8, -47.9, 2),
                    )
                    conn.execute(
                        """INSERT INTO packets(
                           archive_key,source_id,timestamp,from_node,to_node,archived_at
                        ) VALUES(?,?,?,?,?,?)""",
                        ("pkt1", "default", 2, 10, 20, 2),
                    )
                    conn.execute(
                        """INSERT INTO topology_edge_events(
                           event_key,source_id,edge_id,a,b,timestamp_ms,transport,archived_at
                        ) VALUES(?,?,?,?,?,?,?,?)""",
                        ("e1", "default", "10:20", 10, 20, 2, "rf", 2),
                    )

                result = web._delete_local_node(10)
                self.assertTrue(result["success"])
                with web._archive_connect() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM topology_nodes WHERE node_num=10").fetchone()[0], 0)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM positions WHERE node_num=10").fetchone()[0], 0)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM packets WHERE from_node=10 OR to_node=10").fetchone()[0], 0)
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM topology_edge_events WHERE a=10 OR b=10").fetchone()[0], 0)
            finally:
                web.TRAFFIC_ARCHIVE_DB = old_db
                web.MM_SOURCE = old_source

    def test_deleted_node_is_not_reinserted_by_meshmonitor_snapshot(self):
        import time
        with tempfile.TemporaryDirectory() as tmp:
            old_db, old_source = web.TRAFFIC_ARCHIVE_DB, web.MM_SOURCE
            try:
                web.TRAFFIC_ARCHIVE_DB = Path(tmp) / "traffic.db"
                web.MM_SOURCE = "default"
                web._archive_init()
                old_heard = int(time.time()) - 3600

                def snapshot(heard):
                    return {"sourceId": "default", "generatedAtMs": int(time.time() * 1000),
                            "nodes": [{"nodeNum": 10, "nodeId": "!0000000a", "longName": "A", "lastHeard": heard},
                                      {"nodeNum": 20, "nodeId": "!00000014", "longName": "B", "lastHeard": old_heard}],
                            "edges": [{"id": "10:20", "a": 10, "b": 20, "lastSeenMs": old_heard * 1000,
                                       "events": [{"timestampMs": old_heard * 1000, "leg": "forward", "transport": "rf"}]}],
                            "traces": []}

                nums = lambda topo: {int(n["nodeNum"]) for n in topo["nodes"]}
                self.assertIn(10, nums(web._topology_history_merge(snapshot(old_heard))))
                web._delete_local_node(10)
                merged = web._topology_history_merge(snapshot(old_heard))
                self.assertEqual(nums(merged), {20})
                self.assertFalse([e for e in merged["edges"] if 10 in (e["a"], e["b"])])
                with web._archive_connect() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM topology_nodes WHERE node_num=10").fetchone()[0], 0)
                # Nova evidência real, posterior à exclusão, traz o nó de volta.
                merged = web._topology_history_merge(snapshot(int(time.time()) + 5))
                self.assertIn(10, nums(merged))
                with web._archive_connect() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM deleted_nodes").fetchone()[0], 0)
            finally:
                web.TRAFFIC_ARCHIVE_DB, web.MM_SOURCE = old_db, old_source

    def test_bulk_delete_reports_each_node_and_validates_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_db, old_source = web.TRAFFIC_ARCHIVE_DB, web.MM_SOURCE
            try:
                web.TRAFFIC_ARCHIVE_DB = Path(tmp) / "traffic.db"
                web.MM_SOURCE = "default"
                web._archive_init()
                result = web._bulk_delete_nodes([10, 20, 10], "local")
                self.assertTrue(result["success"]);self.assertEqual(result["total"], 2)
                with web._archive_connect() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM deleted_nodes").fetchone()[0], 2)
                with mock.patch.object(web, "_device_node_admin_action",
                                       side_effect=lambda n, a: {"success": n != 30} if n != 40 else (_ for _ in ()).throw(RuntimeError("sem rádio"))):
                    result = web._bulk_delete_nodes([30, 40, 50], "everywhere")
                by = {r["nodeNum"]: r for r in result["results"]}
                self.assertFalse(result["success"]);self.assertEqual(result["succeeded"], 1)
                self.assertTrue(by[50]["success"]);self.assertFalse(by[30]["deviceDeleted"])
                self.assertEqual(by[40]["deviceError"], "sem rádio");self.assertTrue(by[40]["localDeleted"])
                for nums, scope in [([], "local"), (None, "local"), ([1], "tudo"), (list(range(1, 102)), "local"), (["x"], "local")]:
                    with self.assertRaises(ValueError):
                        web._bulk_delete_nodes(nums, scope)
            finally:
                web.TRAFFIC_ARCHIVE_DB, web.MM_SOURCE = old_db, old_source

    def test_nodes_tab_single_click_selects_and_double_click_opens(self):
        html = web.HTML
        self.assertIn('id="nodesSelectAll"', html)
        self.assertIn('id="nodesBulkBar"', html)
        for action in ("favorite", "hide", "nodeinfo", "traceroute", "copy", "csv", "deleteLocal", "deleteEverywhere", "clear"):
            self.assertIn(f'data-node-bulk="{action}"', html)
        self.assertIn("nodesSelectClick(num,event);", html)
        self.assertIn("tr.addEventListener('dblclick'", html)
        self.assertNotIn("tr.addEventListener('click',()=>openNodeFromList", html)
        self.assertIn("/api/nodes-bulk-delete", html)
        self.assertIn("NODE_BULK_RF_MAX=10", html)


if __name__ == "__main__":
    unittest.main()
