# Traffic Analyzer v1.32.0

**Traffic Analyzer** é uma aplicação complementar ao MeshMonitor para análise de topologia e tráfego Meshtastic. Ela usa a API v1 do MeshMonitor como fonte de dados, não disputa a conexão serial/TCP com o rádio e mantém um histórico próprio para relatórios.

## Novidades da v1.32.0

- Nova aba superior **Nós**, com inventário dos nós conhecidos pelo MeshMonitor.
- A tabela principal mostra **Nome longo, Nome curto, Role, Hardware, Saltos, Bateria, Tensão, Distância, SNR, Última interação e Última posição**.
- Colunas técnicas opcionais podem ser ativadas pelo menu **Colunas**: **RSSI, Utilização do canal, Air Util TX, Node ID, PKC e Estado**.
- Todos os títulos das colunas são clicáveis e alternam ordenação **crescente/decrescente**, com ordenação numérica real para saltos, bateria, distância, SNR e timestamps.
- **Última interação** usa tempo relativo compacto (`30 s`, `10 min`, `3 h`, `2 d`) e semáforo: **verde até 1 h**, **amarelo de mais de 1 h até 12 h** e **vermelho acima de 12 h**; sem timestamp fica neutro.
- A idade das interações é atualizada automaticamente enquanto a aba permanece aberta.
- A distância é calculada em linha reta a partir do **nó local da fonte MeshMonitor**, identificado pela API v1 de status da própria fonte.
- Clicar em um nó abre seu detalhe; quando ele possui marcador visível, o Traffic Analyzer leva ao mapa e abre o mesmo popup. Nós sem marcador podem ser consultados em um modal de detalhes.
- O popup do nó passa a exibir **nome amigável do hardware**, seguindo a enumeração HardwareModel utilizada pelo MeshMonitor/Meshtastic (por exemplo, `110 → Heltec V4`, `43 → Heltec V3`).
- Roles numéricas também passam a ser apresentadas por nome amigável.
- O popup aberto é **preservado durante as atualizações periódicas da topologia** e mantém sua posição de rolagem, evitando o fechamento automático observado nas versões anteriores.
- O checklist das consultas continua marcando **✓ verde somente quando uma resposta nova é efetivamente observada no MeshMonitor**; envio aceito sem resposta permanece aguardando.
- Todos os percentuais exibidos no popup, metadados e tabela de nós passam a usar **1 casa decimal**, respeitando vírgula em Português e ponto em English.
- Mantém todas as funções da v1.31.0, incluindo download direto da Latest Release pelo indicador superior.

## Novidades da v1.31.0

- O popup dos nós passa a usar um layout **mais largo, em paisagem**, aproveitando melhor a largura da tela.
- Os metadados são organizados em **duas duplas campo/valor por linha** em telas grandes, reduzindo bastante a altura total do popup.
- O checklist das consultas também passa a usar duas colunas no desktop, e a área de últimos metadados pode distribuir registros em duas colunas.
- O popup recebe **rolagem interna vertical** e limite de altura relativo à janela; quando o conteúdo exceder a tela, o mapa permanece parado e somente o popup rola.
- Em telas médias e pequenas o layout retorna automaticamente para uma coluna, mantendo a interface responsiva.
- A troca de idioma no cabeçalho passa a aparecer como um **único menu pull-down** compacto, mantendo 🇧🇷 Português e 🇺🇸 English e preservando a preferência no navegador.
- Quando existir uma **Latest Release estável mais recente**, o indicador de versão no topo passa a mostrar **BAIXAR**. Clicar nele inicia diretamente o download do ZIP versionado publicado naquela Release.
- O servidor identifica o asset exato `traffic-analyzer-vX.Y.Z.zip`, usando `traffic-analyzer-latest.zip` apenas como fallback da mesma Latest Release.
- Quando não houver atualização, clicar no indicador continua abrindo as informações da versão instalada.
- O `install.sh` agora **encerra de forma controlada a interface e o ciclo agendado da versão anterior antes de substituir os arquivos**, evitando atualização sobre uma instância em execução.
- Após a instalação, os serviços são habilitados novamente, a topologia é regenerada e a interface retorna normalmente.
- Configurações, token do MeshMonitor, autenticação, `traffic.db`, estado e demais dados persistentes continuam preservados.

## Novidades da v1.30.0

- O popup de cada nó passa a funcionar como um **painel completo de diagnóstico**, mostrando tanto as informações disponíveis quanto os campos ainda ausentes.
- Cada metadado esperado recebe um indicador visual: **✓** quando existe informação e **☐** quando o MeshMonitor ainda não possui o dado.
- O popup mostra **latitude, longitude e coordenadas combinadas**, altitude e data/hora da última posição quando disponíveis.
- Passam a ser exibidos, entre outros dados: Node ID, nomes, hardware, role, firmware, status, posição, precisão GPS, hops, SNR/RSSI, canal, bateria, tensão, utilização de canal, Air Util TX, uptime, reboots, Store & Forward e disponibilidade de PKC.
- Nova seção **Consultas ao nó**, com ações individuais para **Node Info, Position, Device Metrics, Environment Metrics, Air Quality, Power Metrics, Neighbor Info e Traceroute**.
- Novo botão **Tudo** executa as consultas em sequência, com pequeno espaçamento para reduzir rajadas de tráfego na malha; **Traceroute é enviado por último**.
- O checklist da consulta muda conforme o processamento: não consultado, aguardando resposta, **✓ respondido**, timeout, erro ou não suportado/não aplicável.
- Enquanto o popup permanece aberto, o Traffic Analyzer consulta o MeshMonitor periodicamente e mostra os metadados à medida que as respostas chegam.
- As consultas usam os **endpoints oficiais do MeshMonitor**. Assim, as respostas são recebidas, processadas e persistidas pelo MM como nas consultas iniciadas por ele próprio; o Traffic Analyzer não cria um NodeDB paralelo.
- Neighbor Info respeita as restrições do MeshMonitor, inclusive consulta apenas a nó local/0-hop e rate limit do firmware quando aplicáveis.
- As transmissões iniciadas pelo popup são tratadas como ações de escrita e continuam protegidas pelo **login administrativo + CSRF** do Traffic Analyzer.
- O mapa, a distinção RF/MQTT-não-RF, as animações, o chat e os demais recursos da v1.29.0 permanecem preservados.

