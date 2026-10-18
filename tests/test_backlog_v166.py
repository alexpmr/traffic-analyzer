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
