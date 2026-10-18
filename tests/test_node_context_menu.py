import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