## Novidades da v1.29.0

- O mapa passa a distinguir a evidência de transporte **por trecho do traceroute**, em vez de classificar toda a rota apenas pelo modo em que o registro chegou ao VHF3/MeshMonitor.
- **Enlace com pelo menos uma observação RF no período:** linha contínua.
- **Enlace com somente observações MQTT/não-RF no período:** linha tracejada.
- Exemplo: se `A → B` usar MQTT/não-RF e `B → VHF3` for confirmado por RF, o mapa mostra `A ╌╌ B ── VHF3`.
- Quando um mesmo enlace tiver observações RF e MQTT/não-RF, ele permanece contínuo porque existe evidência RF real; o popup informa separadamente as quantidades de observações RF e MQTT/não-RF.
- O popup do enlace passa a mostrar classificação, total de observações, composição RF/MQTT-não-RF e SNR conhecido.
- A legenda do mapa passa a explicar linha contínua, linha tracejada e o comportamento de enlaces mistos.
- Em **Configurações → Mapa e topologia**, RF e MQTT/não-RF ganham controles independentes de **cor e espessura**.
- Padrões: RF `#ffff00`, 3 px; MQTT/não-RF `#ff8c42`, 3 px, tracejado.
- As novas preferências seguem a política da v1.28.0: visitante pode alterá-las apenas localmente; administrador pode gravá-las como padrão global.
- A classificação por hop segue a semântica atual do MeshMonitor: o sentinel de SNR desconhecido do firmware é tratado como MQTT/não-RF para visualização. Esse sentinel também pode ocorrer por decrypt failure, relay role ou firmware antigo; portanto a legenda usa **MQTT/não-RF**, e não “MQTT comprovado”.

## Novidades da v1.28.0

- Visitantes sem login passam a poder **explorar e personalizar a interface localmente**: tema claro/escuro, mapa-base, brilho, filtros visuais, cor/espessura das linhas, exibição de nós e nomes, heatmap, animações, sons e aparência das mensagens.
- Essas escolhas são gravadas apenas no **`localStorage` daquele navegador**. Um visitante não altera o servidor nem muda a tela de outros usuários.
- Continuam exigindo login administrativo todas as ações de escrita: **enviar/responder/reagir a mensagens**, forçar refresh administrativo da topologia, alterar auto-update, disparar atualização e modificar o padrão global.
- O administrador ganha o botão **Usar minha configuração visual atual como padrão dos visitantes**. Esse padrão é salvo no servidor e passa a ser a apresentação inicial para navegadores que ainda não possuem personalização local.
- Se um visitante criar suas próprias preferências, elas prevalecem somente naquele navegador. O botão **Restaurar padrão do administrador** apaga o override local e volta ao padrão global.
- O padrão global fica em `/var/lib/traffic-analyzer/ui-defaults.json` por padrão e é exposto para leitura em `GET /api/ui-defaults`. A gravação usa `POST /api/ui-defaults`, protegida pela mesma sessão administrativa e CSRF das demais operações sensíveis.
- O backend aceita somente campos visuais conhecidos e valida faixas, tipos e enumerações antes de persistir qualquer valor.

### Regra de permissão da v1.28.0

**Visitante:** leitura + personalização visual local.  
**Administrador:** tudo acima + mensagens, operações administrativas, atualização e definição do padrão global.

Essa separação permite publicar o painel para consulta e exploração sem entregar capacidade de transmitir para a malha ou modificar o servidor.


## Correção da v1.27.1

- Corrige o mapa-base **Ruas (OSM)** que passou a exibir tiles 403 "Access blocked" após a v1.27.0.
- A causa era dupla: a aplicação ainda usava o formato antigo com subdomínios `{s}.tile.openstreetmap.org` e a nova camada de segurança da v1.27.0 enviava `Referrer-Policy: same-origin`, impedindo o navegador de enviar Referer ao servidor de tiles.
- O endpoint OSM passa a usar exatamente `https://tile.openstreetmap.org/{z}/{x}/{y}.png`.
- O cabeçalho de segurança passa a usar `strict-origin-when-cross-origin`, preservando proteção de privacidade sem bloquear o Referer exigido em requisições web cross-origin.
- Se o OSM falhar repetidamente, o mapa muda temporariamente para **Claro (CARTO)** para evitar uma tela em branco. A escolha manual continua disponível em Configurações.
- Mantém autenticação, modo somente leitura, Mensagens e demais recursos da v1.27.0.

## Novidades da v1.27.0

