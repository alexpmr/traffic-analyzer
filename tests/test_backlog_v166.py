import json
import tempfile
import time
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
        blocks = meshcmd.build_clima_blocks(self.CLIMA_RAW, "não, situação segura", forecast)
        self.assertEqual(blocks, [
            "Temperatura e umidade (1/5)\nTemperatura: 31.0 °C\nUmidade relativa: 35%\nPonto de orvalho: 13.6 °C\n"
            "Pressão: 889.6 hPa\nÍndice ultravioleta: 2.7",
            "Luz e vento (2/5)\nIluminação: 26431 lux\nRadiação solar: 203 W/m²\n"
            "Vento mínimo / médio / rajada: 0.4/2.9/5.4 km/h\nDireção do vento: 70° ENE",
            "Chuva (3/5)\nSem chuva no momento\nPrecipitação em 1 minuto: 0.0 mm\nTaxa de chuva em 10 minutos: 0.0 mm/h\n"
            "Acumulado de chuva em 1 hora: 0.0 mm\nAcumulado de chuva em 24 horas: 0.0 mm",
            "Raios (4/5)\nRaios próximos: não, situação segura\nRaios detectados na última hora: 0\nÚltimo raio detectado: sem registro",
            "Previsão do tempo (5/5)\nAgora: Parcialmente nublado, 31 °C\nHoje: Ensolarado, 18 a 32 °C, chuva 10%\n"
            "Amanhã: Chuva, 17 a 28 °C, chuva 60%",
        ])
        config = {"template": "{{clima}}"}
        parts = automgr.preview("clima", config, clima_responses=blocks)["parts"]
        self.assertEqual(parts, blocks)
        self.assertTrue(all(len(x.encode("utf-8")) <= 200 for x in parts))

    def test_clima_without_home_assistant_keeps_tempest_blocks_and_alerts(self):
        blocks = meshcmd.build_clima_blocks(self.CLIMA_RAW + ["ALERTA | RAIOS"])
        self.assertEqual([b.split("\n")[0] for b in blocks],
                         ["Temperatura e umidade (1/5)", "Luz e vento (2/5)", "Chuva (3/5)", "Raios (4/5)", "Alerta meteorológico (5/5)"])
        self.assertNotIn("Raios próximos", blocks[3])

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
        self.assertEqual(lightning, "SIM, situação de risco")
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

    def test_home_assistant_settings_from_screen_never_expose_token(self):
        env = {"url": "http://127.0.0.1:8123", "token": "", "lightningEntity": "binary_sensor.a",
               "forecastEntity": "weather.b"}
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(web, "HOME_ASSISTANT_SETTINGS_FILE", Path(d) / "ha.json"), \
             mock.patch.object(web, "CLIMA_HOME_ASSISTANT_ENV", env):
            public = web._home_assistant_public()
            self.assertFalse(public["configured"]);self.assertIn("não configurado", public["warning"])
            with mock.patch.object(meshcmd, "fetch_open_meteo_forecast", return_value=["Hoje: Chuva"]) as om:
                result = web._test_home_assistant()
            self.assertTrue(result["success"]);self.assertIn("Open-Meteo", result["forecastSource"])
            self.assertEqual(result["forecast"], ["Hoje: Chuva"]);om.assert_called_once()
            public = web._save_home_assistant({"url": "http://192.168.0.10:8123/", "token": "abc.def",
                                               "forecastEntity": "weather.casa"})
            self.assertTrue(public["configured"]);self.assertEqual(public["tokenSource"], "tela")
            self.assertNotIn("abc.def", json.dumps(public))
            config = web._home_assistant_config()
            self.assertEqual((config["url"], config["token"], config["forecastEntity"], config["lightningEntity"]),
                             ("http://192.168.0.10:8123", "abc.def", "weather.casa", "binary_sensor.a"))
            web._save_home_assistant({"url": "http://192.168.0.10:8123"})
            self.assertEqual(web._home_assistant_config()["token"], "abc.def")
            web._save_home_assistant({"clearToken": True})
            self.assertFalse(web._home_assistant_public()["configured"])
            for bad in [{"url": "ftp://x"}, {"url": "http://u:p@x"}, {"forecastEntity": "weather/../x"},
                        {"token": "com espaço"}, {"other": 1}]:
                with self.assertRaises(ValueError):
                    web._save_home_assistant(bad)

    def test_home_assistant_test_reports_reason(self):
        import urllib.error
        err = urllib.error.HTTPError("http://ha/api/states/x", 401, "Unauthorized", {}, None)
        with mock.patch.object(meshcmd, "_ha_request", side_effect=err):
            errors = []
            meshcmd.fetch_home_assistant_weather("http://ha", "t", "binary_sensor.a", "weather.b", errors=errors)
        self.assertTrue(errors and all("401" in e for e in errors))

    def test_open_meteo_forecast_and_fallback_without_home_assistant(self):
        import datetime as dt
        import io
        body = {"current": {"temperature_2m": 29.7, "weather_code": 2},
                "daily": {"time": ["2026-10-22", "2026-10-23", "2026-10-24"], "weather_code": [3, 81, 95],
                          "temperature_2m_max": [31.2, 27.0, 26.0], "temperature_2m_min": [18.1, 17.4, 16.0],
                          "precipitation_probability_max": [10, 70, 90]}}

        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False

        with mock.patch.object(meshcmd.urllib.request, "urlopen", return_value=Resp(json.dumps(body).encode())) as op:
            lines = meshcmd.fetch_open_meteo_forecast(-15.8, -47.9, today=dt.date(2026, 10, 22))
        self.assertEqual(lines, ["Agora: Parcialmente nublado, 30 °C", "Hoje: Nublado, 18 a 31 °C, chuva 10%",
                                 "Amanhã: Pancadas de chuva, 17 a 27 °C, chuva 70%"])
        self.assertIn("latitude=-15.8000", op.call_args.args[0].full_url)
        errors = []
        with mock.patch.object(meshcmd.urllib.request, "urlopen", side_effect=OSError("offline")):
            self.assertIsNone(meshcmd.fetch_open_meteo_forecast(-15.8, -47.9, errors=errors))
        self.assertIn("Open-Meteo", errors[0])

        tempest = Resp(json.dumps({"responses": self.CLIMA_RAW}).encode())
        with mock.patch.object(meshcmd.urllib.request, "urlopen", return_value=tempest), \
             mock.patch.object(meshcmd, "fetch_open_meteo_forecast", return_value=["Hoje: Nublado"]) as om:
            blocks = meshcmd.fetch_clima_responses("http://127.0.0.1:8765/clima", home_assistant={},
                                                   forecast_location=(-15.8, -47.9))
        self.assertEqual(blocks[-1], "Previsão do tempo (5/5)\nHoje: Nublado")
        self.assertEqual(om.call_args.args[:2], (-15.8, -47.9))
        # Home Assistant com previsão válida tem precedência; o Open-Meteo não é consultado.
        tempest.seek(0)
        with mock.patch.object(meshcmd.urllib.request, "urlopen", return_value=tempest), \
             mock.patch.object(meshcmd, "fetch_home_assistant_weather", return_value=("nenhuma", ["Hoje: Sol"])), \
             mock.patch.object(meshcmd, "fetch_open_meteo_forecast") as om:
            blocks = meshcmd.fetch_clima_responses("http://x", home_assistant={"url": "http://ha", "token": "t"},
                                                   forecast_location=(1, 2))
        om.assert_not_called();self.assertEqual(blocks[-1], "Previsão do tempo (5/5)\nHoje: Sol")

    def test_forecast_location_saved_node_or_brasilia(self):
        with tempfile.TemporaryDirectory() as d, \
             mock.patch.object(web, "HOME_ASSISTANT_SETTINGS_FILE", Path(d) / "ha.json"), \
             mock.patch.object(web, "TOPOLOGY_FILE", Path(d) / "topology.json"), \
             mock.patch.object(web, "MESH_COMMAND_NODE_LABEL", "VHF3"):
            self.assertEqual(web._forecast_location()[2], "Brasília (padrão)")
            (Path(d) / "topology.json").write_text(json.dumps({"nodes": [
                {"nodeNum": 1, "shortName": "VHF3", "longName": "PT2VHF-3", "latitude": -15.75, "longitude": -47.95}]}))
            self.assertEqual(web._forecast_location(), (-15.75, -47.95, "posição do nó VHF3"))
            web._save_home_assistant({"forecastLatitude": "-15,6", "forecastLongitude": "-48.1"})
            self.assertEqual(web._forecast_location(), (-15.6, -48.1, "coordenadas salvas"))
            for bad in [{"forecastLatitude": "abc", "forecastLongitude": "1"}, {"forecastLatitude": 91, "forecastLongitude": 0}]:
                with self.assertRaises(ValueError):
                    web._save_home_assistant(bad)
            web._save_home_assistant({"forecastLatitude": "", "forecastLongitude": ""})
            self.assertEqual(web._forecast_location()[2], "posição do nó VHF3")

    def test_ping_traceroute_round_trip_lines(self):
        # Mesmo traceroute da captura do MeshMonitor (valores brutos do rádio; SNR em dB = valor ÷ 4).
        vhf3, rpt5, bff1, bff2, vhf2 = 0x2a4a005a, 0x11110005, 0x22220001, 0x22220002, 0x2a4a0002
        names = {vhf3: "VHF3", rpt5: "RPT5", bff1: "BFF1", bff2: "BFF2", vhf2: "VHF2"}
        label = lambda n: names.get(n, f"!{n:08x}")
        trace = {"fromNodeNum": vhf3, "toNodeNum": bff1, "route": f"[{rpt5}]", "snrTowards": [22, -44],
                 "routeBack": [bff2, vhf2], "snrBack": [24, -49, 25]}
        self.assertEqual(meshcmd.format_traceroute_lines(trace, label, 20), [
            "Rota de ida:", "VHF3 → RPT5: 5.5 dB", "RPT5 → BFF1: -11.0 dB",
            "Rota de volta:", "BFF1 → BFF2: 6.0 dB", "BFF2 → VHF2: -12.2 dB", "VHF2 → VHF3: 6.2 dB"])
        # Volta ausente nunca é inferida; enlace direto; SNR desconhecido (-128/4 = -32) omitido; hop placeholder.
        self.assertEqual(meshcmd.format_traceroute_lines(
            {"fromNodeNum": vhf3, "toNodeNum": bff1, "route": [], "snrTowards": [-128]}, label), [
            "Rota de ida:", "VHF3 → BFF1", "Rota de volta: não disponível"])
        self.assertEqual(meshcmd.format_traceroute_lines(
            {"fromNodeNum": vhf3, "toNodeNum": bff1, "route": [4294967295], "snrTowards": [8, 4]}, label)[1:3],
            ["VHF3 → ?: 2.0 dB", "? → BFF1: 1.0 dB"])
        self.assertEqual(meshcmd.format_traceroute_lines(None, label, 20), ["Traceroute: sem resposta em 20 s"])

    def test_ping_message_ends_with_traceroute_and_fills_variables(self):
        import automation_manager as automgr
        lines = ["Rota de ida:", "VHF3 → RPT5: 5.5 dB", "RPT5 → BFF1: -11.0 dB",
                 "Rota de volta:", "BFF1 → BFF2: 6.0 dB", "BFF2 → VHF2: -12.2 dB", "VHF2 → VHF3: 6.2 dB"]
        text = meshcmd.format_ping_message(destination_label="VHF3", origin="BFF1", message={"rxSnr": 5, "rxRssi": -90},
                                           heard_nodes_24h=10, route_lines=lines)
        self.assertEqual(text.splitlines()[-7:], lines)
        self.assertNotIn("Teste de rota", text)
        config = {"template": "{{rota_ida}}\n--\n{{rota_volta}}\n--\n{{rota}}"}
        result = automgr.preview("ping", config, default_ping_text=text)
        self.assertEqual(result["text"], "VHF3 → RPT5: 5.5 dB\nRPT5 → BFF1: -11.0 dB\n--\nBFF1 → BFF2: 6.0 dB\n"
                                         "BFF2 → VHF2: -12.2 dB\nVHF2 → VHF3: 6.2 dB\n--\nVHF3 → RPT5: 5.5 dB\nRPT5 → BFF1: -11.0 dB")
        full = automgr.preview("ping", {"template": "{{mensagem_padrao}}"}, default_ping_text=text)["parts"]
        self.assertTrue(all(len(p.encode("utf-8")) <= 200 for p in full))
        # O traceroute começa sempre em mensagem própria, com um enlace por linha.
        self.assertEqual(full[-1], "\n".join(lines))
        self.assertTrue(full[0].startswith("PING VHF3"))
        timeout = meshcmd.format_ping_message(destination_label="VHF3", origin="ST01", message={}, heard_nodes_24h=None,
                                              route_lines=["Traceroute: sem resposta em 20 s"])
        self.assertEqual(automgr.preview("ping", {"template": "{{rota}}/{{rota_volta}}"}, default_ping_text=timeout)["text"],
                         "sem resposta em 20 s/sem resposta em 20 s")

    def test_ping_route_lines_use_live_trace_and_names(self):
        vhf3, rpt1, st01 = 0x2a4a005a, 0x11110001, 0x22220002
        trace = {"fromNodeNum": vhf3, "toNodeNum": st01, "route": [rpt1], "snrTowards": [20, 12], "routeBack": [rpt1],
                 "snrBack": [16, 24], "createdAt": time.time() + 1}
        index = ({vhf3: {}, rpt1: {"shortName": "RPT1"}, st01: {"longName": "Estação 01"}}, {})
        with mock.patch.object(web, "_request_node_query") as request, \
             mock.patch.object(web, "_live_traceroutes", return_value=[{"toNodeNum": 9, "createdAt": time.time()}, trace]), \
             mock.patch.object(web, "_mesh_command_node_index", return_value=index):
            lines = web._mesh_command_route_lines(st01, 5, "VHF3")
        request.assert_called_once_with(st01, "traceroute")
        self.assertEqual(lines, ["Rota de ida:", "VHF3 → RPT1: 5.0 dB", "RPT1 → Estação 01: 3.0 dB",
                                 "Rota de volta:", "Estação 01 → RPT1: 4.0 dB", "RPT1 → VHF3: 6.0 dB"])
        with mock.patch.object(web, "_request_node_query", side_effect=RuntimeError("sem rádio")):
            self.assertEqual(web._mesh_command_route_lines(3, 5, "VHF3"), ["Traceroute: não foi possível solicitar"])

    def test_ping_waits_for_traceroute_response_not_the_pending_request(self):
        # Caso de campo: o MeshMonitor registra o pedido (sem SNR/rota) antes da resposta.
        vhf3, vhf6 = 0x2a4a005a, 0x2a4a0006
        now = time.time() + 1
        pending = {"fromNodeNum": vhf3, "toNodeNum": vhf6, "route": "[]", "snrTowards": None, "createdAt": now}
        answered = dict(pending, snrTowards=[26], routeBack=[], snrBack=[30])
        index = ({vhf3: {"shortName": "VHF3"}, vhf6: {"shortName": "VHF6"}}, {})
        with mock.patch.object(web, "_request_node_query"), \
             mock.patch.object(web, "_live_traceroutes", side_effect=[[pending], [pending], [answered]]), \
             mock.patch.object(web, "_mesh_command_node_index", return_value=index), \
             mock.patch.object(web._mesh_command_stop, "wait"):
            lines = web._mesh_command_route_lines(vhf6, 20, "VHF3")
        self.assertEqual(lines, ["Rota de ida:", "VHF3 → VHF6: 6.5 dB", "Rota de volta:", "VHF6 → VHF3: 7.5 dB"])
        clock = {"t": now}
        tick = lambda seconds=1.0: clock.__setitem__("t", clock["t"] + seconds)
        with mock.patch.object(web, "_request_node_query") as request, \
             mock.patch.object(web, "_live_traceroutes", return_value=[pending]), \
             mock.patch.object(web, "_mesh_command_node_index", return_value=index), \
             mock.patch.object(web.time, "time", side_effect=lambda: clock["t"]), \
             mock.patch.object(web._mesh_command_stop, "wait", side_effect=tick):
            self.assertEqual(web._mesh_command_route_lines(vhf6, 20, "VHF3"), ["Traceroute: sem resposta em 20 s"])
        # Sem resposta: uma única segunda tentativa, na metade do prazo.
        self.assertEqual(request.call_count, 2)

    def test_ping_traceroute_retry_gets_late_responder(self):
        vhf3, vhf6 = 0x2a4a005a, 0x2a4a0006
        start = time.time() + 1
        clock = {"t": start}
        pending = {"fromNodeNum": vhf3, "toNodeNum": vhf6, "route": None, "snrTowards": None, "createdAt": start}
        answered = {"fromNodeNum": vhf3, "toNodeNum": vhf6, "route": [], "snrTowards": [25], "routeBack": [],
                    "snrBack": [28], "createdAt": start + 15}
        requests = []
        # A resposta só aparece depois da segunda tentativa (rádio que dormia no primeiro pedido).
        live = lambda limit: [pending, answered] if len(requests) > 1 else [pending]
        index = ({vhf3: {"shortName": "VHF3"}, vhf6: {"shortName": "VHF6"}}, {})
        with mock.patch.object(web, "_request_node_query", side_effect=lambda *a: requests.append(clock["t"])), \
             mock.patch.object(web, "_live_traceroutes", side_effect=live), \
             mock.patch.object(web, "_mesh_command_node_index", return_value=index), \
             mock.patch.object(web.time, "time", side_effect=lambda: clock["t"]), \
             mock.patch.object(web._mesh_command_stop, "wait", side_effect=lambda s=1.0: clock.__setitem__("t", clock["t"] + s)):
            lines = web._mesh_command_route_lines(vhf6, 30, "VHF3")
        self.assertEqual(lines, ["Rota de ida:", "VHF3 → VHF6: 6.2 dB", "Rota de volta:", "VHF6 → VHF3: 7.0 dB"])
        self.assertEqual(len(requests), 2)
        self.assertAlmostEqual(requests[1] - requests[0], 15, delta=1)

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
