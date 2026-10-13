# Backlog — Traffic Analyzer

Estado consolidado da release **v1.60.0** (2026-10-09).

Esta matriz registra o fechamento do backlog funcional até a v1.60.0. Um item só é tratado como concluído quando existe implementação no código e validação correspondente no pipeline, quando aplicável.

| # | Item | Estado | Evidência / critério |
|---:|---|---|---|
| 1 | Persistência permanente dos nós | Concluído | `topology_nodes` mantém nós observados até reset explícito do banco. |
| 2 | Persistência permanente dos enlaces | Concluído | `topology_edge_events` e agregados históricos preservam hops observados até reset do banco. |
| 3 | Nós não podem desaparecer do mapa por registro histórico incompleto | Concluído | Validação de posição impede `Invalid LatLng` sem eliminar nós válidos. |
| 4 | Diferenciar visualmente nós recentes/antigos | Corrigido na v1.56.0 | Idade baseada em tráfego realmente originado pelo nó e `lastHeard`; `lastSeenMs` de topologia não renova atividade. Verde, amarelo/laranja, vermelho e cinza preservados. |
| 5 | Retenção do tráfego: 1 dia, 1 semana, 1 mês ou nunca | Concluído | `archiveRetentionDays`; padrão **Nunca apagar**; não remove memória de nós/enlaces. |
| 6 | Top 10 enlaces RF mais longos | Concluído | Estatísticas → **Ranking** e endpoint `/api/archive/rf-longest-links`. |
| 7 | Ranking considerar somente hop RF direto | Concluído | Exige evidência RF/SNR válido e consolida A↔B; não inventa A↔C em rota A→B→C. |
| 8 | Aba Nós abrir detalhes completos do nó | Concluído | Clique na linha abre `openNodeDetailsModal`, reutilizando o mesmo conteúdo/lógica do popup. |
| 9 | Detalhes: identificação, posição, RF, routing, traceroute, firmware e energia | Concluído | Visão compartilhada de metadados e consultas do nó. |
| 10 | Nome do nó clicável em Mensagens | Concluído | `.msgSenderNode` abre a mesma visualização ampliada do nó. |
| 11 | Mensagens: Carregar anteriores / Atualizar | Concluído | Handlers dedicados e preservação da posição de rolagem. |
| 12 | Mensagens: sem popup invasivo; aba sinaliza não lidas | Concluído | Badge/animação `messagesNav.unread`; novas mensagens não abrem modal. |
| 13 | Progresso individual por consulta | Concluído | Estado e barra independentes por ação: envio, espera, resposta, erro, timeout e indisponível. |
| 14 | Mostrar cada resposta assim que chegar | Concluído | Polling/correlação atualizam o painel por consulta sem aguardar as demais. |
| 15 | Botão Tudo disparar consultas em uma única rodada | Concluído na v1.50.0 | Despacho concorrente com `Promise.allSettled`; nenhuma consulta espera timeout/resposta da anterior para iniciar. |
| 16 | Popup/painel do nó arrastável, redimensionável e expansível | Concluído | Janela destacável com drag, resize, maximização/restauração. |
| 17 | Relatórios e exportações | Concluído na v1.50.0 | Estatísticas → **Relatório / PDF** e **Exportar CSV**; APIs JSONL/CSV e dump ZIP permanecem disponíveis. |
| 18 | Ranking de interações por chat | Concluído | Saúde da Rede e Estatísticas → Chat usam histórico acumulado do canal primário. |
| 19 | Detecção automática de versão | Concluído | Worker de atualização estável em background. |
| 20 | Popup de novidades após atualização | Concluído | Exibição uma vez por versão e por navegador/perfil. |
| 21 | Download simples da versão em ZIP | Concluído | `traffic-analyzer-latest.zip` e ZIP versionado publicados automaticamente. |
| 22 | Instalação documentada sem exigir Git | Concluído | README contém download, descompactação e instalação pelo ZIP. |
| 23 | Issue #37 — Acessos na mesma faixa do cabeçalho de Estatísticas | Concluído na v1.50.0 | Controles contextuais de Acessos ficam em `.statsHeader`; a segunda barra horizontal foi removida. |
| 24 | Issue #39 — Ajustar os dois blocos de Estatísticas/RF para eliminar rolagem horizontal | Concluído na v1.51.0 | Ranking e enlaces observados usam tabelas fluidas sem largura mínima forçada, eliminando overflow horizontal em desktop normal. |
| 25 | Issue #39 — Criar subaba Ranking em Estatísticas | Concluído na v1.51.0 | Subaba **Ranking** criada; Top 10 movido de RF, mantendo ordenação, critério RF direto e clique para isolamento no mapa. |
| 26 | Issue #39 — Ajustar os dois blocos de Estatísticas/Routing para eliminar rolagem horizontal | Concluído na v1.51.0 | **Distribuição por hops** e **Nós intermediários observados** usam tabelas fluidas, sem barra inferior em desktop, e empilham responsivamente em telas menores. |
| 27 | Issue #40 — Estatísticas: renomear Anomalias para Pontos de atenção | Concluído na v1.51.0 | A interface passa a exibir **Pontos de atenção** nos rótulos, títulos, cartões, resumo e ajuda, mantendo algoritmo, severidades, filtros e dados. |
| 28 | Issue #41 — Estatísticas: manter barra de subabas visível durante rolagem | Concluído na v1.51.0 | Estatísticas usa um único contêiner de rolagem e mantém a barra superior sticky, inclusive em **Pontos de atenção** com conteúdo longo. |
| 29 | Issue #43 — Ranking RF: exigir evidência real de zero saltos | Concluído na v1.52.0 | O Top 10 exige `direct_evidence=1`: **adjacência explícita** na rota ou confirmação independente de **zero saltos**. `transport='rf'` + SNR não basta e `route=[]` ambígua é excluída. |
| 30 | Issue #45 — Ranking RF: corrigir evidência histórica falsa | Concluído na v1.53.0 | O Ranking confia somente em `route-adjacency-api` gerado pela API `/traceroutes`; pacotes brutos TX/RX e TTL não promovem enlaces. Evidências legadas da v1.52.0 são invalidadas automaticamente sem apagar a topologia. |
| 31 | Issue #47 — Ranking RF: incluir enlaces históricos válidos de nós offline | Corrigido definitivamente na v1.55.0 | A v1.54.0 tentou recuperar o histórico via `/api/analysis/traceroutes`, mas a autenticação Bearer dessa rota era inadequada. A v1.55.0 usa a API v1 autenticada com expansão progressiva do limite e preserva evidências revalidadas no `traffic.db`. |
| 32 | Issue #49 — Ranking RF: backfill v1.54 usa endpoint que ignora MM_API_TOKEN | Concluído na v1.55.0 | O backfill usa `/api/v1/sources/{source}/traceroutes` autenticado por Bearer token, expande progressivamente o `limit` e usa a migração `topology-direct-history-v4` para repetir a recuperação mesmo após falso `complete=true` da v1.54.0. |
| 33 | Issue #51 — Mapa: cor dos nós deve refletir tráfego real | Concluído na v1.56.0 | `nodeLastTrafficMs()` usa somente tráfego arquivado realmente originado pelo nó e `lastHeard`; `lastSeenMs` e atualizações administrativas da topologia não renovam cor/Último tráfego. |
| 34 | Issue #52 — Ranking RF: alguns enlaces históricos diretos válidos ainda ficam de fora | Concluído na v1.56.0 | Pares RF sem evidência confiável são reconciliados individualmente pela API autenticada de histórico do par; Ranking inclui todo hop direto comprovado e a nova auditoria informa o motivo de exclusão dos demais. |
| 35 | Ranking RF: usar o mesmo critério RF confirmado do mapa | Concluído na v1.57.0 | Todo hop persistido com `transport='rf'` + SNR válido entra no Ranking quando há posição nos dois extremos; `route-adjacency-api` permanece como evidência adicional, não como requisito. Corrige casos como Perseverance ↔ PT2TSP-3. |
| 36 | Ranking RF: não reintroduzir falsos diretos ao alinhar com o mapa | Concluído na v1.57.1 | Hops RF/SNR continuam elegíveis sem traceroute histórico; porém, se a consulta autenticada do par comprovar somente rotas multi-hop, o par é marcado como `multihop_confirmado` e excluído. Histórico vazio não é evidência negativa. |
| 37 | Mapa-base sem fundo / `API KEY REQUIRED` | Concluído na v1.58.0 | CARTO removido; Claro/Escuro usam OSM com filtro local sem chave; fallback automático entre provedores sem credenciais preserva mapa, zoom, nós e enlaces. |
| 38 | Migrar bot PING para dentro do Traffic Analyzer | Concluído na v1.59.0 | Worker integrado no canal primário, cooldown, traceroute, RSSI/SNR/hops, contagem de nós e identidade usando Long Name + Short Name + Node ID. |
| 39 | Migrar bot CLIMA para dentro do Traffic Analyzer | Concluído na v1.59.0 | Worker integrado chama a API Tempest local, preserva mensagens curtas e intervalo de 8 s; bot externo é desativado, API meteorológica permanece como fonte. |
| 40 | PING mostrar nomes configurados pelo usuário | Concluído na v1.59.0 | Origem prioriza Long Name e Short Name do cadastro conhecido do nó, usando Node ID apenas como referência técnica. |
| 41 | PING/CLIMA integrados não respondiam na rede real | Corrigido na v1.59.1 | Worker usa API de mensagens + fallback no tráfego RX arquivado em traffic.db; CLIMA API é explicitamente iniciada pelo instalador quando disponível. |
| 42 | PING por RF não retornava após a migração | Corrigido na v1.59.2 | Listener em tempo real pelo Virtual Node com TCPInterface + meshtastic.receive.text; suporta mensagens diretas e broadcast sem persistir texto privado no traffic.db. |
| 43 | PING/CLIMA recebidos, mas resposta não retornava por RF | Corrigido na v1.59.3 | Respostas passam a usar TCPInterface.sendText no próprio listener Meshtastic, canal 0 e broadcast ^all, replicando o bot legado. |
| 44 | Listener RF não recebia TEXT_MESSAGE_APP em meshtastic.receive.text | Corrigido na v1.59.4 | Listener passa a usar meshtastic.receive e filtrar TEXT_MESSAGE_APP, conforme teste real no servidor. |
| 45 | URLs completas/dedicadas por tela, subaba e contexto navegável | Concluído na v1.60.0 | Rotas reais com History API, refresh/favoritos/Voltar-Avançar, deep links para Nós e Mapa e filtros relevantes em query string. |

## Política após v1.60.0

- Novos pedidos entram como novos itens de backlog ou issues.
- Correções de regressão têm prioridade sobre novas funcionalidades.
- O histórico bruto pode obedecer retenção; a memória consolidada de nós/enlaces só é removida por reset explícito do banco.
- Rankings RF nunca devem inferir enlace direto a partir de uma rota multihop sem evidência física do hop.
- Ações administrativas continuam protegidas pela autenticação/CSRF existentes.

**Backlog conhecido após a v1.60.0: nenhum item funcional pendente nesta matriz.**