- Remove a aba **Tracklog** da interface, seus controles, mapa e JavaScript específico. O histórico de posições continua preservado em `traffic.db` para relatórios e análises futuras, mas não é mais exposto por uma aba ou endpoint público.
- Adiciona **autenticação administrativa** para permitir exposição controlada da interface na internet.
- Sem login, a aplicação opera em **modo somente leitura**: Mapa, Tráfego, Mensagens, Saúde da Rede, Anomalias e Ajuda continuam disponíveis.
- Sem login, a aba **Configurações** permanece visível, porém seus campos e botões ficam bloqueados.
- Sem login, **Mensagens** permanece para leitura, mas envio, respostas, reações e compositor ficam bloqueados.
- Todas as APIs de escrita também são protegidas no servidor; não é apenas um bloqueio visual.
- Sessões administrativas usam cookie **HttpOnly + SameSite=Strict**, expiração configurável e proteção **CSRF**.
- Adiciona limitação contra tentativas repetidas de login.
- A senha não é armazenada em texto puro: é mantida como hash **PBKDF2-SHA256** com salt e 600.000 iterações.
- Adiciona o comando `sudo traffic-analyzer-set-password` para definir ou trocar usuário/senha e reiniciar a interface.
- Em atualização de instalações existentes, a autenticação é ativada em modo seguro; enquanto nenhuma senha tiver sido definida, operações de escrita permanecem bloqueadas.
- Para publicação na internet, use HTTPS em um **reverse proxy** como Caddy, Nginx ou Cloudflare Tunnel. O Traffic Analyzer não implementa TLS diretamente.
- Quando `TA_AUTH_SECURE_COOKIE=auto`, o cookie recebe a flag Secure quando o proxy informa `X-Forwarded-Proto=https`.
- O acesso público não autenticado não pode disparar atualização de topologia, alterar auto-update nem provocar uma atualização automática.
- Mantém as correções de Mensagens da v1.26.0, incluindo rolagem preservada, emojis maiores, fallback de reação e som diferenciado.

### Ativar o login administrativo

Após instalar/atualizar para a v1.27.0, execute no servidor:

```bash
sudo traffic-analyzer-set-password
```

Informe o usuário administrador e a senha duas vezes. O utilitário grava somente o hash em `/etc/traffic-analyzer-map.env`, aplica permissão `0600` ao arquivo e reinicia `traffic-analyzer-map.service`.

Até esse passo ser concluído, com `TA_AUTH_ENABLED=true`, a aplicação continua acessível para consulta, porém em modo somente leitura.

## Novidades da v1.26.0

- A aba **Mensagens** deixa de forçar a rolagem para o fim durante as consultas automáticas. Se você subir para ler mensagens antigas, a posição permanece estável.
- Quando novas mensagens chegam enquanto você está acima do final da conversa, aparece o botão **↓ Novas mensagens**. Clicar nele leva ao fim e reativa o auto-scroll.
- **Carregar anteriores** preserva o ponto de leitura, sem pular para mensagens mais recentes.
- Emojis do seletor e das reações ficam maiores e mais fáceis de visualizar.
- Corrige o erro **HTTP 403** ao reagir quando o token consegue enviar mensagens pela API v1, mas o endpoint legado de tapback não reconhece a mesma permissão por fonte.
- Reações continuam tentando primeiro o **tapback Meshtastic nativo**. Se somente esse endpoint retornar 403, o Traffic Analyzer envia automaticamente uma **resposta emoji compatível com replyId**, evitando perder a ação.
- A notificação sonora de **nova mensagem** passa a ter assinatura própria em cada tema e usa um controle de repetição separado dos sons de roteamento, para não ser abafada por uma sequência de relays/traceroutes.
- Reações recebidas não disparam a campainha de nova mensagem; apenas mensagens reais geram essa notificação.
- Mantém replies, emojis, reações, múltiplos pacotes simultâneos no mapa e todos os recursos das versões anteriores.

## Correções da v1.25.1

- Mantém todos os recursos funcionais da v1.25.0.
- Corrige o manual PDF para substituir emojis sem suporte pela fonte por descrições textuais, eliminando quadrados/glifos quebrados.
- Remove do manual a instrução em linha do atualizador e orienta a atualização pela interface em **Configurações > Atualizações**.

## Novidades da v1.25.0

- A aba **Mensagens** agora permite **responder diretamente a uma mensagem** usando o `replyId` nativo do Meshtastic/MeshMonitor.
- A resposta mostra, dentro do novo balão, o remetente e um trecho da mensagem original quando ela está carregada.
- Adiciona **seletor de emojis** ao compositor de mensagens.
- Adiciona **reações Meshtastic/tapback** nas mensagens recebidas, com atalhos 👍 👎 ❤️ 😂 😮 😢.
- Reações iguais são agrupadas sob a mensagem original com contador quando houver mais de uma.
- Pacotes de reação não aparecem como mensagens isoladas na conversa; são vinculados ao `replyId` correspondente.
- O autocomplete por `@` permanece disponível para localizar um nó, mas o nome selecionado é inserido sem o caractere `@`.
- O mapa em **Ao vivo** mantém múltiplos traceroutes/pacotes animados simultaneamente.
- O **Histórico** passa a iniciar traceroutes conforme sua ordem temporal e permite vários pacotes percorrendo a malha ao mesmo tempo.
- Não há limite artificial de quantidade de pacotes/traceroutes em trânsito, tanto no modo ao vivo quanto no histórico. Filas pausadas também não descartam eventos por quantidade.
- Pausar congela todas as animações ativas; retomar continua todas. Alterar a velocidade afeta animações que já estão em andamento e também a linha do tempo do histórico.
- O status do mapa mostra quantos pacotes estão em trânsito ou congelados.
- Intervalos históricos curtos são preservados; janelas muito longas são comprimidas proporcionalmente para uma reprodução observável sem serializar os pacotes.
- Continua valendo a regra de não inventar hops: somente caminhos realmente observados são animados como rota.

## Correções da v1.24.1

