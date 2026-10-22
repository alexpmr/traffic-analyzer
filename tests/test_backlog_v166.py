import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mesh_commands as meshcmd
import traffic_analyzer_web as web


class BacklogV166Tests(unittest.TestCase):
    def test_clima_compact_text_becomes_clear_multiline_text(self):
        raw = "CLIMA VHF3 | T 27.0C | UR 52% | Orvalho 16.4C | P 889.1hPa | UV 2.0"
        text = meshcmd.normalize_clima_message(raw)
        self.assertIn("\n", text)
        self.assertIn("Temperatura: 27.0 °C", text)
        self.assertIn("Umidade relativa: 52%", text)
        self.assertIn("Ponto de orvalho: 16.4 °C", text)
        self.assertIn("Pressão: 889.1 hPa", text)
        self.assertIn("Índice ultravioleta: 2.0", text)
        self.assertNotIn(" | ", text)

    def test_clima_rain_and_lightning_avoid_cryptic_abbreviations(self):
        rain = meshcmd.normalize_clima_message(
            "CHUVA | sem chuva | 1min 0.0mm | taxa10m 0.0mm/h | 1h 0.2mm | 24h 4.2mm"
        )
        self.assertIn("Precipitação em 1 minuto: 0.0 mm", rain)
        self.assertIn("Taxa de chuva em 10 minutos: 0.0 mm/h", rain)
        self.assertIn("Acumulado de chuva em 24 horas: 4.2 mm", rain)
        lightning = meshcmd.normalize_clima_message(
            "RAIOS/TEMPEST | raios 1h 0 | ultimo -- | bat 2.742V | dados 39s"
        )
        self.assertIn("Raios detectados na última hora: 0", lightning)
        self.assertIn("Último raio detectado: sem registro", lightning)
        self.assertIn("Bateria: 2.742 V", lightning)
        self.assertIn("Dados atualizados há 39 segundos", lightning)
        self.assertNotIn(" bat ", " " + lightning.lower() + " ")

    CLIMA_RAW = [
        "CLIMA VHF3 | T 31.0C | UR 35% | Orvalho 13.6C | P 889.6hPa | UV 2.7",
        "LUZ/VENTO | 26431lx | Solar 203W/m2 | min/med/raj 0.1/0.8/1.5m/s | 70graus ENE",
        "CHUVA | sem chuva | 1min 0.0mm | taxa10m 0.0mm/h | 1h 0.0mm | 24h 0.0mm",
        "RAIOS/TEMPEST | raios 1h 0 | ultimo -- | bat 2.742V | dados 39s",
    ]

    def test_clima_is_sent_as_five_separate_blocks(self):
        import datetime as dt
        import automation_manager as automgr
        state = {"state": "partlycloudy", "attributes": {"temperature": 31.2, "temperature_unit": "°C"}}
        daily = [{"datetime": "2026-10-22T15:00:00+00:00", "condition": "sunny", "temperature": 32, "templow": 18,
                  "precipitation_probability": 10},
                 {"datetime": "2026-10-23T15:00:00+00:00", "condition": "rainy", "temperature": 28.4, "templow": 17,
                  "precipitation_probability": 60}]
        forecast = meshcmd.format_forecast(state, daily, today=dt.date(2026, 10, 22))
        blocks = meshcmd.build_clima_blocks(self.CLIMA_RAW, "nenhuma", forecast)
        self.assertEqual(blocks, [
            "Temperatura e umidade\nTemperatura: 31.0 °C\nUmidade relativa: 35%\nPonto de orvalho: 13.6 °C\n"
            "Pressão: 889.6 hPa\nÍndice ultravioleta: 2.7",
            "Luz e vento\nIluminação: 26431 lux\nRadiação solar: 203 W/m²\n"
            "Vento mínimo / médio / rajada: 0.1/0.8/1.5 m/s\nDireção do vento: 70° ENE",
            "Chuva\nSem chuva no momento\nPrecipitação em 1 minuto: 0.0 mm\nTaxa de chuva em 10 minutos: 0.0 mm/h\n"
            "Acumulado de chuva em 1 hora: 0.0 mm\nAcumulado de chuva em 24 horas: 0.0 mm",
            "Raios\nDescargas próximas: nenhuma\nRaios detectados na última hora: 0\nÚltimo raio detectado: sem registro",
            "Previsão do tempo\nAgora: Parcialmente nublado, 31 °C\nHoje: Ensolarado, 18 a 32 °C, chuva 10%\n"
            "Amanhã: Chuva, 17 a 28 °C, chuva 60%",
        ])
        config = {"template": "{{clima}}"}
        parts = automgr.preview("clima", config, clima_responses=blocks)["parts"]
        self.assertEqual(parts, blocks)
        self.assertTrue(all(len(x.encode("utf-8")) <= 200 for x in parts))

    def test_clima_without_home_assistant_keeps_tempest_blocks_and_alerts(self):
        blocks = meshcmd.build_clima_blocks(self.CLIMA_RAW + ["ALERTA | RAIOS"])
        self.assertEqual([b.split("\n")[0] for b in blocks],
                         ["Temperatura e umidade", "Luz e vento", "Chuva", "Raios", "Alerta meteorológico"])
        self.assertNotIn("Descargas", blocks[3])

    def test_home_assistant_states_and_forecast_service(self):
        lightning_entity = "binary_sensor.is_lightning"
        forecast_entity = "weather.forecast_home"
        calls = []

        def fake(base, token, path, timeout, payload=None):
            calls.append((path, payload))
            if path.endswith(lightning_entity):
                return {"state": "on"}
            if path.endswith(forecast_entity):
                return {"state": "rainy", "attributes": {"temperature": 22}}
            return {"service_response": {forecast_entity: {"forecast": [
                {"datetime": "2999-01-01", "condition": "pouring", "temperature": 25, "templow": 19}]}}}

        with mock.patch.object(meshcmd, "_ha_request", side_effect=fake):
            lightning, forecast = meshcmd.fetch_home_assistant_weather(
                "http://ha:8123", "t", lightning_entity, forecast_entity)
        self.assertEqual(lightning, "detectadas")
        self.assertEqual(forecast[0], "Agora: Chuva, 22 °C")
        self.assertIn("Chuva forte, 19 a 25 °C", forecast[1])
        self.assertEqual(calls[-1][1], {"entity_id": forecast_entity, "type": "daily"})
        with mock.patch.object(meshcmd, "_ha_request", side_effect=OSError("offline")):
            self.assertEqual(meshcmd.fetch_home_assistant_weather("http://ha", "t", lightning_entity, forecast_entity),
                             ("indisponível", ["Previsão indisponível"]))
        with mock.patch.object(meshcmd, "_ha_request") as never:
            meshcmd.fetch_home_assistant_weather("http://ha", "t", "../bad", "weather.x/../../api")
            never.assert_not_called()

    def test_stale_pending_update_is_requested_again_when_page_checks_version(self):
        import json
        import time
        version = {"success": True, "status": "ok", "updateAvailable": True, "stable": True, "latestVersion": "9.9.9"}
        with tempfile.TemporaryDirectory() as d:
            status_file, request_file = Path(d) / "status.json", Path(d) / "request.json"
            with mock.patch.object(web, "UPDATE_STATUS_FILE", status_file), \
                 mock.patch.object(web, "UPDATE_REQUEST_FILE", request_file), \
                 mock.patch.object(web, "UPDATE_SETTINGS_FILE", Path(d) / "settings.json"):
                now_ms = int(time.time() * 1000)
                for state, key, age, expect in [("pending", "requestedAtMs", 60, False),
                                                ("pending", "requestedAtMs", 11 * 60, True),
                                                ("running", "startedAtMs", 20 * 60, False),
                                                ("running", "startedAtMs", 31 * 60, True)]:
                    request_file.unlink(missing_ok=True)
                    status_file.write_text(json.dumps({"state": state, "targetVersion": "9.9.9",
                                                       key: now_ms - age * 1000}))
                    web._maybe_request_auto_update(version)
                    self.assertEqual(request_file.exists(), expect, (state, age))

    def test_split_utf8_preserves_line_breaks(self):
        text = "Linha um\nLinha dois\nLinha três"
        parts = meshcmd.split_utf8(text, 200)
        self.assertEqual(parts, [text])

    def test_inmet_alert_is_multiline_and_clear(self):
        text = web._notice_inmet_message({
            "event": "Chuva intensa",
            "severity": "Severe",
            "expires": "2026-10-18T20:00:00-03:00",
            "headline": "Risco de chuva forte e rajadas de vento",
        })
        self.assertGreaterEqual(text.count("\n"), 4)
        self.assertIn("Alerta meteorológico do INMET", text)
        self.assertIn("Evento: Chuva intensa", text)
        self.assertIn("Fonte: Instituto Nacional de Meteorologia", text)

    def test_context_menu_font_and_delete_everywhere_first(self):
        html = web.HTML
        self.assertIn("fontSize:'14px'", html)
        delete_pos = html.index("Excluir da base e do dispositivo")
        private_pos = html.index("Enviar mensagem privada")
        self.assertLess(delete_pos, private_pos)

    def test_combined_delete_reports_both_results(self):
        with mock.patch.object(web, "_device_node_admin_action", return_value={"success": True}), \
             mock.patch.object(web, "_delete_local_node", return_value={"success": True}):
            result = web._delete_node_everywhere(123)
        self.assertTrue(result["success"])
        self.assertTrue(result["deviceDeleted"])
        self.assertTrue(result["localDeleted"])

    def test_combined_delete_reports_partial_failure(self):
        with mock.patch.object(web, "_device_node_admin_action", side_effect=RuntimeError("sem conexão")), \
             mock.patch.object(web, "_delete_local_node", return_value={"success": True}):
            result = web._delete_node_everywhere(123)
        self.assertFalse(result["success"])
        self.assertTrue(result["partial"])
        self.assertFalse(result["deviceDeleted"])
        self.assertTrue(result["localDeleted"])
        self.assertIn("sem conexão", result["deviceError"])


if __name__ == "__main__":
    unittest.main()
