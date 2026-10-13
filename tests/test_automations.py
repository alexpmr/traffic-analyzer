#!/usr/bin/env python3
"""Regressões das automações. Executadas pelo pipeline sem acesso RF."""
import json
from pathlib import Path
import tempfile
import unittest

import automation_manager as a


class AutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "automations.json"
        self.defaults = a.defaults()

    def test_defaults_preserve_legacy_bots(self):
        got = a.load(self.path, self.defaults)
        self.assertTrue(got["ping"]["enabled"])
        self.assertTrue(got["clima"]["enabled"])
        self.assertEqual(got["ping"]["cooldownSeconds"], 30)
        self.assertEqual(got["clima"]["cooldownSeconds"], 300)
        self.assertEqual(got["clima"]["apiUrl"], "http://127.0.0.1:8765/clima")

    def test_independent_toggle_and_restart(self):
        a.save(self.path, self.defaults, "ping", {"enabled": False})
        value = a.load(self.path, self.defaults)
        self.assertFalse(value["ping"]["enabled"])
        self.assertTrue(value["clima"]["enabled"])
        a.save(self.path, self.defaults, "clima", {"cooldownSeconds": 45})
        value = a.load(self.path, self.defaults)
        self.assertFalse(value["ping"]["enabled"])
        self.assertEqual(value["clima"]["cooldownSeconds"], 45)
        self.assertTrue((self.path.parent / "automation-audit.jsonl").exists())

    def test_templates_do_not_execute_python(self):
        ping = a.validate_bot("ping", {"template": "PONG {{origem}} — {{rota}}"},
                              self.defaults)
        value = a.preview("ping", ping, default_ping_text="PING VHF3\nOrigem: NÓ !1\nTeste de rota: direto")
        self.assertIn("PONG NÓ !1", value["text"])
        self.assertFalse(value["transmits"])
        with self.assertRaises(ValueError):
            a.validate_bot("ping", {"template": "{{origem.__class__}}"}, self.defaults)
        with self.assertRaises(ValueError):
            a.validate_bot("ping", {"template": "x {{variavel_inventada}}"}, self.defaults)

    def test_clima_preview_without_transmission(self):
        clima = self.defaults["clima"]
        result = a.preview("clima", clima, clima_responses=["Temperatura: 25°C", "Vento: 6 km/h"])
        self.assertEqual(len(result["parts"]), 1)
        self.assertTrue(result["bytes"] > 0)
        self.assertFalse(result["transmits"])

    def test_validation_rejects_unsafe_urls(self):
        for url in ("http://169.254.169.254/latest/meta-data/", "https://localhost:8765/clima",
                    "http://evil.example/clima", "file:///etc/passwd",
                    "http://localhost:8765@evil.example/test"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    a.validate_bot("clima", {"apiUrl": url}, self.defaults)

    def test_validation_rejects_invalid_ranges(self):
        for bot, key, value in [("ping", "cooldownSeconds", -1),
                                ("ping", "routeTimeoutSeconds", 500),
                                ("clima", "replyGapSeconds", 1000)]:
            with self.subTest(bot=bot,key=key):
                with self.assertRaises(ValueError):
                    a.validate_bot(bot, {key: value}, self.defaults)

    def test_payload_limit(self):
        long_message = "á" * 1300
        with self.assertRaises(ValueError):
            a.preview("ping", self.defaults["ping"], default_ping_text=long_message)

    def test_spa_deep_links_exist(self):
        # No server needs to listen: check the Python-served HTML and route table.
        import traffic_analyzer_web as web
        self.assertIn('data-view="automations"', web.HTML)
        self.assertIn("automations:'/automacoes'", web.HTML)
        self.assertIn("automacoes:'automations'", web.HTML)
        self.assertIn('/automations_ui.js', web.HTML)
        self.assertIn("/automacoes/", Path(web.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
