# Changelog

## 1.24.1 - 2026-09-25

- Mantém todos os recursos funcionais da v1.24.0.
- Corrige o tema Silencioso para permanecer realmente sem áudio inclusive no teste.
- Permite sonorizar um relay observado logo após o lançamento quando a primeira observação da viagem já traz esse relay.
- Corrige o manual PDF para evitar glifos quadrados de bandeiras em fontes sem suporte a emoji.

## 1.24.0 - 2026-09-25

- Adiciona temas sonoros Fliperama anos 70, Formal, Rádio / Telecom e Silencioso.
- No tema Fliperama, diferencia lançamento do pacote, ricochete em relay observado, chegada/ACK, mensagem e falha.
- Sonoriza traceroutes hop a hop somente a partir dos caminhos efetivamente observados.
- Adiciona densidade sonora, intervalo mínimo, limite de sons simultâneos, filtros por tipo de evento e estéreo espacial opcional.
- Adiciona teste de tema com sequência demonstrativa.
- Adiciona som para novas mensagens e alerta para falha de envio.
- Remove o comando de atualização em linha do popup de informações da versão.
- Substitui Verificar agora por Continuar no popup de versão; o botão apenas fecha a janela.
- Mantém Ver Release no GitHub e Fechar no popup de novidades.
- Remove do popup o Markdown bruto da seção de screenshots das notas da Release.
- Garante seletor principal com 🇧🇷 Português e 🇺🇸 English, sem abreviações BR/US/ENG.

## 1.23.1 - 2026-09-25

- Corrige falha crítica de inicialização da interface da v1.23.0.
- Corrige a tabela de internacionalização, que continha uma entrada inválida por ausência de vírgula e interrompia o JavaScript antes da configuração das abas.
- Mantém smoke test em Chromium para validar a abertura e a navegação entre as principais abas antes de novas publicações.

## 1.23.0 - 2026-09-25

- Adiciona bandeiras do Brasil e dos Estados Unidos ao seletor de idioma.
- Remove o caractere @ das menções antes de transmitir a mensagem, preservando apenas o nome do nó.
- Adiciona controles visuais de fonte, negrito, itálico, sublinhado, altura de linha e espaçamento entre mensagens.
- Adiciona filtro de severidade na aba Anomalias: Todas, Críticas, Atenção e Informativas.
- Adiciona ajuste de espessura das linhas do mapa e restauração de cor/espessura ao padrão.
- Adiciona auto-update opcional por Latest Release estável, executado por serviço systemd dedicado.
- Adiciona verificação de saúde, lock contra atualizações simultâneas e rollback automático em caso de falha.
- Adiciona status de atualização, botão Atualizar agora e persistência das preferências de auto-update no servidor.
- Adiciona popup de novidades exibido uma única vez ao iniciar após uma atualização.
- O atualizador manual `traffic-analyzer-update` passa a usar a mesma cadeia segura de Latest Release estável do auto-update.

## 1.22.0 - 2026-09-24

- Adiciona internacionalização completa da interface em Português (PT-BR) e English (EN), mantendo PT-BR como padrão.
- Adiciona seletor de idioma no cabeçalho com persistência no navegador e troca imediata.
- Traduz navegação, configurações, abas, controles, filtros, status, legendas, tooltips, popups e painéis analíticos.
- Datas e números da interface passam a usar locale compatível com o idioma selecionado.
- Preserva nomes de nós, mensagens dos usuários, IDs, valores brutos de protocolo e notas de Release sem tradução artificial.
- Adiciona nova aba Ajuda/Help com instruções completas de uso do Traffic Analyzer.
- A Ajuda/Help cobre mapa, reprodução, pausa e backlog, Tracklog, Tráfego, Mensagens/@menções, Saúde da Rede, Anomalias, Configurações, idioma, atualização e limites de interpretação.
- Adiciona uma camada central de tradução com MutationObserver para também traduzir elementos criados dinamicamente.

## 1.21.0 - 2026-09-24

