# Backlog — Traffic Analyzer

## v1.66.1 — Formatação de automações/alertas e menu de contexto

- **Concluído:** preservação de quebras de linha reais em PING/CLIMA e divisão por limite de 200 bytes sem achatar o texto.
- **Concluído:** expansão dos campos compactos de CLIMA para linguagem clara, incluindo temperatura, umidade relativa, ponto de orvalho, pressão, índice ultravioleta, iluminação, radiação solar, vento, chuva, raios e bateria.
- **Concluído:** alertas INMET multilinha e envio de avisos longos em múltiplos blocos.
- **Concluído:** fonte das opções do menu de contexto aumentada para 14 px.
- **Concluído:** primeira opção do menu é **Excluir da base e do dispositivo**, com confirmação e resultado separado das duas etapas.
- **Concluído:** favoritos do menu são sincronizados com a NodeDB do dispositivo Meshtastic conectado.
- **Validado por testes automatizados:** formatação multilinha, expansão de abreviações, alerta INMET, ordem/tamanho do menu e exclusão combinada/resultado parcial.
- **Correção v1.66.1:** normalização de raios refinada para não alterar linhas de dados já expandidas; ausência de último raio usa **sem registro**.
- Teste físico em rádio continua necessário para confirmar comportamento do firmware/dispositivo específico, sem alterar a validação lógica do código.

## v1.65.0 — Menu de contexto de nós

- Implementado clique com botão direito nas abas **Nós** e **Mapa**, reutilizando o mesmo menu e o mesmo nó selecionado.
- Implementados: mensagem privada, Node Info, posição, telemetria, Traceroute, Ping, detalhes, centralização, filtro de tráfego, cópia de campos, favoritos locais, ocultação do mapa e exclusão do histórico local.
- Exclusão local exige autenticação administrativa e confirmação; o nó pode reaparecer se o MeshMonitor voltar a fornecê-lo.
- **Concluído na v1.66.0:** adicionar/remover favoritos agora também é enviado à NodeDB do dispositivo Meshtastic.
- **Pendente:** automações persistentes específicas por nó; o menu já direciona à aba Automações, mas não registra agendamento por nó nesta release.

## v1.64.0 — Anúncios de versões Meshtastic (#73)

- Implementado monitor de estáveis, instáveis e nightly com todas habilitadas; painel, fila persistida, prévia, intervalo/modelo e diagnóstico.
- Baseline inicial sem flood; anúncios aceitos não repetidos após restart. Fontes oficiais GitHub e índice nightly. O índice contém apenas o build atual, sem histórico de builds perdidos entre consultas.
- Testes simulam fontes, reinício, duplicidade, falhas e envio via canal 0. Pendente aceite de recepção RF real; #66 permanece independente.

## v1.63.0 — Ícones por role

- Replica ícones do Mesh Analyzer para todos os 13 papéis conhecidos, com símbolo desconhecido.
- Usa role da API MeshMonitor; não infere pelo nome. Preserva atividade real no contorno, inclusive offline/histórico.
- Legenda recolhível e testes de normalização, SVG e mapa. Pendências de RF físico anteriores permanecem independentes.

