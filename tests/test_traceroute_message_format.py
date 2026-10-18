import unittest

import traffic_analyzer_web as web


class TracerouteMessageFormattingTests(unittest.TestCase):
    def test_traceroute_is_split_into_outbound_and_return_blocks(self):
        html = web.HTML
        self.assertIn("function renderTracerouteChatText", html)
        self.assertIn("Rota de ida", html)
        self.assertIn("Rota de volta", html)
        self.assertIn("traceBlocks", html)
        self.assertIn("traceBlock return", html)
        self.assertIn("Rota de volta não disponível", html)

    def test_traceroute_parser_keeps_real_return_route(self):
        html = web.HTML
        # A volta vem do segundo grupo capturado. Não pode ser fabricada invertendo a ida.
        self.assertIn("tracerouteDirectionHtml('Rota de volta',match[2],'return')", html)
        self.assertNotIn(".reverse()", html[html.index("function renderTracerouteChatText"):html.index("function renderChatText")])

    def test_each_hop_gets_own_visual_line(self):
        html = web.HTML
        self.assertIn("split(/\\s*(?:-->|→|->)\\s*/)", html)
        self.assertIn('class="traceHop"', html)
        self.assertIn(".traceHop+.traceHop", html)


if __name__ == "__main__":
    unittest.main()