- Adiciona aba Tracklog com mapa histórico de deslocamento por estação.
- Cria tabela persistente `positions` em `traffic.db`, alimentada por pacotes POSITION_APP decodificados.
- Reconstrói posições antigas a partir do histórico de pacotes existente quando possível.
- Detecta mobilidade por deslocamento observado, ignora jitter submétrico e filtra saltos incompatíveis com deslocamento terrestre.
- Adiciona filtros de período, seleção de nó, enquadramento, distância acumulada e detalhes por ponto.
- Adiciona autocomplete de menções no chat ao digitar `@`, pesquisando short name, nome completo e node ID.
- Ao selecionar uma menção, substitui o atalho pelo nome completo do nó antes do envio.
- Destaca menções reconhecidas nos balões do chat.
- Mantém as correções de pausa/represamento, indicador de versão e tema claro/escuro da v1.20.0.

## 1.20.0 - 2026-09-24

- Corrige o represamento no modo Ao vivo: traceroutes incompletos não são mais marcados como vistos antes de se tornarem animáveis.
- Mantém polling, coleta e processamento durante a pausa; traceroutes completos ficam em fila e animações ativas permanecem congeladas.
- Amplia a fila de traceroutes ao vivo para 5.000 eventos e passa a informar descartes se o limite for atingido.
- Represa também pulsos de atividade visual recebidos durante a pausa e os libera ao retomar.
- Adiciona indicador de versão no topo com comparação contra a Latest Release do GitHub.
- Adiciona janela com notas da Release, link para o GitHub e comando de atualização.
- Adiciona tema Claro, mantendo Escuro como padrão, com persistência no navegador.
- Remove do resumo do mapa o aviso "Linhas = adjacências observadas, não enlaces permanentes".
- Mantém screenshots anonimizados no README e nas notas da Release.

## 1.19.0 - 2026-09-24

- Unifica os controles de reprodução e pausa em um único botão alternável ▶/⏸.
- No modo Ao vivo, a pausa continua afetando somente a animação, preservando coleta e processamento em segundo plano.
- Ao retomar o Ao vivo, traceroutes acumulados durante a pausa são iniciados simultaneamente.
- No Histórico, a pausa passa a congelar e retomar a animação exatamente do ponto atual.
- Ativa zoom fracionário no Leaflet com `zoomSnap=0.05` e `zoomDelta=0.25`.
- Refaz o comando Enquadrar para maximizar a ocupação da tela com margem aproximada de 6 px.
- O ajuste fino do enquadramento verifica os círculos dos nós e rótulos permanentes antes de aceitar um nível maior de zoom.
- Mantém screenshots anonimizados nas notas da Release e no README.


## 1.18.0 - 2026-09-23

- Pausa no modo Ao vivo congela somente a animação; coleta e processamento continuam ativos.
- Traceroutes represados iniciam simultaneamente ao retomar; animações em andamento continuam do ponto congelado.
- Auto Zoom desligado passa a bloquear enquadramentos automáticos de NodeInfo.
- Enquadrar usa margem fixa mínima de 22 px.
- Atualizar passa a regenerar a topologia imediatamente, com feedback visual.
- Removida a coluna Canal da tabela principal de Tráfego.
- Mensagens usam melhor a tela e ganham controle de tamanho de fonte em Configurações.
- Adicionados screenshots públicos anonimizados.
- Adicionado workflow de ZIP e Release formal marcada como Latest.


## v1.17.0 - 2026-09-23

- **Mensagens:** texto branco no campo de composição.
- **Mensagens:** pop-up de nova mensagem removido; permanecem somente contador e destaque piscante na aba superior enquanto houver não lidas.
- **Mensagens:** adicionada ação explícita **Carregar anteriores**, com preservação da posição de leitura.
- **Mensagens:** botão **Atualizar** passa a forçar consulta imediata com feedback visual.
- **Saúde da Rede:** ranking acumulado de interações por chat no canal primário, ordenado em ordem decrescente.
- **Distribuição:** atualização Git sem prompt de autenticação e documentação de download/instalação via ZIP.


## 1.16.0 - 2026-09-23