- Mantém todos os recursos da v1.24.0 e corrige detalhes da sonificação.
- O tema **Silencioso** não produz áudio nem mesmo no botão de teste.
- Quando a primeira observação de uma viagem já inclui um relay conhecido, o tema pode reproduzir o lançamento e depois o ricochete desse relay, respeitando os limites de densidade/intervalo.
- O manual PDF passa a substituir emojis de bandeiras por texto compatível, evitando glifos quadrados em leitores sem suporte a emoji.

## Novidades da v1.24.0

- Novo sistema de **temas sonoros**: **Fliperama anos 70**, **Formal**, **Rádio / Telecom** e **Silencioso**.
- No tema Fliperama anos 70, o início de uma viagem usa efeito de lançador mecânico; relays observados usam ricochete metálico; chegada/ACK usa alvo/pontuação; falhas usam efeito grave de bola perdida.
- Traceroutes sonorizam apenas os nós e hops realmente observados na animação, sem inventar retransmissões.
- Novos controles de **densidade sonora**, intervalo mínimo, máximo de sons simultâneos, sons de roteamento, mensagens, alertas e estéreo espacial opcional.
- O botão **Testar tema** executa uma pequena sequência de lançamento, ricochetes, chegada e pontuação.
- Mensagens novas podem usar o tema de som escolhido; falhas de envio usam o perfil de alerta.
- No popup de versão, remove o comando de atualização em linha e troca **Verificar agora** por **Continuar**, que apenas fecha a janela.
- O popup de novidades mantém **Ver Release no GitHub** e **Fechar**, sem botão de atualização.
- As notas de Release mostradas no popup deixam de exibir o Markdown bruto da seção de screenshots.
- O seletor da página principal mostra **🇧🇷 Português** e **🇺🇸 English**, sem abreviações BR/US/ENG.
- Mantém os recursos anteriores de filtros de anomalias, aparência do chat, espessura das linhas e auto-update seguro.

## Correção crítica da v1.23.1

- Corrige a falha de inicialização do JavaScript que deixava a **v1.23.0 sem dados e com as abas inoperantes**.
- A causa era uma vírgula ausente na tabela de internacionalização, que produzia uma entrada `undefined` e interrompia a execução antes da inicialização da navegação.
- Adiciona e mantém um **smoke test real em Chromium** que abre a aplicação e testa a troca entre as abas principais, impedindo que esse tipo de regressão seja publicado novamente.
- Os recursos introduzidos na v1.23.0 permanecem inalterados.

## Novidades da v1.23.0

- Seletor de idioma com **🇧🇷 Português** e **🇺🇸 English**.
- O autocomplete por **@** continua disponível no compositor, mas o caractere **@ é removido antes da transmissão**; a malha recebe apenas o nome do nó.
- Configurações de leitura do chat: família da fonte, tamanho, negrito, itálico, sublinhado, altura de linha e espaçamento entre mensagens. Tudo é apenas visual e não altera o texto Meshtastic.
- Filtro de severidade em **Anomalias**: Todas, Críticas, Atenção e Informativas.
- Mapa: controle da **espessura** das linhas, junto da cor, com **Restaurar padrão**.
- **Auto-update opcional**: ao detectar uma nova Latest Release estável, a aplicação cria uma solicitação para um serviço systemd dedicado.
- O updater valida que a Release é estável, baixa o ZIP oficial por HTTPS, confere o digest SHA-256 quando fornecido pelo GitHub, cria backup, instala, verifica `/health` e pode executar rollback.
- Lock em `/run` impede duas atualizações simultâneas.
- Novo status de atualização em Configurações e botão **Atualizar agora**.
- Na primeira abertura após trocar de versão, aparece um popup **Traffic Analyzer atualizado** com as novidades; ele é mostrado uma única vez por versão.
- [Baixar o manual PDF da v1.23.0](./Documentacao_Traffic_Analyzer_v1.23.0.pdf)

## Novidades da v1.22.0

- **Interface bilíngue PT-BR / EN**, com **Português como padrão**.
- Novo seletor **Idioma / Language** no topo da aplicação; a escolha é salva no navegador.
- A troca é imediata e cobre navegação, abas, Configurações, Tracklog, Tráfego, Mensagens, Saúde da Rede, Anomalias, indicador de versão, estados de reprodução/pausa, botões, filtros, legendas, tooltips, popups e mensagens operacionais.
- Datas e números exibidos pela interface passam a respeitar o locale selecionado.
- Nomes dos nós, mensagens dos usuários, IDs, valores brutos de protocolo e notas de Release permanecem como dados de origem e não são artificialmente traduzidos.
- Nova aba **Ajuda / Help**, também integralmente bilíngue, com instruções de uso da ferramenta: mapa, Histórico/Ao vivo, pausa e backlog, Tracklog, Tráfego, Mensagens e @menções, Saúde da Rede, Anomalias, Configurações, idioma, versão/atualização e limites de interpretação.
- A internacionalização usa uma camada central de tradução e um observador de alterações da interface para cobrir também conteúdos gerados dinamicamente.
- Mantidos Tracklog, @menções, tema Claro/Escuro, indicador de versão e represamento de animações das versões anteriores.
- Mantidos os screenshots anonimizados no README e nas notas da Release.
- [Baixar o manual PDF da v1.22.0](./Documentacao_Traffic_Analyzer_v1.22.0.pdf)

## Novidades da v1.21.0