Estado consolidado da release **v1.60.0** (2026-10-13), com novas solicitações registradas separadamente.

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
| 46 | [Issue #63 — Nova aba Automações com PING e CLIMA](https://github.com/alexpmr/traffic-analyzer/issues/63) | **Concluído na v1.61.0** | Nova aba superior com URLs dedicadas, controle independente, edição de respostas e parâmetros, prévia sem RF, diagnóstico e histórico; arquitetura extensível para futuras automações, persistência e proteção administrativa. |
| 47 | [Issue #65 — Mostrar rota NodeInfo por hops observados](https://github.com/alexpmr/traffic-analyzer/issues/65) | **Implementado na v1.62.0; validação por CI** | Sem linha reta quando a rota é desconhecida; desenha somente hops observados; separa notificações; traceroute manual/opt-in com comprovação de NodeInfo TX local e cooldown 5 min global/30 min por destino. |
| 48 | [Issue #66 — PING e CLIMA sem resposta RF na v1.61.0](https://github.com/alexpmr/traffic-analyzer/issues/66) | **Pendente — regressão crítica relatada** | Diagnosticar listener TCP/pacotes, configuração persistente, logs de erro e envio RF; validar com rádio físico antes de encerrar. |
| 49 | [Issue #69 — Pesquisa incremental de nós no mapa](https://github.com/alexpmr/traffic-analyzer/issues/69) | **Implementado na v1.62.0; validação por CI** | Busca a cada caractere filtra marcadores e enlaces no Mapa sem alterar banco/filtros; nomes curtos, longos, personalizados e aliases antigos realmente observados; seleção centraliza, destaca e abre detalhes; limpar restaura mapa. |
| 50 | [Issue #71 — Barra única e pesquisa permanentemente visível](https://github.com/alexpmr/traffic-analyzer/issues/71) | **Concluído na v1.62.1 (CI validado)** | Reprodução, controles, pesquisa e ações do Mapa em linha única, com campo de pesquisa sempre visível; em telas estreitas, rolagem lateral e posicionamento flutuante de menus/resultado sem cortes. |

## Próximas implementações

### Issue #71 — Barra superior do Mapa em uma linha

**Estado:** concluído na v1.62.1; testes automatizados e smoke test de navegador validados.

- Todos os controles, de Reprodução até Atualizar, permanecem **em uma única linha**. O campo de pesquisa fica **sempre visível**, sem botão de expandir/recolher.
- Ajustar `#playback`, `.mapActions`, `#playStatus` e `.mapSearchBox` para impedir `flex-wrap` e distribuir largura de maneira compacta em desktop.
- Em telas pequenas, manter a barra de altura única com rolagem horizontal, sem cortar a lista de resultados nem o menu Camadas.
- Testes de navegador em 1920/1366/1264/1024/768/390 px, busca aberta/fechada e funcionalidade dos controles preservada.

Acompanhamento: https://github.com/alexpmr/traffic-analyzer/issues/71


### Issue #69 — Pesquisa dinâmica por nomes no mapa

**Estado:** implementado no código v1.62.0, condicionado à validação CI. Pesquisa por tecla sobre nós conhecidos, ocultando marcadores e enlaces sem correspondência e mantendo os dados originais.

- Botão de **lupa no Mapa**, com filtro incremental no próprio mapa, sem Enter, usando nomes longos, curtos, de fábrica/customizados (quando observados) e aliases históricos registrados no banco. O filtro é tolerante a maiúsculas e acentos, inclui Node ID e apresenta contador de correspondências.
- Somente nós correspondentes e enlaces entre correspondentes ficam visíveis durante a pesquisa; ao limpar o campo, a visualização original é restaurada. Ao selecionar: **centralizar, ajustar zoom e pulsar marcador**, abrindo detalhes e URL `/mapa/no/<nodeNum>?busca=...`.
- Pesquisar nós **offline e históricos** do catálogo persistente: quando existir posição conhecida válida, exibir que é histórica e a idade; sem coordenadas, informar e abrir detalhes sem centralização errada.
- Manter acesso a nós escondidos pelos filtros por meio de destaque temporário, **sem modificar filtros ou falsear atividade/enlaces RF**.
- Nomes iguais resolvidos por Node ID; se nomes originais/customizados antigos não estiverem na topologia, recuperar de fonte real e preservar aliases ao longo do tempo, sem inventar identificadores.
- Controles responsivos e acessíveis; busca e seleção não transmitem RF. Testes abrangem variações de nomes, duplicatas, offline, falta de coordenadas e deep links.

Acompanhamento: https://github.com/alexpmr/traffic-analyzer/issues/69



### Issue #66 — PING e CLIMA não respondem em teste de RF

**Prioridade:** regressão operacional — diagnosticar antes das próximas funcionalidades. Testes de RF com outro nó não obtiveram resposta para nenhum dos bots na v1.61.0. Sem logs não há causa confirmada. Investigar conexão ao Virtual Node, tratamento de pacotes, carregamento do JSON de automações, cooldowns, API CLIMA e envio; exigir validação física e indicadores de saúde no painel.

Acompanhar: https://github.com/alexpmr/traffic-analyzer/issues/66


### Issue #65 — Desenhar caminho por hops observados e controlar avisos NodeInfo

**Estado:** implementado no código v1.62.0, condicionado à validação CI. Sem comprovação retroativa do caminho original do NodeInfo.

- A linha reta lógica de NodeInfo foi removida: na ausência de traceroute, apenas destaca os marcadores de origem/destino, sem transformar a relação lógica em RF direto.
- Quando existir traceroute com rota e coordenadas confiáveis, **desenhar a sequência real de hops observados**, destacando os intermediários e a hora da medição. Ressalvar que o caminho é do traceroute, não prova do percurso do pacote NodeInfo.
- Sem traceroute, mostrar apenas origem/destino e status **caminho desconhecido**, sem linha reta. Se faltarem coordenadas de hops, mostrar a sequência textual e somente segmentos espacialmente confirmados, nunca fechar lacunas com reta fictícia.
- Oferecer **Descobrir rota agora** e modo **traceroute automático opcional** (desativado por padrão) antes de exibir o resultado, somente quando a origem da consulta torna a medição relevante; priorizar traceroute histórico. Aplicar autenticação, limite inicial sugerido de 30 min por destino e máximo 1 consulta automática a cada 5 min, controle de airtime, concorrência e auditoria. Nunca afirmar que um traceroute do coletor é o caminho exato do NodeInfo entre terceiros.
- Melhorar o texto informativo e distinguir estados: em busca, rota histórica correlacionada, não encontrada, erro real.
- Configurar os avisos flutuantes separadamente da opção existente **Mostrar fluxo de NodeInfo no mapa**; reduzir repetições e conservar diagnóstico acessível.
- Preservar distinção entre ligação lógica e enlace RF confirmado, sem inventar hops ou alterar Ranking.
- Acompanhar: https://github.com/alexpmr/traffic-analyzer/issues/65


### Issue #63 — Aba superior Automações: PING e CLIMA

**Estado:** implementado na v1.61.0, com testes automatizados e smoke test web. Validação física em RF permanece recomendada.

- **Navegação:** nova aba superior `Automações`, rota `/automacoes`, detalhes `/automacoes/ping` e `/automacoes/clima`, com F5/favoritos/Voltar-Avançar.
- **Visão geral:** cartões independentes para PING e CLIMA, status, última execução, erro recente e ações de edição/teste; catálogo preparado para outras automações.
- **PING:** ligar/desligar individualmente, identificação, cooldown, timeout do traceroute, edição segura do conteúdo/campos da resposta e prévia do resultado com limites de payload Meshtastic.
- **CLIMA:** ligar/desligar individualmente, cooldown, endereço/saúde da API Tempest, intervalo entre mensagens, apresentação dos dados meteorológicos e prévia.
- **Observabilidade:** histórico e diagnóstico por bot, aproveitando `mesh_command_events`, separando comando recebido, geração de resposta, tentativa de envio e falha; sem expor dados privados.
- **Segurança de operação:** testes de prévia não transmitem RF; envio de teste exige confirmação explícita. `sendText` não comprova entrega.
- **Persistência:** configurações editadas via interface preservadas em `/var/lib/traffic-analyzer`, sem alteração manual dos scripts, com migração dos defaults existentes, controles de acesso e CSRF.
- **Compatibilidade:** PING e CLIMA atuais seguem operando como na v1.60.0 até alteração pelo operador, sem duplicação de bots/listeners ou regressões dos comandos.
- **Arquitetura extensível:** registro de automações e componentes reutilizáveis, permitindo acrescentar novas rotinas sem transformar a aba em um painel específico de PING/CLIMA.
- **Aceite:** testes de isolamento entre os bots, configuração persistente, roteamento por URL, autorização, preview sem RF e regressão do listener e respostas reais.

Detalhamento e acompanhamento: https://github.com/alexpmr/traffic-analyzer/issues/63

## Política após v1.60.0

- Novos pedidos entram como novos itens de backlog ou issues.
- Correções de regressão têm prioridade sobre novas funcionalidades.
- O histórico bruto pode obedecer retenção; a memória consolidada de nós/enlaces só é removida por reset explícito do banco.
- Rankings RF nunca devem inferir enlace direto a partir de uma rota multihop sem evidência física do hop.
- Ações administrativas continuam protegidas pela autenticação/CSRF existentes.

**Backlog funcional da v1.62.1: #50/issue #71 concluído em código e CI; #48/issue #66 continua aberto aguardando teste físico RF de PING/CLIMA.**