- Adicionada aba Mensagens para o canal primário (0), com interface de chat.
- Adicionados GET `/api/messages` e POST `/api/messages/send` no backend local do Traffic Analyzer.
- Envio é feito server-side para `/api/v1/sources/{sourceId}/messages`; o token MeshMonitor não é exposto ao navegador.
- Adicionados pop-up de nova mensagem, contador de não lidas e animação da aba Mensagens.
- Estados de entrega respeitam semântica real do MeshMonitor: `delivered` = transmitida à malha e `confirmed` = ACK do protocolo; não há recibo de leitura humana em broadcast.
- Mantidas as abas Saúde da Rede e Anomalias e o tempo amigável de última audição no popup dos nós.
- Manual PDF teve tabelas reconstruídas para evitar textos sobrepostos.

## 1.15.0 - 2026-09-23

- Adicionadas as abas superiores **Saúde da Rede** e **Anomalias**.
- Saúde da Rede consolida atividade de nós, tráfego 24 h, enlaces, traceroutes, hops, série dos últimos 7 dias e nós silenciosos.
- Detecção de Anomalias adiciona heurísticas de silêncio >24 h/>7 dias, degradação de SNR, mudança de hops e traceroute assimétrico.
- Adicionados `/api/network-health` e `/api/anomalies` para consumo pela interface e pelo futuro relatório.
- Popup de nó agora informa há quanto tempo ocorreu o último tráfego observado.
- Adicionado `update.sh` e o comando instalado `traffic-analyzer-update` para atualização direta pelo GitHub.
- Mantido OSM como mapa padrão e preservadas todas as funções de tráfego, arquivo histórico e traceroute da v1.14.0.

## 1.14.0

- Remove completamente do Traffic Analyzer o recurso **Remover nó**, incluindo botão do popup, endpoint local de exclusão e proxy destrutivo para o MeshMonitor. A exclusão volta a ser responsabilidade exclusiva do próprio MeshMonitor.
- Define **Ruas (OpenStreetMap / OSM)** como mapa-base padrão. A migração da v1.14.0 troca o antigo padrão Satélite por OSM uma única vez; escolhas manuais posteriores continuam persistidas.
- Simplifica o cabeçalho e remove a linha `gerado em ... · fonte ...`.
- Atualiza o título padrão para **Traffic Analyzer v1.14.0 - MeshMonitor - por Alex, PT2VHF**.
- Mantém o painel de traceroute com origem/destino e distâncias de ida, volta e total, sem estimar segmentos sem coordenadas.
- Mantém o diretório de instalação/extração fixo `traffic-analyzer/`, embora o arquivo ZIP continue versionado.
- Atualiza documentação, exemplos de configuração e instalador para a nova versão.

## 1.13.0

- Corrige o botão **Remover nó** para usar a rota real do MeshMonitor 4.16.x: `DELETE /api/messages/nodes/:nodeNum?sourceId=<fonte>`.
- Mantém a exclusão restrita ao banco local do MeshMonitor da fonte configurada e preserva o histórico já arquivado em `traffic.db`.
- Converte erros `401`, `403` e `404` de remoção em mensagens amigáveis; respostas HTML do MeshMonitor não são mais despejadas na interface.
- Informa especificamente quando o token não possui `messages:write`, quando o nó já não existe e quando o endpoint de remoção não é suportado.
- Após exclusão confirmada, poda imediatamente nó, adjacências e traceroutes correspondentes do `topology.json` e recarrega a interface.
- Padroniza o pacote para extrair sempre no diretório **`traffic-analyzer/`**, mantendo o ZIP versionado sem acumular uma pasta de trabalho diferente para cada release.
- Mantém cores de atividade: verde até 2 h, laranja entre 2 e 24 h, vermelho acima de 24 h e cinza sem timestamp confiável.
- Mantém firmware removido, Dados técnicos amigáveis, dump JSON, arquivo SQLite, traceroutes concorrentes, Auto Zoom, pulsos e sons por viagem.
- Adiciona um painel discreto durante traceroutes animados, exibindo origem e destino, distância direta, distância total da IDA, distância total da VOLTA e o total combinado ida + volta quando ambas as pernas são conhecidas.
- Em traceroutes simultâneos, mantém uma entrada independente por animação ativa; distâncias são calculadas apenas a partir dos hops com coordenadas conhecidas, sem estimar lacunas.

