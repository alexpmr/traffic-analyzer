#!/usr/bin/env python3
"""Regressões para o caminho RF PING/CLIMA; não exige rádio físico."""
import threading
import time
import unittest
from mesh_command_dispatch import MeshCommandDispatcher


class FakeMeshInterface:
    def __init__(self):
        self.local = 0x8fa573a4
    def getMyNodeInfo(self):
        return {"num": self.local}


class DispatchTests(unittest.TestCase):
    def make(self, process, sent, seen=None, record=None, **kwargs):
        return MeshCommandDispatcher(
            process=process,
            seen=seen or (lambda _: False),
            record=record or (lambda *a, **k: None),
            send=lambda text, command: sent.append((text, command)) or {"success": True},
            key=lambda row: row["id"], max_pending=12, **kwargs,
        ).start()

    def test_receiving_is_nonblocking_and_bots_are_independent(self):
        from traffic_analyzer_web import _mesh_command_receive_packet
        iface = FakeMeshInterface()
        ping_started = threading.Event()
        release_ping = threading.Event()
        clima_done = threading.Event()
        sent = []

        def process(row, command, send_func):
            if command == "ping":
                ping_started.set()
                self.assertTrue(release_ping.wait(3))
            send_func(command + "-resposta")
            if command == "clima":
                clima_done.set()

        d = self.make(process, sent)
        try:
            ping = {"from": 42, "to": 0xffffffff, "id": 101, "channel": 0,
                    "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "PING"}}
            clima = {"from": 43, "to": 0xffffffff, "id": 102, "channel": 0,
                     "decoded": {"portnum": "TEXT_MESSAGE_APP", "payload": b"#clima"}}
            t0 = time.monotonic()
            self.assertTrue(_mesh_command_receive_packet(ping, iface, d))
            self.assertLess(time.monotonic() - t0, 0.2)
            self.assertTrue(ping_started.wait(1))
            self.assertTrue(_mesh_command_receive_packet(clima, iface, d))
            self.assertTrue(clima_done.wait(2), "CLIMA não pode aguardar traceroute do PING")
            self.assertFalse(_mesh_command_receive_packet(ping, iface, d), "duplicata RF")
            release_ping.set()
            deadline = time.time() + 2
            while len(sent) != 2 and time.time() < deadline:
                time.sleep(0.02)
            self.assertEqual({cmd for _, cmd in sent}, {"ping", "clima"})
            st = d.snapshot()
            self.assertEqual(st["bots"]["ping"]["rxCount"], 1)
            self.assertEqual(st["bots"]["clima"]["rxCount"], 1)
            self.assertEqual(st["bots"]["ping"]["txCount"], 1)
            self.assertEqual(st["bots"]["clima"]["txCount"], 1)
        finally:
            release_ping.set()
            d.stop()

    def test_ignores_unrelated_and_own_traffic(self):
        from traffic_analyzer_web import _mesh_command_receive_packet
        iface = FakeMeshInterface()
        sent = []
        d = self.make(lambda row, command, send_func: send_func("pong"), sent)
        try:
            base = {"from": 42, "to": 0xffffffff, "id": 5, "channel": 0,
                    "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "ping"}}
            for changes in (
                {"channel": 1},
                {"to": 123},
                {"from": iface.local},
                {"decoded": {"portnum": "NODEINFO_APP", "text": "ping"}},
            ):
                bad = dict(base, **changes)
                self.assertFalse(_mesh_command_receive_packet(bad, iface, d))
            good = dict(base, to=iface.local, id=6)
            self.assertTrue(_mesh_command_receive_packet(good, iface, d))
        finally:
            d.stop()

    def test_processing_errors_logged_not_swallowed(self):
        sent = []
        records = []
        d = self.make(lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("falha teste")),
                      sent, record=lambda *args, **kwargs: records.append((args, kwargs)))
        try:
            self.assertTrue(d.submit({"id": "100", "fromNodeNum": 1}, "ping"))
            deadline = time.time() + 2
            while not records and time.time() < deadline:
                time.sleep(0.02)
            self.assertTrue(records)
            self.assertEqual(records[0][0][2], "error")
            self.assertEqual(d.snapshot()["bots"]["ping"]["errorCount"], 1)
        finally:
            d.stop()


if __name__ == "__main__":
    unittest.main()
