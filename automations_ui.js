/* Traffic Analyzer v1.61.0 — Automações PING/CLIMA. Sem frameworks externos. */
(function(){
'use strict';
const css = [
'#viewAutomations{overflow:auto;padding:18px;background:#0e1621;color:#e8edf2}',
'.autoShell{max-width:1280px;margin:auto}.autoTop{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:18px}',
'.autoTop h2{margin:0 auto 0 0}.autoList{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}',
'.autoCard{background:#172633;border:1px solid #345166;border-radius:10px;padding:16px;min-width:0}',
'.autoCard h3{margin:0 0 8px}.autoCard p{line-height:1.45;color:#bfd0df;font-size:13px}',
'.autoCard .autoState{font-weight:700;display:inline-block;padding:3px 8px;border-radius:9px;background:#344657;margin-bottom:10px}',
'.autoCard .autoState.ok{background:#145043;color:#b6ffe1}.autoCard .autoState.off{background:#654b2c;color:#ffe0a0}',
'.autoToolbar{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:12px 0}',
'.autoToolbar button{padding:8px 12px;font-weight:600}.autoDetail{margin-top:18px;background:#172633;border:1px solid #345166;border-radius:10px;padding:18px}',
'.autoForm{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}',
'.autoField{display:flex;flex-direction:column;gap:7px;font-size:13px;font-weight:650}',
'.autoField input,.autoField textarea{width:100%;box-sizing:border-box;padding:8px 10px;background:#0e1a25;color:#e8edf2;border:1px solid #4c6378;border-radius:5px}',
'.autoField textarea{min-height:125px;font-family:ui-monospace,Consolas,monospace;resize:vertical}',
'.autoField.wide{grid-column:1/-1}.autoHint{color:#a7c1d2;font-size:12px;font-weight:400}',
'.autoResult{padding:12px;background:#0b1721;border:1px solid #476278;border-radius:7px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:400px;overflow:auto}',
'.autoLog{width:100%;border-collapse:collapse;font-size:12px}.autoLog td,.autoLog th{padding:8px;border-bottom:1px solid #365063;text-align:left;vertical-align:top}',
'.autoLogWrap{overflow:auto}.autoBanner{padding:12px;margin-bottom:14px;background:#322a23;border:1px solid #866336;border-radius:8px}',
'.autoInfo{color:#adc9dd;font-size:13px}.autoMsg{min-height:20px;margin:8px 0;font-size:13px}',
'@media(max-width:650px){#viewAutomations{padding:9px}.autoCard,.autoDetail{padding:12px}}'
].join('\n');
const style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
const view=document.createElement('section');view.id='viewAutomations';view.className='view';
view.innerHTML='<div class="autoShell"><div class="autoTop"><h2>Automações</h2>'+
'<span class="autoInfo">Bots e rotinas de resposta da rede Meshtastic</span>'+
'<button type="button" id="autoReload">Atualizar</button></div>'+
'<div id="autoStatus" class="autoBanner">Carregando automações...</div>'+
'<div id="autoCards" class="autoList"></div><div id="autoDetail" class="autoDetail" style="display:none"></div>'+
'<div class="autoDetail"><div class="autoTop"><h3>Histórico e diagnóstico</h3>'+
'<button type="button" id="autoHistoryReload">Atualizar histórico</button></div>'+
'<div class="autoLogWrap"><table class="autoLog"><thead><tr><th>Horário</th><th>Bot</th><th>Estação</th><th>Resultado</th><th>Detalhes</th></tr></thead>'+
'<tbody id="autoHistoryRows"><tr><td colspan="5">Sem dados carregados.</td></tr></tbody></table></div></div>'+
'<p class="autoInfo">As respostas são encaminhadas pelo listener Meshtastic já existente. Enfileiramento de envio não comprova entrega RF.</p></div>';
document.getElementById('viewSettings').parentNode.insertBefore(view,document.getElementById('viewSettings'));
let data=null,selected='',loading=false,hasLoaded=false;
const e=x=>esc(x);
const state=()=>authState.enabled&&!authState.authenticated;
const el=id=>document.getElementById(id);
const fmt=ms=>ms?new Date(Number(ms)).toLocaleString(uiLocale()):'—';
function alertText(text,bad){
 const target=el('autoStatus');target.textContent=text;target.style.borderColor=bad?'#bb6161':'#476278';
}
function applyAutomationAccess(locked){
 if(locked){data=null;hasLoaded=false;el('autoCards').innerHTML='';el('autoDetail').style.display='none';
   el('autoHistoryRows').innerHTML='<tr><td colspan="5">Faça login para consultar os registros.</td></tr>';
   alertText('Acesso administrativo necessário para consultar e editar as automações.',true);}
 else if(el('viewAutomations').classList.contains('active'))loadAutomations();
}
window.applyAutomationAccess=applyAutomationAccess;
function renderCards(){
 if(!data)return;
 const events=data.events||[];
 const cards=(data.items||[]).map(item=>{
  const id=item.id,conf=data.settings[id],last=events.find(x=>x.command===id);
  const active=data.globalEnabled&&conf.enabled;
  const label=active?'Ativo':!data.globalEnabled?'Desativado globalmente':'Desativado';
  return '<article class="autoCard"><h3>'+e(item.name)+'</h3><span class="autoState '+(active?'ok':'off')+'">'+e(label)+'</span>'+
   '<p>'+ (id==='ping'?'Responde a PING com diagnóstico de sinal, nós e traceroute.':'Responde a CLIMA e #CLIMA com os dados locais da API Tempest.')+'</p>'+
   '<p>Última ocorrência: '+e(last?fmt(last.processed_at):'Sem registros')+'</p>'+
   '<p>Status: '+e(last?.status||'—')+'</p>'+
   '<button data-auto-open="'+e(id)+'">Configurar '+e(item.name)+'</button></article>';
 }).join('');
 el('autoCards').innerHTML=cards+'<article class="autoCard"><h3>Próximas automações</h3>'+
 '<p>Estrutura pronta para novas rotinas, sem duplicar listeners ou criar serviços paralelos.</p>'+
 '<span class="autoInfo">Nenhuma outra automação configurada.</span></article>';
 el('autoCards').querySelectorAll('[data-auto-open]').forEach(btn=>btn.addEventListener('click',()=>showAutomationDetails(btn.dataset.autoOpen)));
}
function renderHistory(){
 const events=data?.events||[];
 el('autoHistoryRows').innerHTML=events.map(x=>
  '<tr><td>'+e(fmt(x.processed_at))+'</td><td>'+e(String(x.command||'').toUpperCase())+'</td>'+
  '<td>'+e(x.from_node_id||x.from_node||'—')+'</td><td>'+e(x.status||'—')+'</td><td>'+e(x.detail||'—')+'</td></tr>'
 ).join('')||'<tr><td colspan="5">Nenhum comando registrado.</td></tr>';
}
function formHtml(bot,conf){
 const enabled='<label class="autoField"><span>Automação habilitada</span><select id="autoEnabled"><option value="true" '+(conf.enabled?'selected':'')+'>Sim</option>'+
  '<option value="false" '+(!conf.enabled?'selected':'')+'>Não</option></select></label>';
 const cd='<label class="autoField">Cooldown por estação (s)<input id="autoCooldown" type="number" min="0" max="86400" value="'+e(conf.cooldownSeconds)+'"></label>';
 const ping=bot==='ping';
 const special=ping?
  '<label class="autoField">Identificação do bot<input id="autoLabel" maxlength="45" value="'+e(conf.label)+'"></label>'+
  '<label class="autoField">Timeout de traceroute (s)<input id="autoRouteTimeout" type="number" min="5" max="90" value="'+e(conf.routeTimeoutSeconds)+'"></label>':
  '<label class="autoField">Intervalo entre blocos (s)<input id="autoReplyGap" type="number" min="0" max="60" step="0.5" value="'+e(conf.replyGapSeconds)+'"></label>'+
  '<label class="autoField wide">API Tempest local<input id="autoApiUrl" maxlength="256" value="'+e(conf.apiUrl)+'">'+
  '<span class="autoHint">Somente endereço HTTP de loopback (127.0.0.1/localhost), para proteger o servidor.</span></label>';
 const help=ping?'Variáveis disponíveis: {{mensagem_padrao}}, {{destino}}, {{origem}}, {{hora}}, {{sinal}}, {{qualidade}}, {{saltos}}, {{via}}, {{nos_24h}}, {{rota}}. Modelo personalizado deve conter {{origem}}.':
  'Use {{clima}} para inserir as mensagens geradas pela API Tempest. Prévia consulta a API, mas não transmite.';
 return '<div class="autoTop"><h3>Configurar '+(ping?'PING':'CLIMA')+'</h3>'+
  '<button id="autoClose" type="button">Voltar para as automações</button></div>'+
  '<p class="autoInfo">Alterações só serão efetivadas depois de salvar. A prévia usa os valores atuais do formulário.</p>'+
  '<div class="autoForm">'+enabled+cd+special+
  '<label class="autoField wide">Modelo de resposta<textarea id="autoTemplate">'+e(conf.template)+'</textarea>'+
  '<span class="autoHint">'+e(help)+'</span></label></div>'+
  '<div class="autoToolbar"><button id="autoSave" type="button">Salvar configuração</button>'+
  '<button id="autoPreviewBtn" type="button">Prévia sem transmitir</button>'+
  '<button id="autoSendTest" type="button" title="Envia mensagens reais ao canal primário via MeshMonitor">Enviar teste real (canal primário)</button></div>'+
  '<div id="autoActionStatus" class="autoMsg"></div>'+
  '<pre id="autoPreviewResult" class="autoResult">Use Prévia para revisar o texto antes de qualquer envio.</pre>';
}
function values(){
 const ping=selected==='ping';
 const settings={enabled:el('autoEnabled').value==='true',cooldownSeconds:Number(el('autoCooldown').value),template:el('autoTemplate').value};
 if(ping){settings.label=el('autoLabel').value;settings.routeTimeoutSeconds=Number(el('autoRouteTimeout').value);}
 else{settings.replyGapSeconds=Number(el('autoReplyGap').value);settings.apiUrl=el('autoApiUrl').value;}
 return settings;
}
function showAutomationDetails(id,updateRoute=true){
 selected=(id==='ping'||id==='clima')?id:'';
 const box=el('autoDetail');box.style.display=selected?'block':'none';
 if(selected&&data?.settings?.[selected]){
  box.innerHTML=formHtml(selected,data.settings[selected]);
  el('autoClose').addEventListener('click',()=>showAutomationDetails(''));
  el('autoSave').addEventListener('click',saveAutomation);
  el('autoPreviewBtn').addEventListener('click',previewAutomation);
  el('autoSendTest').addEventListener('click',testAutomation);
  if(state())box.querySelectorAll('input,select,textarea,button').forEach(x=>x.disabled=true);
  box.scrollIntoView({block:'nearest'});
 }
 if(updateRoute)taSyncRoute({view:'automations'});
}
window.showAutomationDetails=showAutomationDetails;
async function loadAutomations(force=false){
 if(state()){applyAutomationAccess(true);return;}
 if(loading||(!force&&hasLoaded))return;
 loading=true;
 try{
  const r=await fetch('/api/automations',{cache:'no-store'}),b=await r.json();
  if(!r.ok||!b.success)throw Error(b.message||'HTTP '+r.status);
  data=b;hasLoaded=true;
  alertText(b.globalEnabled?'Bots integrados habilitados globalmente. Ajuste cada automação abaixo.':
   'ATENÇÃO: TA_MESH_COMMANDS_ENABLED=false desativa todos os bots; a ativação individual não substitui a chave global.',!b.globalEnabled);
  renderCards();renderHistory();
  if(selected)showAutomationDetails(selected,false);
 }catch(ex){hasLoaded=false;alertText('Falha ao consultar automações: '+String(ex.message||ex),true);}
 finally{loading=false;}
}
window.loadAutomations=loadAutomations;
async function post(url,payload){
 const r=await authFetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const b=await r.json();if(!r.ok||!b.success)throw Error(b.message||'HTTP '+r.status);
 return b;
}
function showMessage(msg,bad){
 const target=el('autoActionStatus');if(target){target.textContent=msg;target.style.color=bad?'#ffadad':'#9ee8cc';}
}
async function saveAutomation(){
 if(!authCanWrite()){openAuthModal();return;}
 const btn=el('autoSave');btn.disabled=true;showMessage('Salvando...',false);
 try{
  const b=await post('/api/automations',{bot:selected,settings:values()});
  data.settings=b.settings;showMessage('Configuração salva no servidor e aplicada às próximas mensagens.',false);
  renderCards();
 }catch(ex){showMessage('Erro: '+String(ex.message||ex),true);}
 finally{btn.disabled=false;}
}
async function previewAutomation(){
 if(!authCanWrite()){openAuthModal();return;}
 const btn=el('autoPreviewBtn');btn.disabled=true;showMessage('Gerando prévia sem transmissão...',false);
 try{
  const b=await post('/api/automations/preview',{bot:selected,settings:values()});
  el('autoPreviewResult').textContent=b.text+'\n\n---\n'+b.parts.length+' blocos · '+b.bytes+' bytes · nenhuma transmissão RF';
  showMessage('Prévia gerada. Nenhum pacote foi enviado.',false);
 }catch(ex){el('autoPreviewResult').textContent='';showMessage('Não foi possível gerar a prévia: '+String(ex.message||ex),true);}
 finally{btn.disabled=false;}
}
async function testAutomation(){
 if(!authCanWrite()){openAuthModal();return;}
 const bot=selected;
 if(!confirm('Será executado um envio REAL no canal primário pelo MeshMonitor, possivelmente por RF. A entrega não é garantida. O teste usa apenas a última configuração SALVA. Confirmar?'))return;
 const btn=el('autoSendTest');btn.disabled=true;showMessage('Solicitando envio real pelo MeshMonitor...',false);
 try{
  const b=await post('/api/automations/test-send',{bot,confirm:true});
  showMessage('Teste solicitado: '+b.sentParts+' bloco(s). '+b.notice,false);
  await loadAutomations(true);
 }catch(ex){showMessage('Falha no teste: '+String(ex.message||ex),true);}
 finally{btn.disabled=false;}
}
el('autoReload').addEventListener('click',()=>loadAutomations(true));
el('autoHistoryReload').addEventListener('click',()=>loadAutomations(true));
window.addEventListener('focus',()=>{if(el('viewAutomations').classList.contains('active'))loadAutomations(true);});
})();