## 1.12.0

- Colore os nós do mapa pela recência de atividade observada: **verde** para tráfego nas últimas 2 horas, **laranja** entre 2 e 24 horas e **vermelho** para atividade mais antiga que 24 horas; nós sem timestamp confiável ficam cinza.
- A recência usa o maior timestamp disponível entre o arquivo histórico do Traffic Analyzer (`/api/archive/nodes`) e `lastHeard` do MeshMonitor, evitando depender apenas dos pacotes carregados no navegador.
- Atualiza a legenda do mapa para explicar as faixas de atividade por tempo.
- Adiciona **Remover nó** ao popup de cada nó. A ação pede confirmação e remove o nó do banco local do MeshMonitor para a fonte configurada, preservando o histórico já arquivado em `traffic.db`.
- Após remoção bem-sucedida, o nó e as adjacências correspondentes são retirados imediatamente da topologia local; se o nó voltar a ser ouvido pelo MeshMonitor, ele poderá reaparecer.
- A remoção depende de o token configurado no Traffic Analyzer possuir a permissão de escrita exigida pelo MeshMonitor; falhas de autorização são apresentadas na interface.
- Remove totalmente a informação de **firmware** dos dados gerados e do popup dos nós, pois essa informação não é obtida de forma confiável para os nós remotos.
- Mantém Dados técnicos em formato amigável, dump JSON, histórico SQLite, Ao vivo por padrão, traceroutes concorrentes, Auto Zoom, pulsos e sons por viagem.

## 1.11.0

- Reformula a seção **Dados técnicos** do detalhe de pacote para apresentar os metadados em formato amigável, com pares rótulo/valor em vez de JSON bruto como visualização principal.
- Adiciona nomes legíveis para campos comuns, incluindo ID do pacote, tipo de telemetria, destino, direção, canal, relay, transporte, horário de recepção e indicadores MQTT.
- Destinos numéricos passam a ser exibidos como Node ID hexadecimal e, quando o nó está presente na topologia, com o nome conhecido do nó.
- Valores técnicos reconhecidos reutilizam a formatação amigável de unidades, datas, booleanos, SNR/RSSI, tensão, bateria, temperatura, umidade e pressão.
- `decoded_payload` não é duplicado em Dados técnicos, pois já aparece na seção Payload em formato amigável.
- Mantém **Ver JSON bruto** somente como diagnóstico secundário e recolhido, para troubleshooting avançado.
- Preserva integralmente os recursos da v1.10.0: dump JSON completo em ZIP, histórico SQLite, Ao vivo por padrão, traceroutes concorrentes, Auto Zoom e realce de atividade.

## 1.10.0

- Exibe a versão instalada ao lado do nome **Traffic Analyzer** no cabeçalho superior e também no título da página do navegador; o servidor lê o arquivo `VERSION` instalado para reduzir risco de divergência entre interface e pacote.
- Adiciona o botão **Baixar dump JSON (.zip)** na aba Tráfego.
- O dump contém todo o histórico persistente em um único `traffic.json`, compactado em ZIP, sem o limite de 100.000 linhas do endpoint de exportação tabular.
- O JSON inclui metadados da exportação: versão, horário de geração, fonte, quantidade de pacotes, primeiro/último timestamp, versão do esquema e aviso de privacidade.
- A geração do dump é feita por streaming para o ZIP e por lotes de SQLite, evitando carregar todo o histórico em memória.
- Adiciona `GET /api/archive/dump` com `Content-Disposition` para integração com outras ferramentas.
- Mantém a política de privacidade: mensagens diretas `TEXT_MESSAGE_APP` já chegam ao arquivo com conteúdo e metadata sensível removidos; o dump não reintroduz esses dados.
- Corrige o procedimento genérico de instalação/atualização: o bloco passa a localizar o ZIP em diretórios pessoais comuns (`$PWD`, `$HOME`, `/home` e `/root`) e funciona também quando o administrador está logado diretamente como `root`.
- O instalador passa a copiar o arquivo `VERSION` para `/opt/traffic-analyzer`, usado pelo cabeçalho da aplicação.
- Preserva os recursos da v1.9.0: Ao vivo por padrão, traceroutes concorrentes, Auto Zoom, pulsos de atividade e arquivo histórico SQLite.