- Nova aba **Tracklog** para acompanhar o deslocamento histórico das estações móveis.
- O Traffic Analyzer passa a extrair posições reais de pacotes `POSITION_APP` e armazená-las de forma persistente em `traffic.db`.
- Na primeira execução da v1.21.0, posições já existentes no histórico de pacotes são reconstruídas automaticamente quando houver metadata decodificada disponível.
- O Tracklog permite filtrar por **1 h, 6 h, 24 h, 7 dias ou 30 dias**, selecionar um nó específico ou visualizar todos os nós com mobilidade observada.
- O mapa mostra trajetória, pontos com data/hora, posição mais recente, altitude, SNR/RSSI quando disponíveis e distância acumulada observada.
- Nós são classificados como móveis pela **mudança real de posição**, não pela role Meshtastic; jitter inferior a 3 m e saltos terrestres manifestamente impossíveis são descartados.
- Nova função de **menção no chat**: digitar `@` abre a lista de nós e permite pesquisar por short name, nome completo ou node ID.
- Exemplo: ao selecionar `@VHF4`, o compositor substitui pelo **nome completo do nó**, e a mensagem enviada continua sendo texto Meshtastic normal.
- Menções reconhecidas são destacadas visualmente no chat do Traffic Analyzer.
- Mantidos o tema Claro/Escuro, o indicador de versão e a correção de represamento introduzidos na v1.20.0.
- Mantidos os screenshots anonimizados no README e nas notas da Release.
- [Baixar o manual PDF da v1.21.0](./Documentacao_Traffic_Analyzer_v1.21.0.pdf)

## Novidades da v1.20.0

- **Pausa ao vivo corrigida:** traceroutes incompletos deixam de ser marcados como vistos antes de a rota estar pronta; quando o MeshMonitor completa o registro, ele entra normalmente na animação.
- Durante a pausa, o Traffic Analyzer continua consultando e processando o MeshMonitor; traceroutes prontos ficam represados e animações em andamento permanecem congeladas.
- A fila de traceroutes represados foi ampliada para até **5.000 eventos**, com aviso explícito se o limite for excedido.
- Pulsos de atividade recebidos durante a pausa também ficam represados e são liberados ao retomar.
- **Indicador de versão no topo:** informa se a instalação está atualizada ou se existe uma nova Release publicada no GitHub.
- Ao clicar no indicador, a interface mostra a versão instalada, a versão disponível, as notas da Release e o comando `sudo traffic-analyzer-update`.
- A consulta de versão é feita pelo servidor com cache de 15 minutos; a interface verifica ao abrir e depois periodicamente.
- **Tema da interface:** nova opção **Escuro** (padrão) ou **Claro** em Configurações, salva no navegador e independente do mapa-base.
- Removida do resumo do mapa a indicação **"Linhas = adjacências observadas, não enlaces permanentes"**.
- Mantidos os screenshots anonimizados no README e nas notas da Release.
- [Baixar o manual PDF da v1.20.0](./Documentacao_Traffic_Analyzer_v1.20.0.pdf)

## Novidades da v1.19.0

- **Controle de animação simplificado:** um único botão alterna entre **▶ Reproduzir/Retomar** e **⏸ Pausar**; o segundo botão de play/pause foi removido.
- No modo **Ao vivo**, pausar continua congelando somente a animação visual. Coleta e processamento seguem ativos, e os traceroutes represados iniciam juntos ao retomar.
- No modo **Histórico**, o mesmo botão agora pausa e retoma a animação no ponto exato, sem reiniciar o traceroute em andamento.
- **Enquadrar mais justo:** o mapa usa zoom fracionário em passos de 0,05 e ajusta o nível até ocupar o máximo da tela sem cortar círculos ou rótulos permanentes.
- A margem de segurança do enquadramento foi reduzida para cerca de 6 px; o ajuste fino verifica os elementos realmente renderizados.
- Mantidos os screenshots anonimizados no README e nas notas da Release formal.
- [Baixar o manual PDF da v1.19.0](./Documentacao_Traffic_Analyzer_v1.19.0.pdf)

## Novidades da v1.18.0

- **Pausa no modo Ao vivo:** congela somente a movimentação das animações no mapa. A coleta e o processamento continuam em segundo plano.
- Ao retomar, todos os traceroutes que chegaram durante a pausa iniciam imediatamente, inclusive em paralelo; animações em andamento continuam do ponto congelado.
- **Auto Zoom:** desligado passa a impedir também enquadramentos automáticos de NodeInfo.
- **Enquadrar:** margem fixa mínima de 22 px para usar melhor a tela sem perder nós extremos.
- **Atualizar:** força uma regeneração real da topologia e mostra sucesso/erro.
- **Tráfego:** removida a coluna **Canal** da tabela principal; o canal permanece nos detalhes.
- **Mensagens:** layout ampliado e novo controle de fonte (10 a 20 px) em Configurações.
- **Screenshots:** galeria pública anonimizada adicionada ao README.
- **Release:** GitHub Actions gera ZIP versionado, atualiza `traffic-analyzer-latest.zip` e cria Release formal marcada como Latest.
- [Baixar o manual PDF da v1.18.0](./Documentacao_Traffic_Analyzer_v1.18.0.pdf)

## Novidades da v1.17.0

- Na aba **Mensagens**, o texto digitado no campo de composição agora é branco.
- Removido completamente o **pop-up de nova mensagem**. Mensagens não lidas são sinalizadas apenas pelo contador e pelo destaque piscante da aba superior **Mensagens**.
- **Carregar anteriores** agora amplia explicitamente a janela do histórico e preserva a posição de leitura.
- **Atualizar** agora força uma consulta imediata e mostra o horário/resultado da atualização.
- A aba **Saúde da Rede** ganhou **Interações por chat no canal primário**, em ordem da maior para a menor quantidade acumulada.
- O ranking de chat usa as mensagens `TEXT_MESSAGE_APP` do canal 0 preservadas no histórico `traffic.db`.
- O atualizador por Git passa a operar sem prompt interativo de credenciais, adequado a repositórios públicos.
- Documentação ampliada com download por ZIP e comandos prontos para descompactar e instalar.
- [Baixar o manual PDF da v1.17.0](./Documentacao_Traffic_Analyzer_v1.17.0.pdf)

