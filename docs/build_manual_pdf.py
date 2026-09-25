#!/usr/bin/env python3
"""Gera o manual PDF versionado do Traffic Analyzer a partir do README/CHANGELOG."""

from __future__ import annotations
import argparse
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def extract_release_notes(changelog: str, version: str) -> list[str]:
    pat = re.compile(rf"^##\s+v?{re.escape(version)}(?:\s+-.*)?\s*$", re.M)
    m = pat.search(changelog)
    if not m:
        return []
    start = m.end()
    nxt = re.search(r"^##\s+", changelog[start:], re.M)
    block = changelog[start:start + nxt.start() if nxt else None]
    return [line[2:].strip() for line in block.splitlines() if line.strip().startswith("- ")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    version = args.version.strip()
    out = Path(args.output)
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    notes = extract_release_notes(changelog, version)

    styles = getSampleStyleSheet()
    navy = HexColor("#123047")
    blue = HexColor("#1e5f85")
    gray = HexColor("#5e6b75")
    light = HexColor("#eaf2f7")

    styles.add(ParagraphStyle(name="TA_Cover", parent=styles["Title"], fontName="Helvetica-Bold",
                              fontSize=26, leading=30, textColor=colors.white, alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="TA_CoverSub", parent=styles["Normal"], fontName="Helvetica",
                              fontSize=11, leading=15, textColor=HexColor("#d7e7f1"), alignment=TA_CENTER))
    styles.add(ParagraphStyle(name="TA_H1", parent=styles["Heading1"], fontName="Helvetica-Bold",
                              fontSize=18, leading=22, textColor=navy, spaceAfter=8))
    styles.add(ParagraphStyle(name="TA_H2", parent=styles["Heading2"], fontName="Helvetica-Bold",
                              fontSize=13, leading=16, textColor=blue, spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle(name="TA_Body", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=9.5, leading=13, textColor=HexColor("#263746"), spaceAfter=6))
    styles.add(ParagraphStyle(name="TA_Small", parent=styles["BodyText"], fontName="Helvetica",
                              fontSize=8, leading=10.5, textColor=gray, spaceAfter=4))
    styles.add(ParagraphStyle(name="TA_Code", parent=styles["Code"], fontName="Courier",
                              fontSize=8.2, leading=10.5, backColor=HexColor("#f3f6f8"),
                              borderColor=HexColor("#c9d3da"), borderWidth=0.5, borderPadding=6,
                              spaceBefore=4, spaceAfter=7))

    def P(text: str, style: str = "TA_Body") -> Paragraph:
        return Paragraph(text, styles[style])

    def bullet(text: str) -> Paragraph:
        return P("- " + text)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(gray)
        canvas.drawString(18*mm, 10*mm, f"Traffic Analyzer v{version} - por Alex, PT2VHF")
        canvas.drawRightString(A4[0]-18*mm, 10*mm, f"Página {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                            topMargin=16*mm, bottomMargin=16*mm,
                            title=f"Traffic Analyzer v{version}", author="Alex, PT2VHF")
    story = []

    cover = Table([
        [P("TRAFFIC ANALYZER", "TA_Cover")],
        [P(f"v{version}", "TA_Cover")],
        [P("Manual técnico e guia de utilização", "TA_CoverSub")],
        [P("Complemento ao MeshMonitor para análise de topologia, tráfego e operação de malhas Meshtastic.", "TA_CoverSub")],
        [Spacer(1, 20*mm)],
        [P("por Alex, PT2VHF", "TA_CoverSub")],
    ], colWidths=[A4[0]-36*mm], rowHeights=[22*mm, 20*mm, 14*mm, 25*mm, 30*mm, 18*mm])
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), navy), ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (-1,-1), "CENTER"), ("BOX", (0,0), (-1,-1), 1, blue),
    ]))
    story += [cover, Spacer(1, 9*mm), P(f"<b>Versão:</b> {version}<br/><b>Repositório:</b> alexpmr/traffic-analyzer", "TA_Small"), PageBreak()]

    story += [P("1. Novidades desta versão", "TA_H1")]
    if notes:
        story.extend(bullet(n) for n in notes)
    else:
        story.append(P("Consulte o CHANGELOG.md da Release para os detalhes desta versão."))

    story += [PageBreak(), P("2. Visão geral da ferramenta", "TA_H1"),
              P("O Traffic Analyzer usa a API do MeshMonitor como fonte de dados e mantém histórico próprio para análise. Ele não assume a conexão serial/TCP do rádio."),
              P("Principais áreas", "TA_H2")]
    for item in [
        "<b>Mapa:</b> topologia e traceroutes observados, reprodução Histórica/Ao vivo e enquadramento.",
        "<b>Tracklog:</b> histórico de posições recebidas de estações com mobilidade observada.",
        "<b>Tráfego:</b> pacotes RX/TX, filtros, payload amigável e dados técnicos.",
        "<b>Mensagens:</b> canal primário, envio e menções de nós com @.",
        "<b>Saúde da Rede:</b> indicadores de atividade, links, hops e chat.",
        "<b>Anomalias:</b> heurísticas para silêncio, SNR, hops e assimetria de rotas.",
        "<b>Configurações:</b> aparência, mapa, espessura/cor dos enlaces, som, leitura do chat, atualizações, atividade e privacidade.",
        "<b>Ajuda/Help:</b> instruções incorporadas à própria interface.",
    ]:
        story.append(bullet(item))

    story += [P("Idioma", "TA_H2"),
              P("Português (PT-BR) é o padrão. O seletor mostra as bandeiras do Brasil e dos Estados Unidos antes de Português e English. A troca altera a interface sem modificar nomes de nós, mensagens dos usuários ou valores brutos do protocolo."),
              PageBreak(), P("3. Uso e interpretação", "TA_H1"),
              P("As linhas e traceroutes representam observações feitas pela fonte configurada. Ausência de tráfego ou de rota não é prova isolada de indisponibilidade."),
              P("Pausa e Ao vivo", "TA_H2"),
              P("No modo Ao vivo, Pausar congela apenas a animação visual. Coleta e processamento continuam em segundo plano; eventos represados são liberados ao retomar."),
              P("Tracklog", "TA_H2"),
              P("O Tracklog utiliza posições realmente recebidas. Distância e percurso dependem da frequência dos POSITION_APP observados e não substituem um odômetro/GPS dedicado."),
              P("Mensagens e ACK", "TA_H2"),
              P("Estados de ACK indicam confirmação de protocolo/roteamento quando disponível. Eles não significam que uma pessoa leu a mensagem. O @ é usado apenas para localizar um nó no autocomplete e é removido antes da transmissão."),
              P("Privacidade", "TA_H2"),
              P("O token do MeshMonitor permanece no processo servidor. Conteúdo de mensagens diretas é redigido no histórico conforme a política da aplicação."),
              PageBreak(), P("4. Atualização e diagnóstico", "TA_H1"),
              P("Atualizar a instalação:", "TA_Body"),
              P("sudo traffic-analyzer-update", "TA_Code"),
              P("Verificar a versão:", "TA_Body"),
              P("cat /opt/traffic-analyzer/VERSION", "TA_Code"),
              P("Serviços:", "TA_H2"),
              P("systemctl status traffic-analyzer.timer --no-pager\nsystemctl status traffic-analyzer-map.service --no-pager", "TA_Code"),
              P("Logs:", "TA_H2"),
              P("journalctl -u traffic-analyzer.service -n 50 --no-pager\njournalctl -u traffic-analyzer-map.service -n 50 --no-pager", "TA_Code"),
              P("Auto-update", "TA_H2"),
              P("Em Configurações, o auto-update pode ser ativado. O processo web apenas grava uma solicitação em /var/lib/traffic-analyzer. O unit traffic-analyzer-auto-update.path dispara um serviço root dedicado, que baixa somente a Latest Release estável, valida o ZIP/digest, cria backup, instala, verifica /health e faz rollback se a verificação falhar."),
              P("Status do auto-update:", "TA_Body"),
              P("systemctl status traffic-analyzer-auto-update.path --no-pager\njournalctl -u traffic-analyzer-auto-update.service -n 80 --no-pager", "TA_Code"),
              P("Após atualizações de JavaScript/CSS, use Ctrl+F5 se o navegador ainda estiver mostrando conteúdo em cache."),
              P("Distribuição", "TA_H2"),
              P("A Release formal inclui ZIP versionado, traffic-analyzer-latest.zip, manual PDF e screenshots públicos anonimizados nas notas da Release.")]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    if not out.exists() or out.stat().st_size < 1000:
        raise SystemExit("PDF não foi gerado corretamente")


if __name__ == "__main__":
    main()