## 1.9.0

- Define **Ao vivo** como modo padrão de reprodução do mapa e inicia o polling de novos traceroutes automaticamente ao abrir a interface.
- Permite **múltiplas animações de traceroute simultâneas**: um novo traceroute começa imediatamente mesmo que outro ainda esteja em curso; nenhuma animação ao vivo entra em fila aguardando a anterior terminar.
- Adiciona **Auto Zoom opcional para traceroutes**: ao iniciar uma animação, enquadra os nós envolvidos; com traceroutes simultâneos usa a área combinada e, 5 segundos após a última animação terminar, retorna ao enquadramento anterior.
- Mantém a animação ao longo das linhas de traceroute e acrescenta pulso visual nos nós conhecidos à medida que o marcador alcança origem, relays e destino/resposta.
- Amplia o realce de atividade para tráfego comum: cada pacote observado pode realçar o nó transmissor/resposta e o `relay_node` quando ele puder ser resolvido sem ambiguidade.
- Mantém a regra de não inventar hops ou relays intermediários quando o Packet Monitor não fornece evidência suficiente.
- Mantém sons separados da animação visual: o som toca somente na primeira observação de uma **nova viagem de pacote**, e cópias/retransmissões do mesmo `packet_id` não geram novos sons.
- Adiciona arquivo histórico persistente SQLite em `/var/lib/traffic-analyzer/traffic.db`, preservado entre reinicializações e atualizações.
- Na primeira execução, importa todo o tráfego ainda retido no Packet Monitor; depois sincroniza continuamente novos registros com sobreposição temporal, duas passagens por janela e deduplicação.
- Preserva a privacidade no arquivo: conteúdo e metadata de `TEXT_MESSAGE_APP` direto são removidos antes da persistência; broadcast continua disponível quando decodificado.
- Adiciona API para integração com geradores de relatório: `/api/archive/status`, `/api/archive/packets`, `/api/archive/stats`, `/api/archive/nodes`, `/api/archive/links` e `/api/archive/export` (JSONL ou CSV).
- O endpoint `/health` passa a incluir o estado do arquivo histórico.
- O serviço web passa a usar o usuário de sistema dedicado `traffic-analyzer`, com escrita restrita ao diretório persistente necessário.
- O instalador preserva `traffic.db`, acrescenta automaticamente as novas variáveis de arquivo histórico em instalações existentes e não depende de `/home/painel` nem de outro nome de usuário específico.
- Padroniza os exemplos para começar em `cd ~` e funcionar a partir do home corrente.
- Ao final da instalação, o próprio `install.sh` executa `systemctl status traffic-analyzer.timer --no-pager` e `systemctl status traffic-analyzer-map.service --no-pager`.
- Mantém o ajuste da v1.8.0 para colunas compactas na aba Tráfego e painel de detalhes usando o restante da largura disponível.

## 1.8.0

- Ajusta a aba **Tráfego** para usar colunas compactas e de largura previsível; o painel de detalhes passa a ocupar o restante da largura disponível.
- Mantém rolagem horizontal em telas menores e oculta o painel lateral quando a largura não comporta as duas áreas com legibilidade.
- Adiciona animação de **atividade em tempo real** no mapa, independente dos traceroutes.
- Realça a origem/resposta de uma nova viagem com pulso e ícone de rádio.
- Realça o `relay_node` observado com pulso amarelo quando ele pode ser resolvido sem ambiguidade para um nó posicionado.
- Não inventa relays intermediários quando o byte de relay é ambíguo ou não há posição.
- Adiciona controles em Configurações para ligar/desligar a animação, origem/resposta, retransmissor e duração do pulso.
- Altera as notificações sonoras: o áudio toca apenas no **início de uma nova viagem de pacote**, não para cada cópia/retransmissão observada.
- Usa `packet_id` (ou ID no metadata) para deduplicar a mesma viagem sonora; TX interno sem ID continua sendo tratado como nova viagem individual.
- Mantém os cinco timbres, volume e botão de teste.
- Atualiza documentação e manual com a distinção entre **som por viagem** e **animação por atividade observável**.