## Novidades da v1.16.0

- Nova aba **Mensagens** para o canal primário (canal 0), com visual estilo WhatsApp.
- Campo inferior para envio pelo MeshMonitor v1 API, usando o token apenas no servidor.
- Balões com remetente, data/hora, indicação RF/MQTT e estado real de entrega.
- Ícones de entrega: relógio (pendente), um check (transmitida), dois checks (ACK de protocolo quando disponível) e alerta em falha. Não existe confirmação de leitura humana em broadcast Meshtastic.
- Pop-up central para cada nova mensagem recebida, com botão **OK**.
- A aba **Mensagens** pisca e mostra contador enquanto houver mensagens não lidas. O estado de leitura fica persistido no navegador.
- Enter envia; Shift+Enter quebra linha; contador de bytes protege contra mensagens excessivamente longas.
- Ao rolar para o topo, a interface amplia progressivamente a janela de histórico consultada.
- Manual PDF refeito com tabelas de texto quebrável e altura dinâmica para evitar sobreposição.
- [Baixar o manual PDF da v1.16.0](./Documentacao_Traffic_Analyzer_v1.16.0.pdf)


## Novidades da v1.15.0

- Nova aba **Saúde da Rede** com nós ativos em 2 h/24 h/7 dias, pacotes, enlaces, traceroutes, média/mediana de hops, série diária e nós que merecem atenção.
- Nova aba **Anomalias** com heurísticas para silêncio prolongado, queda de SNR, mudança relevante de hops e traceroute assimétrico.
- Popup do nó mostra a situação com tempo amigável desde a última observação, por exemplo `ouvido há 2 horas e 21 minutos`.
- Novo comando `traffic-analyzer-update` para baixar `main` do GitHub e executar a atualização automaticamente.
- Novos endpoints locais `/api/network-health` e `/api/anomalies`, preparados para alimentar o futuro relatório PDF estruturado.

### Atualizar diretamente do GitHub

Após instalar a v1.15.0, as próximas atualizações podem ser feitas com:

```bash
sudo traffic-analyzer-update
```

Por padrão o comando usa `https://github.com/alexpmr/traffic-analyzer.git`, branch `main`, e mantém configuração e dados persistentes em `/etc` e `/var/lib/traffic-analyzer`.


## Novidades da v1.14.0

A v1.14.0 simplifica a integração com o MeshMonitor e remove completamente do Traffic Analyzer o recurso **Remover nó**. A exclusão de nós deve ser feita diretamente no MeshMonitor, onde existem as operações oficiais para excluir do banco local ou fazer *purge* também na NodeDB do dispositivo conectado. O Traffic Analyzer volta a ser estritamente uma ferramenta de observação, análise e arquivo histórico.

O mapa-base padrão passa a ser **Ruas (OpenStreetMap / OSM)**. Na primeira execução desta versão, a preferência antiga de mapa é migrada uma vez para OSM; depois disso, alterações manuais voltam a ser preservadas normalmente no navegador. Os mapas Topográfico, Claro, Escuro e Satélite continuam disponíveis.

O cabeçalho foi simplificado: não exibe mais a linha `gerado em ... · fonte ...`. O título padrão agora aparece como **Traffic Analyzer v1.14.0 - MeshMonitor - por Alex, PT2VHF**.

Permanece o painel discreto durante traceroutes animados, com origem e destino, distância direta, percurso total de IDA, percurso total de VOLTA e total ida + volta quando ambos os trajetos são completos. As distâncias continuam sendo calculadas apenas a partir de coordenadas conhecidas, sem estimar hops ausentes.

Também permanecem as cores de atividade dos nós: verde até 2 horas, laranja entre 2 e 24 horas, vermelho acima de 24 horas e cinza sem timestamp confiável. A informação de firmware continua removida.

## Screenshots

As capturas abaixo são parcialmente anonimizadas para não expor dados operacionais da malha real.

### Mapa e topologia

![Mapa e topologia](docs/screenshots/01-mapa-topologia.webp)

### Mensagens

![Mensagens](docs/screenshots/03-mensagens.webp)

### Saúde da Rede

![Saúde da Rede](docs/screenshots/04-saude-da-rede.webp)

## Arquitetura

```text
Meshtastic radio/source
        |
        v
MeshMonitor
  |- Nodes / Traceroutes
  |- Packet Monitor
  `- REST API v1
        |
        v
