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
        replacements = {
            "🇧🇷": "Brasil -", "🇺🇸": "Estados Unidos -",
            "👍": "like", "👎": "dislike", "❤️": "coração",
            "❤": "coração", "😂": "risada", "😮": "surpresa", "😢": "tristeza",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        text = text.replace("`", "")
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
        "<b>Mapa:</b> topologia e traceroutes observados, memória permanente de nós/enlaces, reprodução Histórica/Ao vivo, enquadramento, distinção visual entre enlaces RF confirmados e MQTT/não-RF e Cobertura RF em mapa de calor.",
        "<b>Tráfego:</b> pacotes RX/TX, filtros, payload amigável e dados técnicos.",
        "<b>Mensagens:</b> canal primário, respostas estruturadas, emojis, reações/tapbacks e localização de nós com @.",
        "<b>Saúde da Rede:</b> indicadores de atividade, links, hops e chat.",
        "<b>Pontos de atenção:</b> heurísticas para silêncio, SNR, hops e assimetria de rotas.",
        "<b>Configurações:</b> aparência, mapa, controles independentes de cor/espessura para enlaces RF e MQTT/não-RF, retenção do tráfego bruto, temas sonoros e leitura do chat. Visitantes podem personalizar itens visuais somente no próprio navegador; retenção, atualizações e padrões globais continuam administrativos.",
        "<b>Ajuda/Help:</b> instruções incorporadas à própria interface.",
    ]:
        story.append(bullet(item))

    story += [P("Idioma", "TA_H2"),
              P("Português (PT-BR) é o padrão. O seletor mostra as bandeiras do Brasil e dos Estados Unidos antes de Português e English usando SVG embutido no próprio aplicativo, sem depender do suporte de emojis do Windows ou do navegador. A troca altera a interface sem modificar nomes de nós, mensagens dos usuários ou valores brutos do protocolo."),
              PageBreak(), P("3. Uso e interpretação", "TA_H1"),
              P("As linhas e traceroutes representam observações feitas pela fonte configurada. Ausência de tráfego ou de rota não é prova isolada de indisponibilidade."),
              P("Pausa, Ao vivo e Histórico", "TA_H2"),
              P("No modo Ao vivo, vários traceroutes podem percorrer o mapa ao mesmo tempo. No Histórico, eventos são iniciados conforme a ordem temporal observada e também podem permanecer simultaneamente em trânsito. Não existe limite funcional de quantidade de pacotes animados: Pausar congela todos os ativos e mantém eventos aguardando sem descarte por quantidade; Retomar continua o conjunto. Alterar a velocidade afeta animações já em andamento. Janelas históricas extensas têm sua escala temporal comprimida proporcionalmente para uma reprodução prática."),
              P("Os caminhos animados continuam restritos aos hops efetivamente observados. Ausência de rota conhecida não autoriza o Traffic Analyzer a inventar retransmissores."),
              P("RF, MQTT e estilo dos enlaces", "TA_H2"),
              P("A partir da v1.29.0, a topologia preserva a evidência de transporte por observação de cada trecho. Linha contínua significa que existe ao menos uma observação RF confirmada do enlace no período selecionado. Linha tracejada significa que todas as observações daquele enlace no período foram classificadas como MQTT/não-RF. Se houver evidência dos dois tipos, o enlace permanece contínuo e o popup mostra a composição RF versus MQTT/não-RF."),
              P("A classificação segue a semântica do MeshMonitor: o sentinel de SNR desconhecido do firmware é tratado como MQTT/não-RF no hop. Esse sentinel não prova exclusivamente o uso de MQTT, pois também pode aparecer em falha de descriptografia, relay role ou firmware antigo; por isso o Traffic Analyzer usa a expressão MQTT/não-RF."),
              P("Em Configurações > Mapa e topologia, cor e espessura podem ser ajustadas separadamente para RF e MQTT/não-RF. Visitantes alteram apenas o próprio navegador; o administrador pode salvar esses valores no padrão global."),
              P("Mapa-base e provedores de tiles", "TA_H2"),
              P("O modo Ruas usa o endpoint oficial atual do OpenStreetMap: https://tile.openstreetmap.org/{z}/{x}/{y}.png. A interface envia uma política de Referer compatível com requisições web cross-origin. Se os tiles OSM falharem repetidamente, o Traffic Analyzer troca temporariamente para o mapa Claro (CARTO) para evitar uma tela em branco. A troca manual de mapa-base continua disponível em Configurações. Na v1.46.0, o mapa usa zoom fracionário mais gradual e sensibilidade reduzida na roda do mouse/touchpad para oferecer níveis intermediários de enquadramento."),
              P("Correção de mapa da v1.47.1", "TA_H2"),
              P("A v1.47.1 corrige a regressão em que um nó histórico sem latitude/longitude conhecida podia interromper a renderização dos demais marcadores com erro Invalid LatLng. O nó sem posição continua preservado no inventário histórico, mas somente coordenadas geograficamente válidas são entregues ao Leaflet."),
              P("Atualização automática", "TA_H2"),
              P("A partir da v1.48.0, a instalação de novas Releases estáveis oficiais é sempre automática. O serviço web verifica a versão em background mesmo sem navegador aberto ou administrador conectado, cria a solicitação de update e mantém a cadeia segura de lock, health check, rollback e backoff. Após a atualização, cada navegador/perfil recebe uma vez o popup com as novidades daquela versão."),
              P("Cores de atividade dos nós", "TA_H2"),
              P("A idade dos nós aceita timestamps em segundos ou milissegundos e também considera o lastSeenMs histórico. Verde representa até 2 horas, amarelo/laranja de 2 a 24 horas, vermelho acima de 24 horas e cinza ausência de registro confiável. Timestamps absurdamente futuros são ignorados."),
              P("Memória permanente de nós e enlaces", "TA_H2"),
              P("A partir da v1.47.0, cada nó e enlace realmente observado é consolidado em tabelas históricas do traffic.db. A memória não expira por idade, retenção do MeshMonitor, limite de traceroutes, reinício ou regeneração da topologia. Um nó ou enlace histórico só é removido quando o banco é explicitamente apagado/resetado. As janelas de tempo do mapa apenas filtram a visualização."),
              P("O sistema mantém uma fila durável de snapshots de topologia. Se o serviço web estiver temporariamente parado enquanto o coletor continua ativo, os snapshots pendentes são consolidados no banco quando a interface retornar. Na atualização para a v1.47.0, o Traffic Analyzer também tenta recuperar enlaces antigos a partir de metadata de traceroutes já presente no arquivo bruto, quando houver informação suficiente."),
              P("Estatísticas", "TA_H2"),
              P("O período padrão da aba Estatísticas é Todo, portanto a primeira carga usa todo o histórico disponível. O usuário continua podendo restringir a análise para 1 h, 6 h, 24 h, 7 dias ou 30 dias e combinar o período com o filtro por nó."),
              P("Na v1.50.0, Estatísticas adiciona os comandos Relatório / PDF e Exportar CSV. O relatório abre uma visão estruturada com resumo executivo, Top 10 de enlaces RF diretos, nós mais ativos, interações por chat e pontos de atenção; o navegador pode imprimi-lo ou salvá-lo diretamente como PDF. A exportação CSV respeita o período e o filtro por nó selecionados."),
              P("Na subaba Acessos, os controles Período, Atualizar e Baixar log passam para a mesma faixa do cabeçalho principal de Estatísticas, eliminando a segunda barra horizontal e preservando quebra responsiva em telas estreitas."),
              P("No popup e na visualização ampliada do nó, o botão Tudo dispara as consultas em uma única rodada concorrente. Cada consulta mantém acompanhamento, resposta, erro e timeout independentes; uma consulta lenta ou sem resposta não impede o início das demais."),
              P("Na v1.51.0, o Top 10 de enlaces RF diretos passa para a subaba Ranking. As tabelas de Ranking, RF e Routing tornam-se fluidas para usar a largura disponível sem barras de rolagem horizontal desnecessárias. Em Routing, Distribuição por hops e Nós intermediários observados continuam lado a lado em desktop e empilham em telas menores."),
              P("A subaba Anomalias passa a se chamar Pontos de atenção. A mudança é de apresentação; a lógica de severidade e as heurísticas permanecem as mesmas."),
              P("A barra superior de Estatísticas permanece visível durante a rolagem. Saúde da Rede, Pontos de atenção e Acessos deixam de criar contêineres verticais de rolagem próprios, evitando que as subabas desapareçam ao percorrer conteúdos longos."),
              P("Em Estatísticas > Ranking, o ranking dos 10 enlaces RF diretos mais longos considera somente hops físicos confirmados por RF. Cada linha é interativa: ao selecionar um enlace, o Mapa isola os dois nós e o hop escolhido, enquadra o par e oferece o botão Mostrar todos os nós e enlaces para restaurar a topologia completa."),
              P("Na subaba Ranking, o Top 10 usa somente enlaces cuja adjacência veio do endpoint /traceroutes do MeshMonitor. O MeshMonitor define route e routeBack como listas de nós intermediários: A com route=[B] e destino C gera A↔B e B↔C; route=[] significa uma perna sem intermediários. SNR válido continua obrigatório para classificar o hop como RF."),
              P("Na v1.53.0, pacotes TRACEROUTE_APP brutos arquivados, inclusive TX/RX e valores hop_start/hop_limit, deixam de promover enlaces ao Ranking. Uma migração corretiva invalida evidências diretas legadas da v1.52.0 sem apagar eventos, nós, enlaces ou SNR. O Ranking é reconstruído somente por snapshots confiáveis do coletor v1.53.0."),
              P("O endpoint do Ranking também retorna IDs de traceroute/pacote associados à evidência; a interface os mostra no tooltip da linha para facilitar auditoria de casos suspeitos."),
              P("Na v1.55.0, o período Todo recupera também enlaces diretos antigos de nós hoje offline usando exclusivamente a API v1 autenticada pelo MM_API_TOKEN. O sistema começa com 5.000 traceroutes e amplia progressivamente o limite até alcançar o início do histórico ou o teto de segurança configurado."),
              P("A migração topology-direct-history-v4 força uma nova recuperação mesmo em instalações onde a v1.54.0 marcou incorretamente um backfill vazio como completo. Depois de revalidada, a evidência permanece no traffic.db até reset explícito e não depende de o nó voltar a ficar online."),
              P("A consulta periódica continua leve; o backfill profundo ocorre separadamente na primeira sincronização da nova migração."),
              P("Retenção do banco de tráfego", "TA_H2"),
              P("Em Configurações > Banco de tráfego, o administrador escolhe a retenção dos pacotes e posições brutas: 1 dia, 1 semana, 1 mês ou Nunca apagar. O padrão é Nunca apagar. Essa limpeza não remove a memória histórica de nós e enlaces; primeira/última observação, última posição conhecida e evidências agregadas necessárias à topologia permanecem até o banco inteiro ser apagado/resetado."),
              P("Posições históricas", "TA_H2"),
              P("A coleta de posições recebidas continua preservada internamente em traffic.db para relatórios e análises futuras. A v1.27.0 remove a aba Tracklog e deixa de expor esse histórico por endpoint público."),
              P("Mensagens, respostas e reações", "TA_H2"),
              P("Estados de ACK indicam confirmação de protocolo/roteamento quando disponível. Eles não significam que uma pessoa leu a mensagem. O @ é usado apenas para localizar um nó no autocomplete e não integra o texto final transmitido."),
              P("Responder usa o replyId nativo do Meshtastic/MeshMonitor para vincular a nova mensagem ao pacote original. O compositor também aceita emojis. Reações como like, dislike e coração tentam primeiro o tapback estruturado (emoji=1 + replyId). Se o endpoint legado de tapback retornar HTTP 403, mas a API v1 continuar permitindo escrita no canal, o Traffic Analyzer envia automaticamente uma resposta emoji compatível com replyId e informa esse modo no status."),
              P("A aba Mensagens preserva a posição quando o usuário sobe para ler mensagens antigas. Novas mensagens não forçam a tela para o final; um botão Novas mensagens aparece para retornar ao fim e reativar o auto-scroll. Carregar anteriores também mantém o ponto de leitura."),
              P("Temas sonoros", "TA_H2"),
              P("A interface oferece Fliperama anos 70, Formal, Rádio / Telecom e Silencioso. No modo Fliperama, o início da viagem lembra um lançador mecânico, relays observados recebem ricochetes metálicos e chegada/ACK recebe efeito de alvo/pontuação. A chegada de uma nova mensagem usa uma assinatura sonora própria, separada do limitador de sons de roteamento, para continuar audível em períodos de tráfego intenso. Reações não disparam a campainha de nova mensagem."),
              P("Autenticação e acesso externo", "TA_H2"),
              P("Com a autenticação habilitada, visitantes sem login podem alterar preferências visuais e de leitura em Configurações. Essas mudanças ficam apenas no localStorage daquele navegador e não modificam o servidor nem a experiência de outros visitantes. Mensagens continua visível, mas sem envio, resposta ou reação."),
              P("O administrador pode salvar sua configuração visual atual como padrão global para novos visitantes. O visitante pode sobrescrever esse padrão localmente e restaurá-lo quando quiser. Atualizações, refresh administrativo da topologia, envio de mensagens e qualquer escrita persistente no servidor continuam protegidos por sessão administrativa e token CSRF."),
              P("As credenciais são armazenadas apenas como hash derivado, e as sessões expiram automaticamente."),
              P("Para configurar ou trocar a credencial administrativa, execute traffic-analyzer-set-password como root no servidor."),
              P("Para acesso pela Internet, publique a aplicação atrás de HTTPS com reverse proxy. O Traffic Analyzer não implementa TLS diretamente."),
              P("Privacidade", "TA_H2"),
              P("O token do MeshMonitor e o hash administrativo permanecem no processo servidor. Conteúdo de mensagens diretas é redigido no histórico conforme a política da aplicação."),
              PageBreak(), P("4. Atualização e diagnóstico", "TA_H1"),
              P("Atualizar a instalação:", "TA_Body"),
              P("Use Configurações > Atualizações > Atualizar agora. O processo usa a Latest Release estável e mantém as proteções de backup, health-check e rollback."),
              P("Verificar a versão:", "TA_Body"),
              P("cat /opt/traffic-analyzer/VERSION", "TA_Code"),
              P("Serviços:", "TA_H2"),
              P("systemctl status traffic-analyzer.timer --no-pager\nsystemctl status traffic-analyzer-map.service --no-pager", "TA_Code"),
              P("Logs:", "TA_H2"),
              P("journalctl -u traffic-analyzer.service -n 50 --no-pager\njournalctl -u traffic-analyzer-map.service -n 50 --no-pager", "TA_Code"),
              P("Auto-update", "TA_H2"),
              P("Em Configurações, o auto-update pode ser ativado. A verificação de nova versão ocorre a cada 15 minutos por padrão e o administrador pode alterar esse intervalo entre 5 e 1.440 minutos sem reiniciar o serviço. O processo web apenas grava uma solicitação em /var/lib/traffic-analyzer. O unit traffic-analyzer-auto-update.path dispara um serviço root dedicado, que baixa somente a Latest Release estável, valida o ZIP/digest, cria backup, instala, verifica /health e faz rollback se a verificação falhar."),
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