## 1.7.0

- Move os controles de visualização do mapa para a aba **Configurações**: janela temporal, mínimo de observações, mapa-base, brilho, cor das linhas, linhas, nós, mapa de calor, nomes curtos e somente identificados.
- Mantém no mapa apenas os comandos operacionais **Enquadrar** e **Atualizar**, junto da barra de reprodução.
- Remove a mensagem **"aguardando novo traceroute"** do modo Ao vivo; o estado ocioso passa a mostrar somente **AO VIVO**.
- Adiciona cinco perfis de som de notificação sintetizados localmente: **Plim, Campainha, Click, Duplo e Suave**.
- Mantém volume, filtro RX/TX, botão de teste e proteção anti-spam sonora.
- Mensagens `TEXT_MESSAGE_APP` em **broadcast** passam a exibir o payload no detalhe do pacote.
- Mensagens diretas continuam com o conteúdo oculto por padrão no proxy web.
- Payloads decodificados dos demais tipos passam a ser exibidos em formato amigável, com rótulos e unidades quando reconhecidos, em vez de JSON como visualização principal.
- O JSON bruto continua disponível de forma secundária, recolhido em **Dados técnicos**.
- Preferências de mapa antes posicionadas no cabeçalho passam a ser persistidas junto das demais preferências locais.
- Manual revisado para evitar extrapolação de textos em diagramas/caixas.
- O PDF agora termina com uma seção **Changelog** detalhada, sincronizada com este arquivo.

## 1.6.0

- Adiciona visualização automática de fluxo para NodeInfo dirigido.
- Pedidos NodeInfo TX registrados pelo MeshMonitor são reconhecidos imediatamente.
- NodeInfo RX remoto usa correlação ida/volta para evitar chamar toda mensagem dirigida de pedido.
- Procura traceroute completo entre os mesmos endpoints dentro de uma janela temporal de 180 s.
- Quando existe evidência, anima o fluxo pelos hops observados no traceroute.
- Quando não existe, desenha apenas linha lógica tracejada e não inventa relays.
- Adiciona botão **Mostrar fluxo** ao detalhe de NodeInfo.
- Adiciona preferência para ligar/desligar fluxo NodeInfo no mapa.
- Corrige a diagramação inicial do manual, ampliando caixas e aplicando quebra de linha controlada.

## 1.5.0

- Renomeia a aplicação para **Traffic Analyzer**.
- Adiciona aba **Tráfego** com Packet Monitor RX/TX em tempo quase real.
- Adiciona filtros, detalhes de pacote, contadores e som "plim" configurável.
- Mantém mapa/topologia/traceroutes da série anterior e migração automática.

## 1.4.0

- Adiciona reprodução cronológica de traceroutes em modo Histórico e Ao vivo.
- Anima ida e volta com velocidade visual constante e sem pausa nos nós.
- Adiciona janela **Todos** e aumenta o limite padrão de traceroutes carregados.
- Passa a preservar lacunas quando um hop é desconhecido, evitando criar adjacências RF falsas.
- Adiciona eventos por enlace para estatísticas filtradas pela janela temporal.

## 1.3.0

- Adiciona mapa de calor de atividade de roteamento.
- Adiciona controles independentes de linhas e círculos dos nós.
- Consolida manual técnico dentro do ZIP.

## 1.2.0 - 1.2.2

- Adiciona escolha de mapa-base, brilho, cor de linhas e nomes curtos.
- Define Satélite como mapa padrão e amarelo como cor padrão dos enlaces.

## 1.1.0 - 1.1.1

- Adiciona `topology.json` e interface web separada na porta 8788.
- Corrige carregamento do Leaflet e redimensionamento inicial do mapa.

## 1.0.0

- Primeira versão do serviço de descoberta por traceroutes.
- Descobre hops intermediários e classifica nós identificados, stubs e route-only.
- Implementa solicitação controlada de NodeInfo com cooldown e limite de tentativas.