Traffic Analyzer
  |- descoberta/topologia/NodeInfo
  |- interface web :8788
  |- animações de mapa
  `- arquivo persistente traffic.db
        |
        v
Gerador de relatórios externo
  `- /api/archive/*
```

O token `mm_v1_...` permanece no processo servidor. Ele não é enviado ao navegador.

## Requisitos

- MeshMonitor com API v1 por fonte; recomendado 4.16.1 ou superior;
- Packet Monitor habilitado na fonte analisada;
- token API com acesso à fonte e `packetmonitor:read`;
- Python 3;
- Linux com systemd para usar o instalador fornecido.

## Download rápido (ZIP)

A v1.17.0 publica dois pacotes prontos no próprio repositório:

- [Baixar ZIP da versão mais recente](./traffic-analyzer-latest.zip)
- [Baixar ZIP da v1.17.0](./traffic-analyzer-v1.17.0.zip)

Quando o repositório estiver **público**, qualquer usuário poderá baixar o pacote sem conta, token ou chave SSH.

### Baixar e instalar pelo terminal

```bash
cd /tmp

wget -O traffic-analyzer-latest.zip \
  https://raw.githubusercontent.com/alexpmr/traffic-analyzer/main/traffic-analyzer-latest.zip

rm -rf traffic-analyzer
unzip -q -o traffic-analyzer-latest.zip

cd traffic-analyzer
sudo bash install.sh
```

### Se o ZIP já estiver no servidor

Execute no diretório onde o arquivo foi baixado:

```bash
ZIP="$(ls -t traffic-analyzer*.zip | head -n 1)"

rm -rf /tmp/traffic-analyzer-install
mkdir -p /tmp/traffic-analyzer-install

unzip -q -o "$ZIP" -d /tmp/traffic-analyzer-install

cd /tmp/traffic-analyzer-install/traffic-analyzer
sudo bash install.sh
```

> **Importante:** o download anônimo do GitHub só funciona se o repositório estiver configurado como **Public**.

## Instalação / atualização

O bloco abaixo procura o ZIP no diretório atual, no home corrente, em `/home` e em `/root`. Assim ele também funciona quando o arquivo foi enviado para o home de um usuário comum, mas a sessão administrativa está como `root`.

```bash
TA_VER="1.18.0" && \
TA_ZIP="$(find "$PWD" "$HOME" /home /root -maxdepth 3 -type f -name "traffic-analyzer-v${TA_VER}.zip" -print -quit 2>/dev/null)" && \
[ -n "$TA_ZIP" ] && \
TA_BASE="$(dirname "$TA_ZIP")" && \
TA_STAGE="${TA_BASE}/.traffic-analyzer-stage" && \
rm -rf "$TA_STAGE" && \
mkdir -p "$TA_STAGE" && \
unzip -q -o "$TA_ZIP" -d "$TA_STAGE" && \
rm -rf "${TA_BASE}/traffic-analyzer" && \
mv "$TA_STAGE/traffic-analyzer" "${TA_BASE}/traffic-analyzer" && \
rm -rf "$TA_STAGE" && \
cd "${TA_BASE}/traffic-analyzer" && \
{ if [ "$(id -u)" -eq 0 ]; then bash install.sh; else sudo bash install.sh; fi; } && \
systemctl status traffic-analyzer.timer --no-pager && \
systemctl status traffic-analyzer-map.service --no-pager
```

O próprio `install.sh` mostra os dois `systemctl status` ao final; as duas últimas linhas mantêm a checagem explícita no bloco único de copiar/colar.

A atualização preserva token, `MM_SOURCE`, `state.json`, `topology.json`, cooldowns, porta, preferências do navegador e `traffic.db`. O diretório extraído é sempre `traffic-analyzer/`, independentemente da versão, e não existe dependência de `/home/painel` nem de outro nome específico de conta.

## Configuração

Arquivo principal:

```text
/etc/traffic-analyzer.env
```

Exemplo mínimo:

```text
MM_BASE_URL=http://127.0.0.1:3001
MM_API_TOKEN=mm_v1_...
MM_SOURCE=<UUID_DA_FONTE>
DRY_RUN=false
```

Parâmetros do arquivo histórico:

```text
TRAFFIC_ARCHIVE_DB=/var/lib/traffic-analyzer/traffic.db
ARCHIVE_POLL_SECONDS=2
ARCHIVE_PAGE_SIZE=500
ARCHIVE_OVERLAP_MS=10000
ARCHIVE_RETENTION_DAYS=0
```

`ARCHIVE_RETENTION_DAYS=0` significa **sem expiração automática** no Traffic Analyzer.

Interface web:

```text
/etc/traffic-analyzer-map.env
```

Padrão:

```text
MAP_BIND=0.0.0.0
MAP_PORT=8788
MAP_TITLE=Traffic Analyzer - MeshMonitor - por Alex, PT2VHF
```

## Packet Monitor do MeshMonitor

O arquivo histórico só consegue importar o que ainda existe no Packet Monitor no momento da primeira execução. Por isso, uma retenção razoável no MeshMonitor continua importante para cobrir indisponibilidades temporárias do Traffic Analyzer.

Exemplo útil:

```text
Maximum Packets to Store: 10000
Keep Packets For:         168 horas
```

Depois que um pacote é copiado para `traffic.db`, ele deixa de depender da retenção do MeshMonitor.

## Interface

### Mapa

A reprodução inicia em **Ao vivo**. O modo Histórico continua disponível manualmente.

Para traceroutes:

- ida continua animada em ciano e volta em magenta;
- vários traceroutes ao vivo podem ser reproduzidos ao mesmo tempo;
- um traceroute novo começa imediatamente, sem aguardar animações anteriores;
- **Auto Zoom** opcional enquadra os nós das animações ativas e restaura o enquadramento anterior 5 segundos após a última terminar;
- origem, relays conhecidos e destino/resposta recebem pulsos conforme o marcador percorre o caminho;
- ausência de posição ou hop inválido continua quebrando o caminho; não há teleporte nem hop inventado.

Para demais pacotes:

- o nó de origem do pacote observado recebe pulso de atividade;
- uma resposta é realçada quando aparece como nova transmissão do nó que respondeu;
- `relay_node` pode receber pulso amarelo quando resolve de forma não ambígua para um nó conhecido e posicionado;
- a duração do pulso é configurável.

**Cor dos nós por atividade:**

- verde: último tráfego conhecido há até 2 horas;
- laranja: entre 2 e 24 horas;
- vermelho: há mais de 24 horas;
- cinza: sem timestamp de atividade disponível.

A exclusão de nós não é executada pelo Traffic Analyzer. Para apagar um nó, use as ações próprias do MeshMonitor na fonte correspondente; isso evita que a interface analítica faça operações destrutivas no banco ou na NodeDB do rádio.

### Tráfego

As colunas Hora, DIR, Origem, Destino, Tipo, SNR, RSSI, Hops e Canal permanecem compactas. O painel de detalhes usa o restante da largura disponível. Em telas menores, a tabela usa rolagem horizontal e o painel lateral pode ser ocultado.

No detalhe do pacote:

- `TEXT_MESSAGE_APP` broadcast: conteúdo exibido quando decodificado;
- `TEXT_MESSAGE_APP` direto: conteúdo oculto por padrão;
- Position, NodeInfo, Telemetry, Traceroute, NeighborInfo, Routing e outros: apresentação amigável quando o MeshMonitor fornece payload decodificado;
- Dados técnicos: exibidos em formato amigável; **Ver JSON bruto** permanece apenas como diagnóstico secundário.

O botão **Baixar dump JSON (.zip)** baixa todo o arquivo histórico disponível. O ZIP contém apenas `traffic.json`, com um bloco `export` de metadados e a lista `packets` com todos os registros arquivados.

### Sons e viagem de pacote

O som é emitido somente na primeira observação da viagem. A chave usa, em ordem: `packet_id`, ID disponível no metadata e fallbacks conservadores para registros sem ID. A animação visual é independente e pode acontecer em cada atividade observada.

## Arquivo histórico persistente

Banco padrão:

```text
/var/lib/traffic-analyzer/traffic.db
```

O banco usa SQLite em modo WAL. Na primeira inicialização, o serviço percorre o histórico ainda retido no Packet Monitor. Depois consulta continuamente uma janela sobreposta; a mesma janela é percorrida duas vezes e inserções usam deduplicação para reduzir o risco de lacunas quando novos registros chegam durante a paginação por offset.

São preservados, quando disponíveis: timestamp, `packet_id`, direção RX/TX, origem, destino, tipo/portnum, canal, SNR, RSSI, `hop_start`, `hop_limit`, `relay_node`, tamanho, criptografia, mecanismo de transporte, flags e metadata permitida.

### Privacidade

Antes da gravação:

- mensagem direta `TEXT_MESSAGE_APP`: `payload_preview` é substituído por `[conteúdo oculto]` e `metadata` é removido;
- broadcast: payload pode ser preservado;
- demais tipos: metadata é preservada quando fornecida pelo MeshMonitor.

## API para o gerador de relatórios

Endpoints locais do Traffic Analyzer:

```text
GET /api/archive/status
GET /api/archive/packets
GET /api/archive/stats
GET /api/archive/nodes
GET /api/archive/links
GET /api/archive/export?format=jsonl
GET /api/archive/export?format=csv
GET /api/archive/dump
```

Filtros aceitos nos endpoints de consulta incluem `since`, `until`, `direction=rx|tx`, `type`, `node`, `limit` e `offset`, conforme aplicável.

Exemplos:

```text
/api/archive/packets?since=1790000000000&direction=rx&limit=1000
/api/archive/stats?type=TELEMETRY_APP
/api/archive/nodes?since=1790000000000
/api/archive/export?format=jsonl&limit=100000
/api/archive/dump
```

`/api/archive/links` representa pares lógicos origem-destino observados nos pacotes; não deve ser interpretado automaticamente como adjacência RF física.

O endpoint `/health` também inclui o estado do coletor histórico e a quantidade arquivada.

## Fluxo NodeInfo

Pacotes comuns, inclusive `NODEINFO_APP`, não carregam a cadeia completa de relays como um traceroute. Quando existe traceroute próximo no tempo entre os mesmos endpoints, o Traffic Analyzer pode usá-lo como **evidência de uma rota observada**, sem afirmar que aquele pacote NodeInfo específico percorreu exatamente os mesmos relays.

## Serviços systemd

```bash
sudo systemctl status traffic-analyzer.timer --no-pager
sudo systemctl status traffic-analyzer-map.service --no-pager
```

Logs:

```bash
sudo journalctl -u traffic-analyzer.service -n 100 --no-pager
sudo journalctl -u traffic-analyzer-map.service -n 100 --no-pager
```

## Backup

`/var/lib/traffic-analyzer/traffic.db` passa a ser um ativo persistente. Para uma cópia simples e consistente, pare brevemente `traffic-analyzer-map.service`, copie o banco e inicie o serviço novamente; ou use uma rotina SQLite-aware no projeto de backup.

## Segurança e limitações

- a porta 8788 não possui autenticação própria; proteja-a por firewall/VLAN, bind local ou reverse proxy autenticado;
- tráfego apagado pelo MeshMonitor antes da primeira execução do arquivo histórico não pode ser reconstruído;
- se o Traffic Analyzer ficar indisponível por mais tempo que a retenção do Packet Monitor, pode existir lacuna histórica;
- `relay_node` normalmente representa apenas o último relay observado e pode ser somente um byte; relays ambíguos não são escolhidos arbitrariamente;
- a animação representa sequência visual dos dados observados, não o tempo RF real;
- o SQLite não expira dados por padrão e pode crescer continuamente.

## Changelog

Consulte `CHANGELOG.md`. O mesmo histórico detalhado é incluído como **última seção do manual PDF**.

## Autoria

**Por Alex, PT2VHF**
