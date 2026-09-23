#!/usr/bin/env python3
"""Interface web do Traffic Analyzer v1.17.0 para MeshMonitor."""

import csv
import io
import json
import os
import sqlite3
import statistics
import threading
import time
import tempfile
import zipfile
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_VERSION = "1.17.0"
try:
    _version_path = Path(__file__).with_name("VERSION")
    if _version_path.exists():
        APP_VERSION = _version_path.read_text(encoding="utf-8").strip() or APP_VERSION
except Exception:
    pass

BIND = os.getenv("MAP_BIND", "0.0.0.0")
PORT = int(os.getenv("MAP_PORT", "8788"))
TITLE = os.getenv("MAP_TITLE", "Traffic Analyzer - MeshMonitor - por Alex, PT2VHF")
def _display_title(title: str) -> str:
    if title.startswith("Traffic Analyzer"):
        return title.replace("Traffic Analyzer", f"Traffic Analyzer v{APP_VERSION}", 1)
    return f"{title} - v{APP_VERSION}"
DISPLAY_TITLE = _display_title(TITLE)
TOPOLOGY_FILE = Path(os.getenv(
    "TOPOLOGY_FILE",
    "/var/lib/traffic-analyzer/topology.json",
))
MM_BASE_URL = os.getenv("MM_BASE_URL", "http://127.0.0.1:3001").rstrip("/")
MM_API_TOKEN = os.getenv("MM_API_TOKEN", "").strip()
MM_SOURCE = os.getenv("MM_SOURCE", "default").strip() or "default"
TRAFFIC_ARCHIVE_DB = Path(os.getenv(
    "TRAFFIC_ARCHIVE_DB",
    "/var/lib/traffic-analyzer/traffic.db",
))
ARCHIVE_POLL_SECONDS = max(1.0, float(os.getenv("ARCHIVE_POLL_SECONDS", "2")))
ARCHIVE_PAGE_SIZE = max(100, min(int(os.getenv("ARCHIVE_PAGE_SIZE", "500")), 1000))
ARCHIVE_OVERLAP_MS = max(1000, int(os.getenv("ARCHIVE_OVERLAP_MS", "10000")))
ARCHIVE_RETENTION_DAYS = max(0, int(os.getenv("ARCHIVE_RETENTION_DAYS", "0")))
_archive_stop = threading.Event()
_archive_status_lock = threading.Lock()
_archive_status = {"running": False, "last_sync_ms": None, "last_error": None, "inserted_last_sync": 0}

HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__DISPLAY_TITLE__</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
 integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<style>
  html,body{height:100%;margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#0e1621;color:#e8edf2}
  #app{height:100%;display:flex;flex-direction:column;min-height:0}
  header{padding:10px 14px;background:#17212b;border-bottom:1px solid #293744;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
  header h1{font-size:17px;margin:0;font-weight:700}.downloadBtn{background:#234d63;border-color:#4c7e96;font-weight:700}
  #summary{display:flex;gap:8px;flex-wrap:wrap;padding:8px 12px;background:#111c27;border-bottom:1px solid #293744}
  #playback{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:7px 12px;background:#14202b;border-bottom:1px solid #293744}
  #playStatus{font-size:12px;color:#cbd6df;min-width:260px;max-width:680px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .liveBadge{color:#ff6b6b;font-weight:700}
  .metric{background:#1d2b38;border:1px solid #304353;border-radius:7px;padding:5px 9px;font-size:12px}
  .metric b{font-size:15px;margin-right:4px}
  #nav{display:flex;gap:5px;align-items:center}
  .navbtn{font-weight:700;padding:6px 10px}.navbtn.active{background:#e4b800;color:#101820;border-color:#ffe34d}
  .view{display:none;flex:1;min-height:0;min-width:0}.view.active{display:flex;flex-direction:column}
  #viewMap #map{flex:1;min-height:0}
  #trafficToolbar{display:flex;gap:9px;align-items:center;flex-wrap:wrap;padding:9px 12px;background:#111c27;border-bottom:1px solid #293744}
  #trafficStats{display:flex;gap:8px;flex-wrap:wrap;padding:8px 12px;background:#14202b;border-bottom:1px solid #293744}
  #trafficBody{display:grid;grid-template-columns:max-content minmax(360px,1fr);flex:1;min-height:0;min-width:0}
  #trafficTableWrap{overflow:auto;min-height:0;min-width:0;max-width:100vw}.trafficTable{width:auto;border-collapse:collapse;font-size:12px;table-layout:fixed}.trafficTable th{position:sticky;top:0;background:#17212b;color:#cbd6df;text-align:left;padding:8px;border-bottom:1px solid #405668;z-index:2}.trafficTable td{padding:7px 8px;border-bottom:1px solid #22313f;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.trafficTable tr{cursor:pointer}.trafficTable tbody tr:hover{background:#1d2b38}.trafficTable tbody tr.selected{background:#263b4d}
  .trafficTable th:nth-child(1),.trafficTable td:nth-child(1){width:72px}.trafficTable th:nth-child(2),.trafficTable td:nth-child(2){width:48px}.trafficTable th:nth-child(3),.trafficTable td:nth-child(3){width:185px;max-width:185px}.trafficTable th:nth-child(4),.trafficTable td:nth-child(4){width:185px;max-width:185px}.trafficTable th:nth-child(5),.trafficTable td:nth-child(5){width:118px;max-width:118px}.trafficTable th:nth-child(6),.trafficTable td:nth-child(6){width:58px}.trafficTable th:nth-child(7),.trafficTable td:nth-child(7){width:58px}.trafficTable th:nth-child(8),.trafficTable td:nth-child(8){width:48px}.trafficTable th:nth-child(9),.trafficTable td:nth-child(9){width:48px}
  .badge{display:inline-block;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:800}.rx{background:#174f37;color:#7af0ad}.tx{background:#164a64;color:#7ddcff}.typeBadge{background:#374657;color:#e8edf2}.type-text{background:#5d3b7c}.type-position{background:#365f3a}.type-nodeinfo{background:#795628}.type-telemetry{background:#1f5d69}.type-traceroute{background:#5a487d}.type-routing{background:#754044}.type-neighbor{background:#4d5b25}
  #packetDetail{overflow:auto;border-left:1px solid #293744;background:#111a24;padding:14px}.detailTitle{font-size:16px;font-weight:800;margin-bottom:8px}.detailGrid{display:grid;grid-template-columns:120px minmax(0,1fr);gap:7px;font-size:12px}.detailGrid b{color:#9fb0bf}.emptyDetail{color:#8194a5;font-size:13px;padding-top:8px}.payloadBox{background:#172532;border:1px solid #304353;border-radius:7px;padding:9px;line-height:1.45;overflow-wrap:anywhere}.payloadRows{display:grid;grid-template-columns:minmax(110px,38%) minmax(0,1fr);gap:4px 9px}.payloadRows .k{color:#9fb0bf;font-weight:700}.payloadRows .v{overflow-wrap:anywhere}.techDetails{margin-top:8px}.techDetails summary{cursor:pointer;color:#9fc6e4;font-weight:700}.techDetails .payloadBox{margin-top:7px}.rawJson{margin-top:9px;border-top:1px solid #304353;padding-top:7px}.rawJson summary{font-size:11px;color:#8194a5;font-weight:600}.techDetails pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0d1620;border:1px solid #2e4050;border-radius:6px;padding:8px;font-size:10px;max-height:320px;overflow:auto}.broadcastTag{display:inline-block;background:#345d39;color:#a8f0b0;border-radius:9px;padding:2px 6px;font-size:10px;font-weight:800;margin-left:6px}
  #viewSettings{overflow:auto}.settingsCard{max-width:900px;margin:24px auto;background:#17212b;border:1px solid #304353;border-radius:10px;padding:20px;width:calc(100% - 48px);box-sizing:border-box}.settingsCard h2{margin-top:0}.settingsCard h3{margin:20px 0 4px;color:#e9d46d}.settingRow{padding:12px 0;border-bottom:1px solid #293744}.settingRow:last-child{border-bottom:0}.settingDesc{color:#99aaba;font-size:12px;margin-top:5px}.soundTest{margin-left:8px}.settingsGrid{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:10px 22px}.settingsGrid .settingRow{min-width:0}.mapActions{margin-left:auto;display:flex;gap:7px}@media(max-width:760px){.settingsGrid{grid-template-columns:1fr}.mapActions{margin-left:0}}
  @media(max-width:1150px){#trafficBody{grid-template-columns:minmax(0,1fr)}#packetDetail{display:none}header{align-items:flex-start}.trafficTable{min-width:820px}}
  select,input,button{background:#233443;color:#edf3f8;border:1px solid #405668;border-radius:6px;padding:5px 7px}
  label{font-size:12px;color:#cbd6df}
  #map{height:100%;width:100%;min-height:0;min-width:0}
  .legend{background:rgba(23,33,43,.94);padding:8px 10px;border-radius:7px;color:#edf3f8;font-size:12px;line-height:1.55;border:1px solid #405668}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px}
  .identified{background:#39a96b}.stub{background:#e0a13a}.routeonly{background:#d85b5b}
  .trafficFresh{background:#2ecc71}.trafficWarm{background:#f39c12}.trafficOld{background:#e74c3c}.trafficUnknown{background:#7f8c8d}
  .leaflet-popup-content-wrapper,.leaflet-popup-tip{background:#17212b;color:#e8edf2}
  .warn{color:#ffcc66}
  .short-label{background:rgba(14,22,33,.88);border:1px solid #405668;color:#fff;border-radius:4px;padding:1px 4px;font-weight:700;box-shadow:none}
  .short-label:before{display:none}
  #flowToast{position:fixed;right:16px;top:16px;z-index:2000;max-width:440px;background:rgba(23,33,43,.97);border:1px solid #6e5aa8;border-left:5px solid #a970ff;border-radius:8px;padding:10px 12px;box-shadow:0 8px 24px rgba(0,0,0,.35);font-size:12px;line-height:1.4;display:none;cursor:pointer}
  #flowToast b{color:#d8c8ff}.flowNote{color:#aebbc7;margin-top:3px}.flowUnknown{border-left-color:#ffb347!important}.flowKnown{border-left-color:#a970ff!important}
  .activityLeafletIcon{background:transparent!important;border:0!important}.activityPulse{position:relative;width:46px;height:46px;display:flex;align-items:center;justify-content:center;transform:translate(-1px,-1px);pointer-events:none}.activityPulse .activityCore{position:relative;z-index:3;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:20px;border:2px solid #fff;box-shadow:0 0 12px rgba(255,255,255,.75);animation:activityBounce var(--taDur,1s) ease-out both}.activityPulse:before,.activityPulse:after{content:'';position:absolute;inset:7px;border-radius:50%;border:3px solid currentColor;opacity:.9;animation:activityRing var(--taDur,1s) ease-out both}.activityPulse:after{animation-delay:.16s}.activityPulse.origin{color:#38d6ff}.activityPulse.origin .activityCore{background:#0c6b82}.activityPulse.relay{color:#ffcf4a}.activityPulse.relay .activityCore{background:#8a6810}.activityPulse.response{color:#a970ff}.activityPulse.response .activityCore{background:#5a3482}@keyframes activityRing{0%{transform:scale(.45);opacity:.95}100%{transform:scale(1.65);opacity:0}}@keyframes activityBounce{0%{transform:scale(.7)}35%{transform:scale(1.25)}100%{transform:scale(1)}}
  .traceHud{background:rgba(14,22,33,.90);border:1px solid #405668;border-radius:8px;color:#e8edf2;padding:7px 9px;min-width:260px;max-width:410px;max-height:34vh;overflow:auto;box-shadow:0 6px 18px rgba(0,0,0,.28);pointer-events:none}.traceHud:empty{display:none}.traceHudItem{padding:5px 0;border-bottom:1px solid rgba(64,86,104,.55)}.traceHudItem:last-child{border-bottom:0}.traceHudHead{font-size:11px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.traceHudTotal{color:#ffd166;font-weight:700;margin-left:5px}.traceHudLeg{font-size:10px;color:#b9c7d2;margin-top:2px}.traceHudLeg.active{color:#fff;font-weight:800}.traceHudLeg .forward{color:#54e8ff}.traceHudLeg .return{color:#ff83e7}.traceHudDim{color:#8093a3}

  /* v1.15 - Saúde da Rede e Anomalias */
  #viewHealth,#viewAnomalies{overflow:auto;background:#0e1621}
  .dashboardWrap{width:100%;box-sizing:border-box;padding:14px;max-width:1500px;margin:0 auto}
  .dashboardToolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:12px}
  .dashboardToolbar h2{margin:0 auto 0 0;font-size:18px}
  .dashGrid{display:grid;grid-template-columns:repeat(4,minmax(170px,1fr));gap:10px;margin-bottom:12px}
  .dashCard{background:#17212b;border:1px solid #304353;border-radius:9px;padding:12px;min-width:0}
  .dashCard .value{font-size:27px;font-weight:800;line-height:1.05;margin:4px 0}.dashCard .label{font-size:12px;color:#aebbc7}.dashCard .sub{font-size:11px;color:#8194a5;margin-top:5px}
  .dashSection{background:#111a24;border:1px solid #293744;border-radius:9px;margin:10px 0;overflow:hidden}.dashSection h3{font-size:14px;margin:0;padding:10px 12px;background:#17212b;border-bottom:1px solid #293744}.dashSectionBody{padding:10px 12px;overflow:auto}
  .dashTable{width:100%;border-collapse:collapse;font-size:12px;min-width:720px}.dashTable th{position:sticky;top:0;background:#17212b;color:#cbd6df;text-align:left;padding:8px;border-bottom:1px solid #405668}.dashTable td{padding:8px;border-bottom:1px solid #22313f}.dashTable tr:last-child td{border-bottom:0}
  .miniBars{display:flex;align-items:flex-end;gap:7px;height:130px;padding:8px 4px 22px}.miniBarWrap{flex:1;min-width:42px;text-align:center;position:relative;height:100%}.miniBar{position:absolute;bottom:19px;left:12%;right:12%;background:#3a8fbd;border-radius:4px 4px 0 0;min-height:2px}.miniBarLabel{position:absolute;bottom:0;left:0;right:0;font-size:10px;color:#91a4b3}.miniBarValue{position:absolute;bottom:calc(var(--h) + 23px);left:0;right:0;font-size:10px;color:#dbe6ee}
  .severity{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:800}.sev-critical{background:#6e2020;color:#ffb2b2}.sev-warning{background:#6a4a13;color:#ffd98a}.sev-info{background:#174f64;color:#9ce8ff}.sev-ok{background:#174f37;color:#9df2bc}
  .anomalyRow{display:grid;grid-template-columns:92px minmax(150px,240px) minmax(300px,1fr) 160px;gap:8px;align-items:start;padding:10px 12px;border-bottom:1px solid #22313f;font-size:12px}.anomalyRow:last-child{border-bottom:0}.anomalyTitle{font-weight:800}.anomalyEvidence{color:#9fb0bf;margin-top:3px}.anomalyTime{color:#8194a5;text-align:right}
  .emptyPanel{padding:22px;color:#8194a5;text-align:center}.methodNote{font-size:11px;color:#8194a5;line-height:1.45}
  @media(max-width:1000px){.dashGrid{grid-template-columns:repeat(2,minmax(160px,1fr))}.anomalyRow{grid-template-columns:90px 1fr}.anomalyRow .anomalyMsg,.anomalyRow .anomalyTime{grid-column:2}.anomalyTime{text-align:left}}
  @media(max-width:620px){.dashGrid{grid-template-columns:1fr}.dashboardWrap{padding:9px}}


  /* v1.16 - Mensagens do canal primário */
  #viewMessages{background:#0b141a;min-height:0;position:relative}
  #messageHeader{padding:9px 14px;background:#17212b;border-bottom:1px solid #293744;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  #messageHeader .msgTitle{font-weight:800}.msgHint{font-size:11px;color:#91a4b3}.msgSpacer{flex:1}
  #messageList{flex:1;overflow:auto;padding:18px max(12px,calc((100% - 980px)/2));box-sizing:border-box;background:linear-gradient(rgba(11,20,26,.96),rgba(11,20,26,.96));scroll-behavior:smooth}
  .msgDay{text-align:center;margin:12px 0}.msgDay span{background:#182229;color:#b8c7d1;padding:5px 10px;border-radius:8px;font-size:11px;box-shadow:0 1px 2px rgba(0,0,0,.25)}
  .msgRow{display:flex;margin:4px 0}.msgRow.mine{justify-content:flex-end}.msgBubble{max-width:min(76%,720px);min-width:120px;border-radius:9px;padding:6px 8px 5px;box-shadow:0 1px 2px rgba(0,0,0,.28);overflow-wrap:anywhere;position:relative}.msgRow.theirs .msgBubble{background:#202c33;border-top-left-radius:2px}.msgRow.mine .msgBubble{background:#005c4b;border-top-right-radius:2px}
  .msgSender{font-size:11px;color:#70cfff;font-weight:800;margin-bottom:2px}.msgText{white-space:pre-wrap;font-size:13px;line-height:1.35;padding-right:58px}.msgMeta{font-size:10px;color:#b8c4ca;text-align:right;margin-top:-1px;white-space:nowrap}.msgStatus{font-size:12px;margin-left:4px;letter-spacing:-2px}.msgStatus.confirmed{color:#53bdeb}.msgStatus.failed{color:#ff8f8f}.msgTransport{font-size:9px;color:#8194a5;margin-left:5px}
  .msgNewMark{display:inline-block;background:#1f6f8b;color:white;border-radius:8px;padding:1px 5px;font-size:9px;margin-left:5px}
  #messageComposer{display:flex;gap:8px;align-items:flex-end;padding:9px max(12px,calc((100% - 980px)/2));background:#202c33;border-top:1px solid #293744;box-sizing:border-box}#messageInput{flex:1;min-height:38px;max-height:120px;resize:none;border-radius:18px;padding:9px 12px;font:inherit;line-height:1.25;background:#2a3942;color:#fff;caret-color:#fff}#messageInput::placeholder{color:#9fb0bf;opacity:1}#messageSend{width:42px;height:42px;border-radius:50%;font-size:20px;background:#00a884;border-color:#00a884;color:#fff;padding:0;display:flex;align-items:center;justify-content:center}.msgCounter{font-size:10px;color:#91a4b3;min-width:52px;text-align:right;padding-bottom:11px}.msgCounter.over{color:#ff8f8f;font-weight:800}
  #messagesNav.unread{animation:messagesUnread 1.15s ease-in-out infinite;border-color:#53bdeb;box-shadow:0 0 0 1px rgba(83,189,235,.25)}@keyframes messagesUnread{0%,100%{background:#233443;color:#edf3f8}50%{background:#0b6f81;color:#fff}}
  .unreadCount{display:none;background:#25d366;color:#07140c;border-radius:10px;min-width:18px;padding:1px 5px;margin-left:4px;font-size:10px;font-weight:900}.unread .unreadCount{display:inline-block}
  @media(max-width:650px){.msgBubble{max-width:88%}.msgText{padding-right:46px}#messageList{padding:10px 8px}#messageComposer{padding:8px}.msgCounter{display:none}}

</style>
</head>
<body>
<div id="flowToast" title="Clique para abrir o mapa"></div>
<div id="app">
<header>
  <h1>__DISPLAY_TITLE__</h1>
  <div id="nav">
    <button class="navbtn active" data-view="map">Mapa</button>
    <button class="navbtn" data-view="traffic">Tráfego</button>
    <button class="navbtn" id="messagesNav" data-view="messages">Mensagens <span id="messagesUnreadCount" class="unreadCount">0</span></button>
    <button class="navbtn" data-view="health">Saúde da Rede</button>
    <button class="navbtn" data-view="anomalies">Anomalias</button>
    <button class="navbtn" data-view="settings">Configurações</button>
  </div>
</header>
<section id="viewMap" class="view active">
<div id="summary"></div>
<div id="playback">
  <label>Reprodução:
    <select id="playMode">
      <option value="history">Histórico</option>
      <option value="live" selected>Ao vivo</option>
    </select>
  </label>
  <button id="prevTrace" title="Traceroute anterior">⏮</button>
  <button id="playTrace" title="Reproduzir">▶</button>
  <button id="pauseTrace" title="Pausar">⏸</button>
  <button id="nextTrace" title="Próximo traceroute">⏭</button>
  <label>Velocidade:
    <select id="animSpeed">
      <option value="80">0,5x</option>
      <option value="150" selected>1x</option>
      <option value="280">2x</option>
      <option value="500">4x</option>
    </select>
  </label>
  <span id="playStatus">Histórico pronto.</span>
  <div class="mapActions"><button id="fit">Enquadrar</button><button id="reload">Atualizar</button></div>
</div>
<div id="map"></div>
</section>
<section id="viewTraffic" class="view">
  <div id="trafficToolbar">
    <b>Tráfego ao vivo</b>
    <span id="trafficLive" class="liveBadge">● AO VIVO</span>
    <label>Direção: <select id="trafficDirection"><option value="all">Todos</option><option value="rx">RX</option><option value="tx">TX</option></select></label>
    <label>Tipo: <select id="trafficType"><option value="all">Todos</option><option value="TEXT_MESSAGE_APP">Mensagem</option><option value="POSITION_APP">Position</option><option value="NODEINFO_APP">NodeInfo</option><option value="TELEMETRY_APP">Telemetry</option><option value="TRACEROUTE_APP">Traceroute</option><option value="ROUTING_APP">Routing</option><option value="NEIGHBORINFO_APP">NeighborInfo</option><option value="ADMIN_APP">Admin</option></select></label>
    <label>Buscar: <input id="trafficSearch" type="search" placeholder="nó, ID, tipo..." style="width:180px"></label>
    <button id="trafficPause">Pausar</button>
    <button id="trafficReload">Atualizar</button>
    <button id="trafficDump" class="downloadBtn" title="Baixa todo o histórico persistente em traffic.json dentro de um ZIP">Baixar dump JSON (.zip)</button>
  </div>
  <div id="trafficStats"></div>
  <div id="trafficBody">
    <div id="trafficTableWrap">
      <table class="trafficTable">
        <thead><tr><th>Hora</th><th>DIR</th><th>Origem</th><th>Destino</th><th>Tipo</th><th>SNR</th><th>RSSI</th><th>Hops</th><th>Canal</th></tr></thead>
        <tbody id="trafficRows"><tr><td colspan="9">Carregando pacotes...</td></tr></tbody>
      </table>
    </div>
    <aside id="packetDetail"><div class="emptyDetail">Clique em um pacote para ver os detalhes.</div></aside>
  </div>
</section>


<section id="viewMessages" class="view">
  <div id="messageHeader">
    <span class="msgTitle">Canal primário</span><span class="msgHint">Canal 0 - mensagens de broadcast</span>
    <span class="msgSpacer"></span><span id="messageStatus" class="msgHint">Carregando...</span><button id="messageLoadOlder" title="Carregar mais mensagens antigas">Carregar anteriores</button><button id="messageReload" title="Consultar novas mensagens agora">Atualizar</button>
  </div>
  <div id="messageList"><div class="emptyPanel">Carregando mensagens...</div></div>
  <div id="messageComposer">
    <textarea id="messageInput" rows="1" placeholder="Digite uma mensagem"></textarea><span id="messageCounter" class="msgCounter">0 B</span><button id="messageSend" title="Enviar">➤</button>
  </div>
</section>
<section id="viewHealth" class="view">
  <div class="dashboardWrap">
    <div class="dashboardToolbar"><h2>Saúde da Rede</h2><span id="healthUpdated" class="settingDesc"></span><button id="healthReload">Atualizar</button></div>
    <div id="healthCards" class="dashGrid"><div class="dashCard"><div class="label">Carregando...</div></div></div>
    <div class="dashSection"><h3>Atividade dos últimos 7 dias</h3><div class="dashSectionBody"><div id="healthDaily" class="miniBars"></div></div></div>
    <div class="dashSection"><h3>Traceroutes e roteamento</h3><div id="healthRoutes" class="dashSectionBody"></div></div>
    <div class="dashSection"><h3>Interações por chat no canal primário</h3><div class="dashSectionBody"><table class="dashTable" style="min-width:520px"><thead><tr><th>Nó</th><th>Interações</th></tr></thead><tbody id="healthChatRows"></tbody></table></div></div>
    <div class="dashSection"><h3>Nós que merecem atenção</h3><div class="dashSectionBody"><table class="dashTable"><thead><tr><th>Nó</th><th>Último tráfego</th><th>Tempo sem ouvir</th><th>Pacotes 7d</th><th>SNR médio 7d</th></tr></thead><tbody id="healthSilentRows"></tbody></table></div></div>
    <div class="methodNote">Os indicadores usam o histórico persistente do Traffic Analyzer e a topologia observada pelo MeshMonitor. O ranking de chat conta interações acumuladas registradas no canal primário. Ausência de tráfego não prova falha física; pode representar um nó silencioso, desligado ou fora do alcance da fonte.</div>
  </div>
</section>
<section id="viewAnomalies" class="view">
  <div class="dashboardWrap">
    <div class="dashboardToolbar"><h2>Detecção de Anomalias</h2><span id="anomalyUpdated" class="settingDesc"></span><button id="anomalyReload">Reanalisar</button></div>
    <div id="anomalyCards" class="dashGrid"><div class="dashCard"><div class="label">Analisando...</div></div></div>
    <div class="dashSection"><h3>Ocorrências detectadas</h3><div id="anomalyList"></div></div>
    <div class="dashSection"><h3>Como interpretar</h3><div class="dashSectionBody methodNote">As anomalias são heurísticas: silêncio prolongado, degradação de SNR, mudança relevante na quantidade de hops e traceroute assimétrico. Elas servem para priorizar investigação e não constituem prova isolada de defeito, indisponibilidade ou causalidade.</div></div>
  </div>
</section>

<section id="viewSettings" class="view">
  <div class="settingsCard">
    <h2>Configurações do Traffic Analyzer</h2>

    <h3>Mapa e topologia</h3>
    <div class="settingsGrid">
      <div class="settingRow">
        <label>Janela: <select id="ageHours"><option value="all" selected>Todos</option><option value="1">1 h</option><option value="6">6 h</option><option value="12">12 h</option><option value="24">24 h</option><option value="168">7 dias</option><option value="720">30 dias</option></select></label>
        <div class="settingDesc">Filtra enlaces e traceroutes pela idade da observação.</div>
      </div>
      <div class="settingRow">
        <label>Mínimo de observações: <input id="minObs" type="number" min="1" value="1" style="width:70px"></label>
        <div class="settingDesc">Oculta enlaces com menos observações que o valor escolhido.</div>
      </div>
      <div class="settingRow">
        <label>Mapa base: <select id="mapType"><option value="osm" selected>Ruas (OSM)</option><option value="topo">Topográfico</option><option value="light">Claro</option><option value="dark">Escuro</option><option value="satellite">Satélite</option></select></label>
      </div>
      <div class="settingRow">
        <label>Brilho: <input id="mapBrightness" type="range" min="30" max="150" step="5" value="100" style="width:150px;vertical-align:middle"> <span id="mapBrightnessValue">100%</span></label>
      </div>
      <div class="settingRow">
        <label>Cor das linhas: <input id="lineColor" type="color" value="#ffff00" style="width:48px;height:30px;padding:2px;vertical-align:middle"></label>
      </div>
      <div class="settingRow">
        <label><input id="showLines" type="checkbox" checked> Mostrar linhas</label><br>
        <label><input id="showNodes" type="checkbox" checked> Mostrar nós</label><br>
        <label><input id="showHeatmap" type="checkbox"> Mapa de calor</label>
      </div>
      <div class="settingRow">
        <label><input id="showShortNames" type="checkbox"> Mostrar nomes curtos</label><br>
        <label><input id="onlyIdentified" type="checkbox"> Mostrar somente identificados</label>
      </div>
      <div class="settingRow">
        <label><input id="autoZoomTraceroute" type="checkbox"> Auto Zoom durante traceroutes</label>
        <div class="settingDesc">Enquadra automaticamente todos os nós envolvidos nas animações de traceroute. Se houver animações simultâneas, usa a área combinada. Cinco segundos após a última terminar, retorna ao enquadramento anterior.</div>
      </div>
    </div>

    <h3>Notificações sonoras</h3>
    <div class="settingsGrid">
      <div class="settingRow">
        <label><input id="soundEnabled" type="checkbox"> Som no início de uma nova viagem de pacote</label>
        <div class="settingDesc">O som toca uma única vez quando uma nova viagem de pacote é observada. Cópias/retransmissões do mesmo packet_id não geram novos sons.</div>
      </div>
      <div class="settingRow">
        <label>Som: <select id="soundTone"><option value="plim">Plim</option><option value="chime">Campainha</option><option value="click">Click</option><option value="double">Duplo</option><option value="soft">Suave</option></select></label>
        <button id="soundTest" class="soundTest">Testar som</button>
        <div class="settingDesc">Todos os sons são sintetizados localmente; nenhum arquivo de áudio é baixado.</div>
      </div>
      <div class="settingRow">
        <label>Volume: <input id="soundVolume" type="range" min="0" max="100" step="5" value="35" style="width:180px;vertical-align:middle"> <span id="soundVolumeValue">35%</span></label>
        <div class="settingDesc">A preferência fica salva neste navegador. O primeiro clique libera o Web Audio quando exigido pelo navegador.</div>
      </div>
    </div>

    <h3>Atividade em tempo real no mapa</h3>
    <div class="settingsGrid">
      <div class="settingRow">
        <label><input id="activityAnimationEnabled" type="checkbox" checked> Animar atividade dos nós</label><br>
        <label><input id="activityOriginEnabled" type="checkbox" checked> Realçar origem/resposta</label><br>
        <label><input id="activityRelayEnabled" type="checkbox" checked> Realçar retransmissor observado</label>
        <div class="settingDesc">Cada atividade observada recebe um pulso visual no mapa. Só são destacados nós que podem ser identificados com segurança.</div>
      </div>
      <div class="settingRow">
        <label>Duração do realce: <select id="activityDuration"><option value="650">0,65 s</option><option value="1000" selected>1,0 s</option><option value="1500">1,5 s</option><option value="2000">2,0 s</option></select></label>
        <div class="settingDesc">Origem/resposta usa pulso azul/roxo; relay observado usa pulso amarelo. O Traffic Analyzer não inventa relays intermediários.</div>
      </div>
    </div>

    <h3>Fluxos e privacidade</h3>
    <div class="settingRow">
      <label><input id="nodeInfoFlowEnabled" type="checkbox" checked> Mostrar fluxo de NodeInfo no mapa</label>
      <div class="settingDesc">O mapa liga origem e destino. A animação por hops só usa rota observada quando existe traceroute completo compatível; sem evidência suficiente, nenhum hop é inventado.</div>
    </div>
    <div class="settingRow">
      <b>Conteúdo dos pacotes</b>
      <div class="settingDesc">Mensagens TEXT_MESSAGE em broadcast mostram o payload no detalhe. Mensagens diretas continuam ocultas por padrão. Payloads e dados técnicos são apresentados com rótulos amigáveis; o JSON bruto fica disponível apenas como diagnóstico secundário.</div>
    </div>
    <div class="settingRow">
      <b>Segurança</b>
      <div class="settingDesc">O token mm_v1 permanece no processo servidor e não é enviado ao navegador.</div>
    </div>
  </div>
</section>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
 integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>
<script>
const map = L.map('map', {preferCanvas:true}).setView([-15.8,-47.9], 9);

const baseMaps = {
  osm: {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: {maxZoom:19, attribution:'&copy; OpenStreetMap contributors'}
  },
  topo: {
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    options: {maxZoom:17, attribution:'Map data &copy; OpenStreetMap contributors, SRTM | Map style &copy; OpenTopoMap'}
  },
  light: {
    url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    options: {maxZoom:20, subdomains:'abcd', attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}
  },
  dark: {
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    options: {maxZoom:20, subdomains:'abcd', attribution:'&copy; OpenStreetMap contributors &copy; CARTO'}
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    options: {maxZoom:19, attribution:'Tiles &copy; Esri'}
  }
};

let baseLayer = null;
const lineLayer = L.layerGroup().addTo(map);
const nodeLayer = L.layerGroup().addTo(map);
const animationLayer = L.layerGroup().addTo(map);
const flowLayer = L.layerGroup().addTo(map);
const activityLayer = L.layerGroup().addTo(map);
const activityMarkers = new Map();
let heatLayer = null;
let topology = null;
const nodeTrafficLastSeen = new Map();
let lastBounds = null;
let historyIndex = 0;
let playbackRunning = false;
let animationGeneration = 0;
let livePollTimer = null;
let liveInitialized = false;
let liveSeen = new Set();
let liveQueue = [];
let liveProcessing = false;
let liveAnimationSeq = 0;
const activeLiveAnimations = new Map();
let autoZoomSavedCenter = null;
let autoZoomSavedZoom = null;
let autoZoomRestoreTimer = null;
let autoZoomEngaged = false;
const autoZoomActive = new Map();
const traceHudEntries = new Map();
let traceHudContainer = null;

const PREF_KEY = 'trafficAnalyzerPrefsV15';
function loadPrefs(){
  try {
    const current=localStorage.getItem(PREF_KEY);
    if(current) return JSON.parse(current);
    const legacy=localStorage.getItem('mmRouteMapPrefsV12');
    if(legacy){ const parsed=JSON.parse(legacy); localStorage.setItem(PREF_KEY,JSON.stringify(parsed)); return parsed; }
    return {};
  } catch { return {}; }
}
function savePrefs(){
  const prefs = {
    ageHours: document.getElementById('ageHours').value,
    minObs: Number(document.getElementById('minObs').value || 1),
    onlyIdentified: document.getElementById('onlyIdentified').checked,
    mapType: document.getElementById('mapType').value,
    brightness: Number(document.getElementById('mapBrightness').value || 100),
    lineColor: document.getElementById('lineColor').value || '#ffff00',
    showShortNames: document.getElementById('showShortNames').checked,
    showLines: document.getElementById('showLines').checked,
    showNodes: document.getElementById('showNodes').checked,
    showHeatmap: document.getElementById('showHeatmap').checked,
    animSpeed: Number(document.getElementById('animSpeed').value || 150),
    soundEnabled: document.getElementById('soundEnabled').checked,
    soundVolume: Number(document.getElementById('soundVolume').value || 35),
    soundTone: document.getElementById('soundTone').value || 'plim',
    activityAnimationEnabled: document.getElementById('activityAnimationEnabled').checked,
    activityOriginEnabled: document.getElementById('activityOriginEnabled').checked,
    activityRelayEnabled: document.getElementById('activityRelayEnabled').checked,
    activityDuration: Number(document.getElementById('activityDuration').value || 1000),
    autoZoomTraceroute: document.getElementById('autoZoomTraceroute').checked,
    nodeInfoFlowEnabled: document.getElementById('nodeInfoFlowEnabled').checked
  };
  localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
}
function setBaseMap(type){
  const cfg = baseMaps[type] || baseMaps.osm;
  if(baseLayer) map.removeLayer(baseLayer);
  baseLayer = L.tileLayer(cfg.url, cfg.options).addTo(map);
  baseLayer.bringToBack();
  applyBrightness();
}
function applyBrightness(){
  const value = Math.max(30, Math.min(150, Number(document.getElementById('mapBrightness').value || 100)));
  document.getElementById('mapBrightnessValue').textContent = `${value}%`;
  const pane = map.getPane('tilePane');
  if(pane) pane.style.filter = `brightness(${value}%)`;
}
function initVisualPrefs(){
  const prefs = loadPrefs();

  // v1.16.0: Ruas (OSM) volta a ser o mapa-base padrão.
  // A migração roda uma única vez para neutralizar o antigo padrão Satélite;
  // depois disso, qualquer escolha manual do usuário volta a ser preservada.
  if(Number(prefs.defaultsVersion || 0) < 140){
    prefs.mapType = 'osm';
    if(!prefs.lineColor || String(prefs.lineColor).toLowerCase() === '#ff0000') prefs.lineColor = '#ffff00';
    prefs.defaultsVersion = 140;
    localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
  }

  if(['all','1','6','12','24','168','720'].includes(String(prefs.ageHours))) document.getElementById('ageHours').value = String(prefs.ageHours);
  if(Number.isFinite(Number(prefs.minObs)) && Number(prefs.minObs)>=1) document.getElementById('minObs').value = String(Math.floor(Number(prefs.minObs)));
  document.getElementById('onlyIdentified').checked = Boolean(prefs.onlyIdentified);
  if(baseMaps[prefs.mapType]) document.getElementById('mapType').value = prefs.mapType;
  if(Number.isFinite(Number(prefs.brightness))) document.getElementById('mapBrightness').value = String(prefs.brightness);
  if(/^#[0-9a-fA-F]{6}$/.test(prefs.lineColor || '')) document.getElementById('lineColor').value = prefs.lineColor;
  if(typeof prefs.showShortNames === 'boolean') document.getElementById('showShortNames').checked = prefs.showShortNames;
  document.getElementById('showLines').checked = (typeof prefs.showLines === 'boolean') ? prefs.showLines : true;
  document.getElementById('showNodes').checked = (typeof prefs.showNodes === 'boolean') ? prefs.showNodes : true;
  document.getElementById('showHeatmap').checked = (typeof prefs.showHeatmap === 'boolean') ? prefs.showHeatmap : false;
  if([80,150,280,500].includes(Number(prefs.animSpeed))) document.getElementById('animSpeed').value = String(prefs.animSpeed);
  document.getElementById('soundEnabled').checked = Boolean(prefs.soundEnabled);
  if(Number.isFinite(Number(prefs.soundVolume))) document.getElementById('soundVolume').value = String(Math.max(0,Math.min(100,Number(prefs.soundVolume))));
  if(['plim','chime','click','double','soft'].includes(prefs.soundTone)) document.getElementById('soundTone').value = prefs.soundTone;
  document.getElementById('activityAnimationEnabled').checked = (typeof prefs.activityAnimationEnabled === 'boolean') ? prefs.activityAnimationEnabled : true;
  document.getElementById('activityOriginEnabled').checked = (typeof prefs.activityOriginEnabled === 'boolean') ? prefs.activityOriginEnabled : true;
  document.getElementById('activityRelayEnabled').checked = (typeof prefs.activityRelayEnabled === 'boolean') ? prefs.activityRelayEnabled : true;
  if([650,1000,1500,2000].includes(Number(prefs.activityDuration))) document.getElementById('activityDuration').value = String(prefs.activityDuration);
  document.getElementById('autoZoomTraceroute').checked = (typeof prefs.autoZoomTraceroute === 'boolean') ? prefs.autoZoomTraceroute : false;
  document.getElementById('nodeInfoFlowEnabled').checked = (typeof prefs.nodeInfoFlowEnabled === 'boolean') ? prefs.nodeInfoFlowEnabled : true;
  document.getElementById('soundVolumeValue').textContent = `${document.getElementById('soundVolume').value}%`;
  setBaseMap(document.getElementById('mapType').value);
  applyBrightness();
}

const esc = (x) => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dt = (ms) => ms ? new Date(ms).toLocaleString('pt-BR') : '—';
const snr = (v) => (v === null || v === undefined) ? '—' : `${Number(v).toFixed(1)} dB`;

function nodeLastTrafficMs(n){
  const archived=Number(nodeTrafficLastSeen.get(Number(n.nodeNum))||0);
  const heard=Number(n.lastHeard||0)>0 ? Number(n.lastHeard)*1000 : 0;
  return Math.max(Number.isFinite(archived)?archived:0, Number.isFinite(heard)?heard:0);
}
function humanAge(ms){
  if(!ms) return 'sem registro';
  let sec=Math.max(0,Math.floor((Date.now()-Number(ms))/1000));
  if(sec<60) return sec<=1?'há poucos segundos':`há ${sec} segundos`;
  const min=Math.floor(sec/60); if(min<60) return `há ${min} ${min===1?'minuto':'minutos'}`;
  const h=Math.floor(min/60), m=min%60;
  if(h<24) return `há ${h} ${h===1?'hora':'horas'}${m?` e ${m} ${m===1?'minuto':'minutos'}`:''}`;
  const d=Math.floor(h/24), rh=h%24;
  return `há ${d} ${d===1?'dia':'dias'}${rh?` e ${rh} ${rh===1?'hora':'horas'}`:''}`;
}

function nodeTrafficAge(n){
  const ts=nodeLastTrafficMs(n);
  if(!ts) return {color:'#7f8c8d',label:'Sem tráfego registrado',className:'trafficUnknown',ts:0};
  const age=Math.max(0,Date.now()-ts);
  if(age<=2*3600*1000) return {color:'#2ecc71',label:'Tráfego nas últimas 2 h',className:'trafficFresh',ts};
  if(age<=24*3600*1000) return {color:'#f39c12',label:'Tráfego entre 2 e 24 h',className:'trafficWarm',ts};
  return {color:'#e74c3c',label:'Tráfego há mais de 24 h',className:'trafficOld',ts};
}

function cutoffForSelection(){
  const value = document.getElementById('ageHours').value;
  if(value === 'all') return null;
  const h = Number(value);
  return (topology?.generatedAtMs || Date.now()) - h * 3600 * 1000;
}

function edgeStatsForWindow(e, cutoff){
  const events = Array.isArray(e.events) ? e.events : null;
  if(!events){
    if(cutoff !== null && (e.lastSeenMs || 0) < cutoff) return null;
    return {
      observations:Number(e.observations || 0),
      forward:Number(e.forwardObservations || 0),
      back:Number(e.returnObservations || 0),
      avgSnr:e.avgSnr, minSnr:e.minSnr, maxSnr:e.maxSnr,
      lastSeenMs:e.lastSeenMs, latestTraceId:e.latestTraceId, latestChannel:e.latestChannel
    };
  }
  const active = cutoff === null ? events : events.filter(x => Number(x.timestampMs || 0) >= cutoff);
  if(!active.length) return null;
  const snrs = active.map(x => x.snr).filter(x => x !== null && x !== undefined && Number.isFinite(Number(x))).map(Number);
  const latest = active.reduce((a,b) => Number(a.timestampMs||0) >= Number(b.timestampMs||0) ? a : b);
  return {
    observations:active.length,
    forward:active.filter(x => x.leg === 'forward').length,
    back:active.filter(x => x.leg === 'return').length,
    avgSnr:snrs.length ? snrs.reduce((a,b)=>a+b,0)/snrs.length : null,
    minSnr:snrs.length ? Math.min(...snrs) : null,
    maxSnr:snrs.length ? Math.max(...snrs) : null,
    lastSeenMs:Number(latest.timestampMs || e.lastSeenMs || 0),
    latestTraceId:latest.traceId ?? e.latestTraceId,
    latestChannel:e.latestChannel
  };
}

function render(){
  if(!topology) return;
  lineLayer.clearLayers();
  nodeLayer.clearLayers();
  if(heatLayer){ map.removeLayer(heatLayer); heatLayer = null; }

  const cutoff = cutoffForSelection();
  const minObs = Math.max(1, Number(document.getElementById('minObs').value || 1));
  const onlyIdentified = document.getElementById('onlyIdentified').checked;
  const showShortNames = document.getElementById('showShortNames').checked;
  const showLines = document.getElementById('showLines').checked;
  const showNodes = document.getElementById('showNodes').checked;
  const showHeatmap = document.getElementById('showHeatmap').checked;
  const nodeMap = new Map((topology.nodes || []).map(n => [Number(n.nodeNum), n]));
  const visibleNodes = new Set();
  const heatWeights = new Map();
  let edgeCount = 0;

  for(const e of topology.edges || []){
    if(!e.geometry) continue;
    const stats = edgeStatsForWindow(e, cutoff);
    if(!stats || stats.observations < minObs) continue;
    const a = nodeMap.get(Number(e.a)), b = nodeMap.get(Number(e.b));
    if(onlyIdentified && ((a?.state !== 'identified') || (b?.state !== 'identified'))) continue;

    visibleNodes.add(Number(e.a)); visibleNodes.add(Number(e.b)); edgeCount++;
    const obs = Math.max(1, Number(stats.observations || 1));
    heatWeights.set(Number(e.a), (heatWeights.get(Number(e.a)) || 0) + obs);
    heatWeights.set(Number(e.b), (heatWeights.get(Number(e.b)) || 0) + obs);

    if(showLines){
      const lineColor = document.getElementById('lineColor').value || '#ffff00';
      const line = L.polyline(e.geometry, {weight:3, opacity:.82, color:lineColor});
      line.bindPopup(
        `<b>${esc(e.aName)} ↔ ${esc(e.bName)}</b><br>`+
        `${esc(e.aId)} ↔ ${esc(e.bId)}<br>`+
        `Observações: <b>${stats.observations}</b><br>`+
        `Ida: ${stats.forward} | Volta: ${stats.back}<br>`+
        `SNR médio: ${snr(stats.avgSnr)}<br>`+
        `Faixa SNR: ${snr(stats.minSnr)} a ${snr(stats.maxSnr)}<br>`+
        `Última observação: ${dt(stats.lastSeenMs)}<br>`+
        `Traceroute: ${esc(stats.latestTraceId ?? '—')} | canal: ${esc(stats.latestChannel ?? '—')}`
      );
      line.addTo(lineLayer);
    }
  }

  if(showHeatmap && typeof L.heatLayer === 'function' && heatWeights.size){
    const maxWeight = Math.max(...heatWeights.values(), 1);
    const heatPoints = [];
    for(const [nodeNum, weight] of heatWeights.entries()){
      const n = nodeMap.get(nodeNum);
      if(!n || n.latitude === null || n.longitude === null) continue;
      if(onlyIdentified && n.state !== 'identified') continue;
      const intensity = Math.max(.08, Math.log1p(weight) / Math.log1p(maxWeight));
      heatPoints.push([n.latitude, n.longitude, intensity]);
    }
    if(heatPoints.length){
      heatLayer = L.heatLayer(heatPoints, {
        radius:34, blur:24, maxZoom:13, minOpacity:.28,
        gradient:{0.15:'#2b83ba',0.35:'#abdda4',0.55:'#ffffbf',0.75:'#fdae61',1:'#d7191c'}
      }).addTo(map);
    }
  }

  const coords = [];
  let markerCount = 0, mappableCount = 0;
  const mappableStates = {identified:0, stub:0, 'route-only':0};
  for(const n of topology.nodes || []){
    if(n.latitude === null || n.longitude === null) continue;
    if(onlyIdentified && n.state !== 'identified') continue;
    mappableCount++;
    mappableStates[n.state] = (mappableStates[n.state] || 0) + 1;
    coords.push([n.latitude,n.longitude]);
    if(!showNodes) continue;

    const trafficAge=nodeTrafficAge(n);
    const marker = L.circleMarker([n.latitude,n.longitude], {
      radius:n.state === 'identified' ? 6 : 7,
      color:trafficAge.color, fillColor:trafficAge.color, fillOpacity:.90, weight:2
    });
    if(showShortNames && n.shortName){
      marker.bindTooltip(esc(n.shortName), {direction:'top', permanent:true, className:'short-label', offset:[0,-7]});
    } else {
      marker.bindTooltip(esc(n.name || n.nodeId), {direction:'top'});
    }
    marker.bindPopup(
      `<b>${esc(n.name || n.nodeId)}</b><br>`+
      `${esc(n.nodeId)}<br>`+
      `Short name: ${esc(n.shortName ?? '—')}<br>`+
      `Estado: <b>${esc(n.state)}</b><br>`+
      `Posição: ${esc(n.positionSource || '—')}<br>`+
      `Hops: ${esc(n.hopsAway ?? '—')} | SNR: ${snr(n.snr)} | RSSI: ${esc(n.rssi ?? '—')}<br>`+
      `Hardware: ${esc(n.hwModel ?? '—')} | Role: ${esc(n.role ?? '—')}<br>`+
      `Public key: ${n.publicKey ? 'sim' : 'não'}<br>`+
      `Último tráfego: ${trafficAge.ts ? new Date(trafficAge.ts).toLocaleString('pt-BR') : '—'}<br>`+
      `Situação: <b>${esc(trafficAge.label)}</b>${trafficAge.ts ? ` - ouvido ${esc(humanAge(trafficAge.ts))}` : ''}`
    );
    marker.addTo(nodeLayer); markerCount++;
  }

  const traceCount = (topology.traces || []).filter(t => cutoff === null || Number(t.timestampMs||0) >= cutoff).length;
  lastBounds = coords.length ? L.latLngBounds(coords) : null;
  document.getElementById('summary').innerHTML =
    `<span class="metric"><b>${edgeCount}</b> enlaces no filtro</span>`+
    `<span class="metric"><b>${mappableCount}</b> nós no mapa</span>`+
    `<span class="metric"><b>${mappableStates.identified || 0}</b> identificados</span>`+
    `<span class="metric"><b>${mappableStates.stub || 0}</b> stubs</span>`+
    `<span class="metric"><b>${mappableStates['route-only'] || 0}</b> route-only</span>`+
    `<span class="metric"><b>${traceCount}</b> traceroutes no histórico</span>`+
    (showNodes ? `<span class="metric"><b>${markerCount}</b> círculos visíveis</span>` : '')+
    (showHeatmap ? `<span class="metric warn">Calor = atividade de roteamento observada</span>` : '')+
    `<span class="metric warn">Linhas = adjacências observadas, não enlaces permanentes</span>`;
  updatePlaybackStatusIdle();
}

const INVALID_NODES = new Set([0,1,2,3,255,65535,4294967295]);
function parseJsonArray(v){
  if(Array.isArray(v)) return v.map(Number);
  if(v === null || v === undefined || v === '' || v === 'null') return [];
  try { const x = JSON.parse(v); return Array.isArray(x) ? x.map(Number) : []; } catch { return []; }
}
function parseRoutePositions(v){
  if(!v) return {};
  try { return typeof v === 'string' ? JSON.parse(v) : v; } catch { return {}; }
}
function pointForLive(nodeNum, positions){
  const p = positions?.[String(nodeNum)] ?? positions?.[nodeNum];
  if(p && Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lng)))
    return {nodeNum, nodeId:`!${(nodeNum>>>0).toString(16).padStart(8,'0')}`, name:(topology?.nodes||[]).find(n=>Number(n.nodeNum)===nodeNum)?.name || `!${(nodeNum>>>0).toString(16).padStart(8,'0')}`, lat:Number(p.lat), lon:Number(p.lng)};
  const n = (topology?.nodes || []).find(x => Number(x.nodeNum) === nodeNum);
  if(n && n.latitude !== null && n.longitude !== null)
    return {nodeNum, nodeId:n.nodeId, name:n.name || n.nodeId, lat:Number(n.latitude), lon:Number(n.longitude)};
  return null;
}
function liveLeg(start, midsRaw, end, positions){
  const nums = [Number(start), ...parseJsonArray(midsRaw), Number(end)].map(x => x >>> 0);
  if(nums.some(n => INVALID_NODES.has(n))) return null;
  const pts = nums.map(n => pointForLive(n, positions));
  return pts.every(Boolean) ? pts : null;
}
function normalizeLiveTrace(tr){
  const fromNum = Number(tr.fromNodeNum) >>> 0, toNum = Number(tr.toNodeNum) >>> 0;
  if(INVALID_NODES.has(fromNum) || INVALID_NODES.has(toNum)) return null;
  const positions = parseRoutePositions(tr.routePositions);
  const forward = (tr.route !== null && tr.route !== undefined && tr.route !== '' && tr.route !== 'null') ? liveLeg(fromNum, tr.route, toNum, positions) : null;
  const rb = parseJsonArray(tr.routeBack);
  const hasBack = rb.length > 0 || (tr.snrBack && tr.snrBack !== '[]' && tr.snrBack !== 'null');
  const back = hasBack ? liveLeg(toNum, tr.routeBack, fromNum, positions) : null;
  const nodeMap = new Map((topology?.nodes || []).map(n => [Number(n.nodeNum), n]));
  return {
    id:tr.id, packetId:tr.packetId,
    timestampMs:Number(tr.timestamp || tr.createdAt || Date.now()) < 10000000000 ? Number(tr.timestamp || tr.createdAt || Date.now())*1000 : Number(tr.timestamp || tr.createdAt || Date.now()),
    fromNodeNum:fromNum, toNodeNum:toNum,
    fromNodeId:tr.fromNodeId || `!${fromNum.toString(16).padStart(8,'0')}`,
    toNodeId:tr.toNodeId || `!${toNum.toString(16).padStart(8,'0')}`,
    fromName:nodeMap.get(fromNum)?.name || tr.fromNodeId || `!${fromNum.toString(16).padStart(8,'0')}`,
    toName:nodeMap.get(toNum)?.name || tr.toNodeId || `!${toNum.toString(16).padStart(8,'0')}`,
    channel:tr.channel,
    forwardPath:forward, returnPath:back,
    animatable:Boolean((forward && forward.length>1) || (back && back.length>1))
  };
}
function traceKey(t){ return `${t.id ?? ''}:${t.packetId ?? ''}:${t.timestamp ?? t.timestampMs ?? ''}:${t.fromNodeNum}:${t.toNodeNum}`; }
function historyTraces(){
  const cutoff = cutoffForSelection();
  return (topology?.traces || []).filter(t => t.animatable && (cutoff === null || Number(t.timestampMs||0) >= cutoff));
}
function geoDistanceMeters(a,b){
  if(!a || !b) return null;
  if(!Number.isFinite(Number(a.lat)) || !Number.isFinite(Number(a.lon)) || !Number.isFinite(Number(b.lat)) || !Number.isFinite(Number(b.lon))) return null;
  return L.latLng(Number(a.lat),Number(a.lon)).distanceTo(L.latLng(Number(b.lat),Number(b.lon)));
}
function pathDistanceMeters(points){
  if(!points || points.length<2) return null;
  let total=0;
  for(let i=0;i<points.length-1;i++){
    const d=geoDistanceMeters(points[i],points[i+1]);
    if(!Number.isFinite(d)) return null;
    total+=d;
  }
  return total;
}
function fmtDistance(m){
  if(!Number.isFinite(Number(m))) return '—';
  const v=Number(m);
  if(v<1000) return `${Math.round(v).toLocaleString('pt-BR')} m`;
  return `${(v/1000).toLocaleString('pt-BR',{minimumFractionDigits:v<10000?1:0,maximumFractionDigits:1})} km`;
}
function traceDistanceInfo(trace){
  const forward=pathDistanceMeters(trace?.forwardPath);
  const back=pathDistanceMeters(trace?.returnPath);
  const a=trace?.forwardPath?.[0] || trace?.returnPath?.[trace?.returnPath?.length-1];
  const b=trace?.forwardPath?.[trace?.forwardPath?.length-1] || trace?.returnPath?.[0];
  const direct=geoDistanceMeters(a,b);
  const roundTrip=(Number.isFinite(forward)&&Number.isFinite(back)) ? forward+back : null;
  const known=[forward,back].filter(Number.isFinite).reduce((x,y)=>x+y,0);
  return {direct,forward,back,roundTrip,known};
}
function ensureTraceHud(){
  if(traceHudContainer) return;
  const ctrl=L.control({position:'bottomleft'});
  ctrl.onAdd=()=>{
    traceHudContainer=L.DomUtil.create('div','traceHud');
    L.DomEvent.disableClickPropagation(traceHudContainer);
    return traceHudContainer;
  };
  ctrl.addTo(map);
}
function renderTraceHud(){
  ensureTraceHud();
  if(!traceHudContainer) return;
  const entries=[...traceHudEntries.values()];
  traceHudContainer.innerHTML=entries.map(e=>{
    const d=e.dist;
    const topTotal=Number.isFinite(d.roundTrip) ? `Total ida + volta: ${fmtDistance(d.roundTrip)}` : (d.known>0 ? `Total conhecido: ${fmtDistance(d.known)}` : 'Total ida + volta: —');
    const idaClass=e.leg==='forward'?' active':'';
    const voltaClass=e.leg==='return'?' active':'';
    const ida=e.trace.forwardPath?.length>1 ? `<span class="forward">IDA</span> · direta ${fmtDistance(d.direct)} · percurso ${fmtDistance(d.forward)}` : `<span class="forward">IDA</span> · <span class="traceHudDim">sem percurso completo</span>`;
    const volta=e.trace.returnPath?.length>1 ? `<span class="return">VOLTA</span> · direta ${fmtDistance(d.direct)} · percurso ${fmtDistance(d.back)}` : `<span class="return">VOLTA</span> · <span class="traceHudDim">sem percurso completo</span>`;
    return `<div class="traceHudItem"><div class="traceHudHead">${esc(e.trace.fromName)} → ${esc(e.trace.toName)} <span class="traceHudTotal">${esc(topTotal)}</span></div><div class="traceHudLeg${idaClass}">${ida}</div><div class="traceHudLeg${voltaClass}">${volta}</div></div>`;
  }).join('');
}
function beginTraceHud(key,trace){
  traceHudEntries.set(key,{trace,dist:traceDistanceInfo(trace),leg:null});
  renderTraceHud();
}
function setTraceHudLeg(key,leg){
  const e=traceHudEntries.get(key); if(!e) return;
  e.leg=leg; renderTraceHud();
}
function endTraceHud(key){ traceHudEntries.delete(key); renderTraceHud(); }
function clearTraceHud(){ traceHudEntries.clear(); renderTraceHud(); }
function updatePlaybackStatusIdle(){
  const el = document.getElementById('playStatus');
  if(document.getElementById('playMode').value === 'live'){
    if(!liveInitialized) el.innerHTML = '<span class="liveBadge">AO VIVO</span> · conectando…';
    else if(!liveQueue.length && activeLiveAnimations.size===0) el.innerHTML = '<span class="liveBadge">AO VIVO</span>';
    else if(activeLiveAnimations.size>1) el.innerHTML = `<span class="liveBadge">AO VIVO</span> · ${activeLiveAnimations.size} traceroutes simultâneos`;
    else if(activeLiveAnimations.size===1) el.innerHTML = '<span class="liveBadge">AO VIVO</span> · 1 traceroute em animação';
    return;
  }
  if(playbackRunning) return;
  const list = historyTraces();
  if(historyIndex >= list.length) historyIndex = Math.max(0, list.length-1);
  el.textContent = list.length ? `Histórico: ${list.length} traceroutes animáveis · posição ${historyIndex+1}/${list.length}` : 'Histórico: nenhum traceroute completamente mapeável no filtro atual.';
}
function pathNames(path){ return (path || []).map(p => p.name || p.nodeId).join(' → '); }
function setTraceStatus(trace, leg, idx, total){
  const mode = document.getElementById('playMode').value === 'live' ? '<span class="liveBadge">AO VIVO</span>' : `Histórico ${idx+1}/${total}`;
  const path = leg === 'return' ? trace.returnPath : trace.forwardPath;
  document.getElementById('playStatus').innerHTML = `${mode} · ${dt(trace.timestampMs)} · ${leg === 'return' ? 'VOLTA' : 'IDA'} · ${esc(pathNames(path))}`;
}
function stopAnimation(){
  playbackRunning = false;
  animationGeneration++;
  activeLiveAnimations.clear();
  liveProcessing = false;
  animationLayer.clearLayers();
  clearTraceHud();
  updatePlaybackStatusIdle();
}
function latLngAt(points, segIndex, ratio){
  const a=points[segIndex], b=points[segIndex+1];
  return L.latLng(a.lat + (b.lat-a.lat)*ratio, a.lon + (b.lon-a.lon)*ratio);
}
function traceBounds(trace){
  const pts=[...(trace?.forwardPath||[]),...(trace?.returnPath||[])].filter(p=>Number.isFinite(Number(p?.lat))&&Number.isFinite(Number(p?.lon)));
  if(!pts.length) return null;
  const b=L.latLngBounds(pts.map(p=>[Number(p.lat),Number(p.lon)]));
  return b.isValid()?b:null;
}
function refitAutoZoom(){
  if(!autoZoomEngaged || !document.getElementById('autoZoomTraceroute').checked) return;
  let combined=null;
  for(const b of autoZoomActive.values()){
    if(!b || !b.isValid()) continue;
    if(!combined) combined=L.latLngBounds(b.getSouthWest(),b.getNorthEast());
    else combined.extend(b);
  }
  if(combined && combined.isValid() && document.getElementById('viewMap').classList.contains('active')){
    map.fitBounds(combined.pad(.12),{maxZoom:15,animate:true});
  }
}
function beginAutoZoom(key,trace){
  if(!document.getElementById('autoZoomTraceroute').checked) return false;
  const b=traceBounds(trace);
  if(!b) return false;
  if(autoZoomRestoreTimer){ clearTimeout(autoZoomRestoreTimer); autoZoomRestoreTimer=null; }
  if(!autoZoomEngaged){
    autoZoomSavedCenter=map.getCenter();
    autoZoomSavedZoom=map.getZoom();
    autoZoomEngaged=true;
  }
  autoZoomActive.set(key,b);
  refitAutoZoom();
  return true;
}
function endAutoZoom(key){
  autoZoomActive.delete(key);
  if(!autoZoomEngaged) return;
  if(autoZoomActive.size){ refitAutoZoom(); return; }
  if(autoZoomRestoreTimer) clearTimeout(autoZoomRestoreTimer);
  autoZoomRestoreTimer=setTimeout(()=>{
    if(!autoZoomEngaged || autoZoomActive.size) return;
    const center=autoZoomSavedCenter, zoom=autoZoomSavedZoom;
    autoZoomEngaged=false; autoZoomSavedCenter=null; autoZoomSavedZoom=null; autoZoomRestoreTimer=null;
    if(center && Number.isFinite(Number(zoom)) && document.getElementById('viewMap').classList.contains('active')) map.setView(center,zoom,{animate:true});
  },5000);
}
function disableAutoZoomAndRestore(){
  if(autoZoomRestoreTimer){ clearTimeout(autoZoomRestoreTimer); autoZoomRestoreTimer=null; }
  autoZoomActive.clear();
  const center=autoZoomSavedCenter, zoom=autoZoomSavedZoom;
  const shouldRestore=autoZoomEngaged && center && Number.isFinite(Number(zoom));
  autoZoomEngaged=false; autoZoomSavedCenter=null; autoZoomSavedZoom=null;
  if(shouldRestore && document.getElementById('viewMap').classList.contains('active')) map.setView(center,zoom,{animate:true});
}
function animatePath(points, color, isActive){
  return new Promise(resolve => {
    if(!points || points.length < 2){ resolve(true); return; }
    const latlngs = points.map(p => L.latLng(p.lat,p.lon));
    const screen = latlngs.map(ll => map.latLngToContainerPoint(ll));
    const lengths=[]; let total=0;
    for(let i=0;i<screen.length-1;i++){ const d=screen[i].distanceTo(screen[i+1]); lengths.push(d); total+=d; }
    if(total < 1){ resolve(true); return; }
    const speed = Math.max(20, Number(document.getElementById('animSpeed').value || 150));
    const routeGlow = L.polyline(latlngs,{color,weight:5,opacity:.38,dashArray:'8 7',interactive:false}).addTo(animationLayer);
    const pulse = L.circleMarker(latlngs[0],{radius:7,color:'#ffffff',weight:2,fillColor:color,fillOpacity:1,interactive:false}).addTo(animationLayer);
    const emitted = new Set();
    const emitNode = (idx) => {
      if(idx < 0 || idx >= points.length || emitted.has(idx)) return;
      emitted.add(idx);
      const n = Number(points[idx]?.nodeNum);
      if(!Number.isFinite(n) || INVALID_NODES.has(n>>>0)) return;
      const kind = idx===0 ? 'origin' : (idx===points.length-1 ? 'response' : 'relay');
      activityPulseAtPoint(points[idx],n>>>0,kind);
    };
    emitNode(0);
    const start=performance.now();
    function cleanup(){
      try{ animationLayer.removeLayer(pulse); }catch{}
      try{ animationLayer.removeLayer(routeGlow); }catch{}
    }
    function frame(now){
      if(!isActive()){ cleanup(); resolve(false); return; }
      const travelled=((now-start)/1000)*speed;
      if(travelled >= total){
        pulse.setLatLng(latlngs[latlngs.length-1]);
        for(let i=1;i<points.length;i++) emitNode(i);
        cleanup(); resolve(true); return;
      }
      let rem=travelled, seg=0;
      while(seg<lengths.length-1 && rem>lengths[seg]){ rem-=lengths[seg]; seg++; }
      // Quando o marcador alcança um novo hop, o nó também recebe o pulso de
      // atividade. A linha continua animada de forma independente.
      for(let i=1;i<=seg;i++) emitNode(i);
      const ratio=lengths[seg] ? Math.max(0,Math.min(1,rem/lengths[seg])) : 1;
      pulse.setLatLng(latLngAt(points,seg,ratio));
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  });
}
async function animateTrace(trace, isActive, idx=0, total=1, hudKey=null){
  if(trace.forwardPath?.length > 1){
    if(hudKey) setTraceHudLeg(hudKey,'forward');
    setTraceStatus(trace,'forward',idx,total);
    if(!await animatePath(trace.forwardPath,'#00e5ff',isActive)) return false;
  }
  if(trace.returnPath?.length > 1){
    if(hudKey) setTraceHudLeg(hudKey,'return');
    setTraceStatus(trace,'return',idx,total);
    if(!await animatePath(trace.returnPath,'#ff4fd8',isActive)) return false;
  }
  return true;
}
async function playHistoryLoop(){
  stopLivePolling();
  const list=historyTraces();
  if(!list.length){ updatePlaybackStatusIdle(); return; }
  playbackRunning=true;
  if(historyIndex>=list.length) historyIndex=0;
  const generation=++animationGeneration;
  const active=()=>playbackRunning && generation===animationGeneration && document.getElementById('playMode').value==='history';
  while(active() && historyIndex<list.length){
    const trace=list[historyIndex];
    const autoKey=`history:${generation}:${historyIndex}`;
    const zoomed=beginAutoZoom(autoKey,trace);
    beginTraceHud(autoKey,trace);
    let ok=false;
    try{ ok=await animateTrace(trace,active,historyIndex,list.length,autoKey); }
    finally{ endTraceHud(autoKey); if(zoomed) endAutoZoom(autoKey); }
    if(!ok) break;
    historyIndex++;
  }
  if(generation===animationGeneration){
    playbackRunning=false;
    if(historyIndex>=list.length){ historyIndex=0; document.getElementById('playStatus').textContent=`Histórico concluído · ${list.length} traceroutes reproduzidos`; }
    else updatePlaybackStatusIdle();
  }
}
async function playHistoryOnce(index){
  stopLivePolling();
  const list=historyTraces();
  if(!list.length){ updatePlaybackStatusIdle(); return; }
  historyIndex=Math.max(0,Math.min(index,list.length-1));
  playbackRunning=true;
  const generation=++animationGeneration;
  const active=()=>playbackRunning && generation===animationGeneration && document.getElementById('playMode').value==='history';
  const trace=list[historyIndex];
  const autoKey=`history-once:${generation}:${historyIndex}`;
  const zoomed=beginAutoZoom(autoKey,trace);
  beginTraceHud(autoKey,trace);
  try{ await animateTrace(trace,active,historyIndex,list.length,autoKey); }
  finally{ endTraceHud(autoKey); if(zoomed) endAutoZoom(autoKey); }
  if(generation===animationGeneration){ playbackRunning=false; updatePlaybackStatusIdle(); }
}
async function pollLive(){
  if(document.getElementById('playMode').value !== 'live') return;
  try{
    const r=await fetch('/api/live-traceroutes?limit=100',{cache:'no-store'});
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    const body=await r.json();
    const rows=(body.data || []).slice().sort((a,b)=>Number(a.timestamp||a.createdAt||0)-Number(b.timestamp||b.createdAt||0));
    if(!liveInitialized){
      rows.forEach(x=>liveSeen.add(traceKey(x)));
      liveInitialized=true; updatePlaybackStatusIdle(); return;
    }
    const fresh=[];
    for(const row of rows){
      const key=traceKey(row);
      if(liveSeen.has(key)) continue;
      liveSeen.add(key);
      const t=normalizeLiveTrace(row);
      if(t?.animatable) fresh.push(t);
    }
    if(fresh.length){ liveQueue.push(...fresh); if(liveQueue.length>250) liveQueue=liveQueue.slice(-250); processLiveQueue(); }
  }catch(e){ document.getElementById('playStatus').innerHTML=`<span class="liveBadge">AO VIVO</span> · erro: ${esc(e)}`; }
}
function runLiveTrace(trace){
  const token=++liveAnimationSeq;
  activeLiveAnimations.set(token,{trace});
  liveProcessing=true;
  const autoKey=`live:${token}`;
  const zoomed=beginAutoZoom(autoKey,trace);
  beginTraceHud(autoKey,trace);
  const active=()=>playbackRunning && document.getElementById('playMode').value==='live' && activeLiveAnimations.has(token);
  (async()=>{
    try{
      await animateTrace(trace,active,0,1,autoKey);
    } finally {
      endTraceHud(autoKey);
      if(zoomed) endAutoZoom(autoKey);
      activeLiveAnimations.delete(token);
      liveProcessing=activeLiveAnimations.size>0;
      updatePlaybackStatusIdle();
    }
  })();
}
function processLiveQueue(){
  if(!playbackRunning || document.getElementById('playMode').value !== 'live') return;
  // Cada traceroute novo ganha sua própria animação. Assim, um novo evento começa
  // imediatamente mesmo quando outro traceroute ainda está percorrendo o mapa.
  while(liveQueue.length){ runLiveTrace(liveQueue.shift()); }
  updatePlaybackStatusIdle();
}
function startLivePolling(){
  if(livePollTimer) clearInterval(livePollTimer);
  liveSeen=new Set(); liveQueue=[]; liveInitialized=false; liveProcessing=false;
  activeLiveAnimations.clear();
  playbackRunning=true;
  pollLive();
  livePollTimer=setInterval(pollLive,3000);
}
function stopLivePolling(){
  if(livePollTimer){ clearInterval(livePollTimer); livePollTimer=null; }
  activeLiveAnimations.clear();
  liveProcessing=false;
  for(const key of [...traceHudEntries.keys()]) if(String(key).startsWith('live:')) traceHudEntries.delete(key);
  renderTraceHud();
}


// ---------------- Traffic Analyzer: packet monitor ----------------
let trafficPackets=[];
let trafficInitialized=false;
let trafficLastTs=0;
let trafficTimer=null;
let trafficPaused=false;
let trafficTotal=0;
let selectedPacketId=null;
let audioCtx=null;
let lastSoundAt=0;
let journeySeen=new Set();
let flowGeneration=0;
let flowToastTimer=null;
let nodeInfoRecent=new Map();
let nodeInfoTriggered=new Set();
const NODEINFO_PAIR_WINDOW_MS=45000;
const NODEINFO_TRACE_WINDOW_MS=180000;
const NODEINFO_ROUTE_WAIT_MS=30000;

function setView(name){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.querySelectorAll('.navbtn').forEach(b=>b.classList.toggle('active',b.dataset.view===name));
  const ids={map:'viewMap',traffic:'viewTraffic',messages:'viewMessages',health:'viewHealth',anomalies:'viewAnomalies',settings:'viewSettings'};
  const target=document.getElementById(ids[name]||'viewMap');
  target.classList.add('active');
  if(name==='map') setTimeout(()=>map.invalidateSize(),40);
  if(name==='traffic' && !trafficInitialized) loadTrafficInitial();
  if(name==='messages'){ loadPrimaryMessages(true); markMessagesRead(); }
  if(name==='health') loadNetworkHealth();
  if(name==='anomalies') loadAnomalies();
}

function packetTypeClass(name){
  if(name==='TEXT_MESSAGE_APP') return 'type-text';
  if(name==='POSITION_APP') return 'type-position';
  if(name==='NODEINFO_APP') return 'type-nodeinfo';
  if(name==='TELEMETRY_APP') return 'type-telemetry';
  if(name==='TRACEROUTE_APP') return 'type-traceroute';
  if(name==='ROUTING_APP') return 'type-routing';
  if(name==='NEIGHBORINFO_APP') return 'type-neighbor';
  return '';
}
function packetTypeLabel(name){ return String(name||'UNKNOWN').replace(/_APP$/,'').replaceAll('_',' '); }
function packetNode(p,prefix){ return p[`${prefix}_node_longName`] || p[`${prefix}_node_id`] || (p[`${prefix}_node`]!==null && p[`${prefix}_node`]!==undefined ? String(p[`${prefix}_node`]) : '—'); }
function packetHops(p){ const hs=Number(p.hop_start), hl=Number(p.hop_limit); return Number.isFinite(hs)&&Number.isFinite(hl) ? hs-hl : null; }
function packetTime(p){ let t=Number(p.timestamp||0); if(t>0&&t<10000000000)t*=1000; return t; }
function fmtTime(ms){ return ms?new Date(ms).toLocaleTimeString('pt-BR',{hour12:false}):'—'; }
function fmtNum(v,d=1){ return v===null||v===undefined||v===''?'—':Number(v).toFixed(d); }
function trafficKey(p){ return `${p.id ?? ''}:${p.packet_id ?? ''}:${p.timestamp ?? ''}:${p.from_node ?? ''}:${p.to_node ?? ''}:${p.portnum ?? ''}:${p.direction ?? ''}`; }
function packetNodeNum(p,prefix){
  const v=Number(p?.[`${prefix}_node`]);
  return Number.isFinite(v) ? (v >>> 0) : null;
}
function isDirectedNodeInfo(p){
  if(!p || p.portnum_name!=='NODEINFO_APP') return false;
  const a=packetNodeNum(p,'from'), b=packetNodeNum(p,'to');
  return a!==null && b!==null && a!==b && !INVALID_NODES.has(a) && !INVALID_NODES.has(b);
}
function isConfirmedNodeInfoRequest(p){
  if(!isDirectedNodeInfo(p)) return false;
  const preview=String(p.payload_preview||'').toLowerCase();
  if(preview.includes('nodeinfo request') || preview.includes('node info request')) return true;
  // Na v4.16.1, NodeInfo TX originado pelo próprio MeshMonitor é registrado por logOutgoingPacket.
  return String(p.direction||'').toLowerCase()==='tx';
}
function topologyPoint(nodeNum){
  const n=(topology?.nodes||[]).find(x=>Number(x.nodeNum)===Number(nodeNum));
  if(!n || n.latitude===null || n.longitude===null || !Number.isFinite(Number(n.latitude)) || !Number.isFinite(Number(n.longitude))) return null;
  return {nodeNum:Number(nodeNum),nodeId:n.nodeId,name:n.name||n.nodeId,lat:Number(n.latitude),lon:Number(n.longitude)};
}
function sameEndpoints(path,a,b){
  if(!Array.isArray(path) || path.length<2) return false;
  return Number(path[0].nodeNum)===Number(a) && Number(path[path.length-1].nodeNum)===Number(b);
}
function bestObservedTracePath(traces,a,b,eventTs){
  let best=null;
  for(const t of traces||[]){
    const ts=Number(t.timestampMs||0); if(!ts) continue;
    const delta=Math.abs(ts-eventTs); if(delta>NODEINFO_TRACE_WINDOW_MS) continue;
    for(const [leg,path] of [['forward',t.forwardPath],['return',t.returnPath]]){
      if(!sameEndpoints(path,a,b)) continue;
      if(!best || delta<best.delta) best={path,trace:t,leg,delta};
    }
  }
  return best;
}
async function fetchObservedTracePath(a,b,eventTs){
  let best=bestObservedTracePath(topology?.traces||[],a,b,eventTs);
  try{
    const r=await fetch('/api/live-traceroutes?limit=200',{cache:'no-store'});
    if(r.ok){
      const body=await r.json();
      const live=(body.data||[]).map(normalizeLiveTrace).filter(Boolean);
      const cand=bestObservedTracePath(live,a,b,eventTs);
      if(cand && (!best || cand.delta<best.delta)) best=cand;
    }
  }catch{}
  return best;
}
function flowToast(html,known=false){
  const el=document.getElementById('flowToast');
  el.className=known?'flowKnown':'flowUnknown'; el.innerHTML=html; el.style.display='block';
  if(flowToastTimer) clearTimeout(flowToastTimer);
  flowToastTimer=setTimeout(()=>{el.style.display='none';},12000);
}
function clearFlowLater(generation,ms=45000){
  setTimeout(()=>{ if(generation===flowGeneration) flowLayer.clearLayers(); },ms);
}
function drawLogicalNodeInfoLine(p,generation){
  const a=topologyPoint(packetNodeNum(p,'from')), b=topologyPoint(packetNodeNum(p,'to'));
  if(!a || !b) return null;
  const line=L.polyline([[a.lat,a.lon],[b.lat,b.lon]],{color:'#ffb347',weight:3,opacity:.86,dashArray:'7 8',interactive:true}).addTo(flowLayer);
  line.bindTooltip(`NodeInfo ${a.name} → ${b.name} · caminho intermediário ainda não observado`);
  if(document.getElementById('viewMap').classList.contains('active')) map.fitBounds(line.getBounds().pad(.18),{maxZoom:13});
  return {a,b,line};
}
function animateFlowPath(points,generation,color='#a970ff'){
  return new Promise(resolve=>{
    if(!points||points.length<2){resolve(false);return;}
    const latlngs=points.map(p=>L.latLng(p.lat,p.lon));
    const screen=latlngs.map(ll=>map.latLngToContainerPoint(ll));
    const lengths=[];let total=0;
    for(let i=0;i<screen.length-1;i++){const d=screen[i].distanceTo(screen[i+1]);lengths.push(d);total+=d;}
    if(total<1){resolve(true);return;}
    const speed=Math.max(20,Number(document.getElementById('animSpeed').value||150));
    const pulse=L.circleMarker(latlngs[0],{radius:7,color:'#fff',weight:2,fillColor:color,fillOpacity:1,interactive:false}).addTo(flowLayer);
    const start=performance.now();
    function frame(now){
      if(generation!==flowGeneration){try{flowLayer.removeLayer(pulse)}catch{} resolve(false);return;}
      const travelled=((now-start)/1000)*speed;
      if(travelled>=total){pulse.setLatLng(latlngs[latlngs.length-1]);setTimeout(()=>{try{flowLayer.removeLayer(pulse)}catch{}},350);resolve(true);return;}
      let rem=travelled,seg=0;while(seg<lengths.length-1&&rem>lengths[seg]){rem-=lengths[seg];seg++;}
      const ratio=lengths[seg]?Math.max(0,Math.min(1,rem/lengths[seg])):1;
      pulse.setLatLng(latLngAt(points,seg,ratio));requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  });
}
async function showNodeInfoFlow(p,opts={}){
  if(!document.getElementById('nodeInfoFlowEnabled').checked || !isDirectedNodeInfo(p)) return;
  const aNum=packetNodeNum(p,'from'), bNum=packetNodeNum(p,'to'), eventTs=packetTime(p);
  const from=packetNode(p,'from'), to=packetNode(p,'to');
  const generation=++flowGeneration; flowLayer.clearLayers();
  const logical=drawLogicalNodeInfoLine(p,generation);
  if(!logical){
    flowToast(`<b>NodeInfo: ${esc(from)} → ${esc(to)}</b><div class="flowNote">Sem coordenadas suficientes para desenhar o fluxo no mapa.</div>`);
    return;
  }
  flowToast(`<b>NodeInfo: ${esc(from)} → ${esc(to)}</b><div class="flowNote">Linha lógica exibida; procurando um traceroute próximo no tempo para não inventar hops.</div>`);
  const deadline=Date.now()+(opts.wait===false?0:NODEINFO_ROUTE_WAIT_MS);
  let evidence=null;
  do{
    evidence=await fetchObservedTracePath(aNum,bNum,eventTs);
    if(evidence) break;
    if(Date.now()>=deadline) break;
    await new Promise(r=>setTimeout(r,5000));
  }while(generation===flowGeneration);
  if(generation!==flowGeneration) return;
  if(!evidence){
    flowToast(`<b>NodeInfo: ${esc(from)} → ${esc(to)}</b><div class="flowNote">O pacote comum não carrega a cadeia completa de relays. A linha tracejada é apenas origem/destino; nenhum hop foi inventado.</div>`);
    clearFlowLater(generation,30000); return;
  }
  flowLayer.clearLayers();
  const latlngs=evidence.path.map(x=>[x.lat,x.lon]);
  const line=L.polyline(latlngs,{color:'#a970ff',weight:5,opacity:.88,interactive:true}).addTo(flowLayer);
  const deltaS=Math.round(evidence.delta/1000);
  line.bindTooltip(`Rota observada por traceroute próximo (${deltaS}s) · não prova que o NodeInfo usou exatamente os mesmos relays`);
  evidence.path.forEach((pt,i)=>L.circleMarker([pt.lat,pt.lon],{radius:i===0||i===evidence.path.length-1?6:4,color:'#d8c8ff',fillColor:'#a970ff',fillOpacity:.85,weight:1,interactive:false}).addTo(flowLayer));
  if(document.getElementById('viewMap').classList.contains('active')) map.fitBounds(line.getBounds().pad(.18),{maxZoom:13});
  flowToast(`<b>NodeInfo: ${esc(from)} → ${esc(to)}</b><div class="flowNote">Animando pela rota observada em traceroute entre os mesmos nós, ${deltaS}s distante deste evento. É evidência de rota, não o caminho codificado no pacote NodeInfo.</div>`,true);
  await animateFlowPath(evidence.path,generation,'#a970ff');
  clearFlowLater(generation,45000);
}
function handleNodeInfoPacket(p){
  if(!isDirectedNodeInfo(p) || !document.getElementById('nodeInfoFlowEnabled').checked) return;
  const key=trafficKey(p); if(nodeInfoTriggered.has(key)) return;
  const a=packetNodeNum(p,'from'), b=packetNodeNum(p,'to'), now=packetTime(p)||Date.now();
  const pair=`${a}:${b}`, reverse=`${b}:${a}`;
  // Pedido confirmado: TX do MeshMonitor ou preview explícito.
  if(isConfirmedNodeInfoRequest(p)){
    nodeInfoTriggered.add(key); showNodeInfoFlow(p); return;
  }
  // Em RX o Packet Monitor v4.16.1 não persiste want_response. Só promovemos o
  // primeiro frame a "pedido provável" quando observamos a resposta reversa.
  const prev=nodeInfoRecent.get(reverse);
  if(prev && Math.abs(now-packetTime(prev))<=NODEINFO_PAIR_WINDOW_MS){
    const prevKey=trafficKey(prev);
    if(!nodeInfoTriggered.has(prevKey)){
      nodeInfoTriggered.add(prevKey);
      showNodeInfoFlow(prev,{wait:false});
    }
  }
  nodeInfoRecent.set(pair,p);
  // limpeza simples
  for(const [k,v] of [...nodeInfoRecent.entries()]) if(now-packetTime(v)>NODEINFO_PAIR_WINDOW_MS) nodeInfoRecent.delete(k);
}
function filteredTraffic(){
  const dir=document.getElementById('trafficDirection').value;
  const type=document.getElementById('trafficType').value;
  const q=document.getElementById('trafficSearch').value.trim().toLowerCase();
  return trafficPackets.filter(p=>{
    if(dir!=='all' && String(p.direction||'').toLowerCase()!==dir)return false;
    if(type!=='all' && p.portnum_name!==type)return false;
    if(q){ const hay=[packetNode(p,'from'),packetNode(p,'to'),p.from_node_id,p.to_node_id,p.portnum_name,p.payload_preview].join(' ').toLowerCase(); if(!hay.includes(q))return false; }
    return true;
  });
}
function renderTraffic(){
  const rows=filteredTraffic();
  const now=Date.now();
  const rx=trafficPackets.filter(p=>String(p.direction||'').toLowerCase()==='rx').length;
  const tx=trafficPackets.filter(p=>String(p.direction||'').toLowerCase()==='tx').length;
  const lastMin=trafficPackets.filter(p=>now-packetTime(p)<=60000).length;
  document.getElementById('trafficStats').innerHTML=
    `<span class="metric"><b>${trafficTotal}</b> armazenados no MM</span>`+
    `<span class="metric"><b>${trafficPackets.length}</b> carregados</span>`+
    `<span class="metric"><b>${rx}</b> RX</span>`+
    `<span class="metric"><b>${tx}</b> TX</span>`+
    `<span class="metric"><b>${lastMin}</b> último minuto</span>`+
    `<span class="metric"><b>${rows.length}</b> no filtro</span>`;
  const body=document.getElementById('trafficRows');
  body.innerHTML=rows.length?rows.slice(0,1000).map(p=>{
    const id=trafficKey(p); const dir=String(p.direction||'?').toLowerCase(); const hops=packetHops(p);
    return `<tr data-packet="${esc(id)}" class="${selectedPacketId===id?'selected':''}">`+
      `<td>${fmtTime(packetTime(p))}</td><td><span class="badge ${dir==='rx'?'rx':'tx'}">${esc(dir.toUpperCase())}</span></td>`+
      `<td title="${esc(p.from_node_id||'')}">${esc(packetNode(p,'from'))}</td><td title="${esc(p.to_node_id||'')}">${esc(packetNode(p,'to'))}</td>`+
      `<td><span class="badge typeBadge ${packetTypeClass(p.portnum_name)}" title="Clique para ver o payload formatado">${esc(packetTypeLabel(p.portnum_name))}</span></td>`+
      `<td>${p.snr==null?'—':fmtNum(p.snr,2)}</td><td>${p.rssi==null?'—':esc(p.rssi)}</td><td>${hops==null?'—':esc(hops)}</td><td>${p.channel==null?'—':esc(p.channel)}</td></tr>`;
  }).join(''):'<tr><td colspan="9">Nenhum pacote corresponde ao filtro.</td></tr>';
  body.querySelectorAll('tr[data-packet]').forEach(tr=>tr.addEventListener('click',()=>selectPacket(tr.dataset.packet)));
}
function isBroadcastPacket(p){
  const to=packetNodeNum(p,'to');
  const id=String(p?.to_node_id||'').toLowerCase();
  return to===0xffffffff || id==='!ffffffff' || id==='broadcast';
}
function parsedMetadata(p){
  if(!p?.metadata) return {};
  if(typeof p.metadata==='object') return p.metadata;
  try{ const x=JSON.parse(p.metadata); return x&&typeof x==='object'?x:{}; }catch{return {};}
}
const FRIENDLY_LABELS={
  latitude:'Latitude',longitude:'Longitude',latitudeI:'Latitude',longitudeI:'Longitude',altitude:'Altitude',altitudeHae:'Altitude HAE',
  time:'Horário',timestamp:'Horário',batteryLevel:'Bateria',voltage:'Tensão',channelUtilization:'Utilização do canal',airUtilTx:'Air Util TX',uptimeSeconds:'Uptime',
  temperature:'Temperatura',relativeHumidity:'Umidade',barometricPressure:'Pressão',gasResistance:'Resistência do gás',current:'Corrente',lux:'Luminosidade',
  longName:'Nome',shortName:'Nome curto',id:'ID',macaddr:'MAC',hwModel:'Hardware',role:'Role',publicKey:'Chave pública',isLicensed:'Licenciado',
  nodeId:'Nó',snr:'SNR',lastRxTime:'Última recepção',neighbors:'Vizinhos',route:'Rota',routeBack:'Rota de volta',routingError:'Erro de roteamento',errorReason:'Motivo',
  requestId:'ID da solicitação',replyId:'ID da resposta',packetId:'ID do pacote',telemetryType:'Tipo de telemetria',wantResponse:'Solicita resposta',wantAck:'Solicita ACK',destination:'Destino',direction:'Direção',
  channel:'Canal',portnum:'PortNum',portnumName:'Tipo de pacote',relayNode:'Relay',transportMechanism:'Transporte',rxTime:'Recebido em',viaMqtt:'Via MQTT',priority:'Prioridade',
  deviceMetrics:'Métricas do dispositivo',environmentMetrics:'Métricas ambientais',localStats:'Estatísticas locais',powerMetrics:'Métricas de energia',airQualityMetrics:'Qualidade do ar'
};
function friendlyKey(k){
  if(FRIENDLY_LABELS[k]) return FRIENDLY_LABELS[k];
  return String(k).replace(/([a-z0-9])([A-Z])/g,'$1 $2').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());
}
function friendlyScalar(k,v){
  if(v===null||v===undefined||v==='') return '—';
  if(typeof v==='boolean') return v?'Sim':'Não';
  if(typeof v==='number'){
    if(/latitudeI|longitudeI/.test(k) && Math.abs(v)>180) return (v/1e7).toFixed(7)+'°';
    if(/latitude|longitude/.test(k) && Math.abs(v)<=180) return Number(v).toFixed(7)+'°';
    if(/batteryLevel/i.test(k)) return `${v}%`;
    if(/voltage/i.test(k)) return `${Number(v).toFixed(3)} V`;
    if(/temperature/i.test(k)) return `${Number(v).toFixed(1)} °C`;
    if(/humidity/i.test(k)) return `${Number(v).toFixed(1)}%`;
    if(/pressure/i.test(k)) return `${Number(v).toFixed(1)} hPa`;
    if(/snr/i.test(k)) return `${Number(v).toFixed(2)} dB`;
    if(/rssi/i.test(k)) return `${v} dBm`;
    if(/uptimeSeconds/i.test(k)){
      const d=Math.floor(v/86400),h=Math.floor((v%86400)/3600),m=Math.floor((v%3600)/60); return [d?`${d}d`:null,h?`${h}h`:null,`${m}min`].filter(Boolean).join(' ');
    }
    if((/time|timestamp|lastRxTime/i.test(k)) && v>1000000000){const ms=v<10000000000?v*1000:v;return new Date(ms).toLocaleString('pt-BR');}
    return String(v);
  }
  return String(v);
}
function flattenFriendly(obj,prefix='',out=[]){
  if(obj===null||obj===undefined) return out;
  if(Array.isArray(obj)){
    if(obj.every(x=>x===null||['string','number','boolean'].includes(typeof x))){ out.push([prefix||'Valores',obj.map((x,i)=>friendlyScalar(prefix,x)).join(' → ')]); }
    else obj.forEach((x,i)=>flattenFriendly(x,`${prefix||'Item'} ${i+1}`,out));
    return out;
  }
  if(typeof obj!=='object'){out.push([prefix||'Valor',friendlyScalar(prefix,obj)]);return out;}
  for(const [k,v] of Object.entries(obj)){
    const label=prefix?`${prefix} · ${friendlyKey(k)}`:friendlyKey(k);
    if(v!==null && typeof v==='object') flattenFriendly(v,label,out); else out.push([label,friendlyScalar(k,v)]);
  }
  return out;
}
function friendlyPayloadHtml(p){
  const meta=parsedMetadata(p);
  const decoded=meta.decoded_payload;
  const preview=String(p.payload_preview||'').trim();
  const broadcast=isBroadcastPacket(p);
  const directHidden=p.portnum_name==='TEXT_MESSAGE_APP' && !broadcast && preview==='[conteúdo oculto]';
  if(directHidden) return '<div class="payloadBox">Conteúdo de mensagem direta ocultado por padrão.</div>';
  let rows=[];
  if(decoded!==undefined && decoded!==null) rows=flattenFriendly(decoded);
  if(p.portnum_name==='TEXT_MESSAGE_APP' && preview && preview!=='[conteúdo oculto]'){
    return `<div class="payloadBox"><b>Mensagem${broadcast?' broadcast':''}:</b><br>${esc(preview)}</div>`;
  }
  if(!rows.length && preview && preview!=='[conteúdo oculto]') return `<div class="payloadBox">${esc(preview)}</div>`;
  if(!rows.length) return '<div class="payloadBox">Nenhum payload decodificado disponível.</div>';
  const html=rows.slice(0,120).map(([k,v])=>`<span class="k">${esc(k)}</span><span class="v">${esc(v)}</span>`).join('');
  return `<div class="payloadBox"><div class="payloadRows">${html}</div></div>`;
}
function technicalNodeValue(v){
  if(v===null||v===undefined||v==='') return '—';
  const n=Number(v);
  if(!Number.isFinite(n)) return String(v);
  const u=n>>>0;
  if(u===0xffffffff) return 'Broadcast (!ffffffff)';
  const node=(topology?.nodes||[]).find(x=>(Number(x.nodeNum)>>>0)===u);
  const id=`!${u.toString(16).padStart(8,'0')}`;
  return node ? `${node.name||node.shortName||node.nodeId||id} (${node.nodeId||id})` : id;
}
function friendlyTechnicalScalar(k,v){
  if(k==='destination' || k==='source' || k==='fromNode' || k==='toNode' || k==='nodeNum') return technicalNodeValue(v);
  if(k==='direction') return String(v||'—').toUpperCase();
  if(k==='telemetryType'){
    const m={device:'Métricas do dispositivo',environment:'Métricas ambientais',localStats:'Estatísticas locais',power:'Métricas de energia',airQuality:'Qualidade do ar'};
    return m[String(v)] || friendlyScalar(k,v);
  }
  if(k==='viaMqtt') return v?'Sim':'Não';
  return friendlyScalar(k,v);
}
function flattenFriendlyTechnical(obj,prefix='',out=[]){
  if(obj===null||obj===undefined) return out;
  if(Array.isArray(obj)){
    if(obj.every(x=>x===null||['string','number','boolean'].includes(typeof x))) out.push([prefix||'Valores',obj.map(x=>friendlyTechnicalScalar(prefix,x)).join(' → ')]);
    else obj.forEach((x,i)=>flattenFriendlyTechnical(x,`${prefix||'Item'} ${i+1}`,out));
    return out;
  }
  if(typeof obj!=='object'){out.push([prefix||'Valor',friendlyTechnicalScalar(prefix,obj)]);return out;}
  for(const [k,v] of Object.entries(obj)){
    if(k==='decoded_payload') continue; // já aparece em Payload, em formato amigável
    const label=prefix?`${prefix} · ${friendlyKey(k)}`:friendlyKey(k);
    if(v!==null && typeof v==='object') flattenFriendlyTechnical(v,label,out); else out.push([label,friendlyTechnicalScalar(k,v)]);
  }
  return out;
}
function technicalDetailsHtml(p){
  const meta=parsedMetadata(p);
  const rows=flattenFriendlyTechnical(meta);
  if(!rows.length) return '<details class="techDetails"><summary>Dados técnicos</summary><div class="payloadBox">Nenhum dado técnico adicional disponível.</div></details>';
  const html=rows.slice(0,160).map(([k,v])=>`<span class="k">${esc(k)}</span><span class="v">${esc(v)}</span>`).join('');
  const raw=`<details class="rawJson"><summary>Ver JSON bruto</summary><pre>${esc(JSON.stringify(meta,null,2))}</pre></details>`;
  return `<details class="techDetails"><summary>Dados técnicos</summary><div class="payloadBox"><div class="payloadRows">${html}</div>${raw}</div></details>`;
}
function selectPacket(key){
  selectedPacketId=key; const p=trafficPackets.find(x=>trafficKey(x)===key); if(!p)return;
  const hops=packetHops(p); const broadcast=isBroadcastPacket(p);
  document.getElementById('packetDetail').innerHTML=`<div class="detailTitle">${esc(packetTypeLabel(p.portnum_name))}${broadcast?'<span class="broadcastTag">BROADCAST</span>':''}</div>`+
    `<div class="detailGrid"><b>Hora</b><span>${esc(new Date(packetTime(p)).toLocaleString('pt-BR'))}</span>`+
    `<b>Direção</b><span>${esc(String(p.direction||'?').toUpperCase())}</span>`+
    `<b>Origem</b><span>${esc(packetNode(p,'from'))}<br>${esc(p.from_node_id||'')}</span>`+
    `<b>Destino</b><span>${esc(packetNode(p,'to'))}<br>${esc(p.to_node_id||'')}</span>`+
    `<b>Canal</b><span>${p.channel==null?'—':esc(p.channel)}</span>`+
    `<b>SNR</b><span>${p.snr==null?'—':fmtNum(p.snr,2)+' dB'}</span>`+
    `<b>RSSI</b><span>${p.rssi==null?'—':esc(p.rssi)+' dBm'}</span>`+
    `<b>Hops</b><span>${hops==null?'—':esc(hops)}</span>`+
    `<b>Relay</b><span>${p.relay_node==null?'—':esc(p.relay_node)}</span>`+
    `<b>Criptografado</b><span>${p.encrypted?'sim':'não'}</span>`+
    `<b>Payload</b><span>${friendlyPayloadHtml(p)}${technicalDetailsHtml(p)}</span>`+
    (isDirectedNodeInfo(p)?`<b>Mapa</b><span><button id="showNodeInfoFlowBtn">Mostrar fluxo</button></span>`:'')+`</div>`;
  const flowBtn=document.getElementById('showNodeInfoFlowBtn'); if(flowBtn) flowBtn.addEventListener('click',()=>{setView('map');showNodeInfoFlow(p);});
  renderTraffic();
}
function ensureAudio(){ if(!audioCtx){ const C=window.AudioContext||window.webkitAudioContext; if(C) audioCtx=new C(); } if(audioCtx?.state==='suspended') audioCtx.resume(); return audioCtx; }
function toneOsc(ctx,type,f0,f1,start,duration,amp){
  const osc=ctx.createOscillator(),gain=ctx.createGain(); osc.type=type; osc.frequency.setValueAtTime(f0,start); if(f1&&f1!==f0) osc.frequency.exponentialRampToValueAtTime(f1,start+duration*.65);
  gain.gain.setValueAtTime(0.0001,start); gain.gain.exponentialRampToValueAtTime(Math.max(0.001,amp),start+0.01); gain.gain.exponentialRampToValueAtTime(0.0001,start+duration);
  osc.connect(gain);gain.connect(ctx.destination);osc.start(start);osc.stop(start+duration+.02);
}
function playNotification(force=false){
  if(!force && !document.getElementById('soundEnabled').checked)return;
  const now=performance.now(); if(!force && now-lastSoundAt<350)return; lastSoundAt=now;
  const ctx=ensureAudio();if(!ctx)return; const vol=Math.max(0,Math.min(1,Number(document.getElementById('soundVolume').value||35)/100)); const t=ctx.currentTime+.01;
  const tone=document.getElementById('soundTone').value||'plim'; const a=Math.max(.001,vol*.16);
  if(tone==='chime'){toneOsc(ctx,'sine',659,659,t,.28,a*.75);toneOsc(ctx,'sine',988,988,t+.07,.32,a*.55);toneOsc(ctx,'sine',1319,1319,t+.14,.36,a*.35);}
  else if(tone==='click'){toneOsc(ctx,'square',1500,900,t,.055,a*.35);}
  else if(tone==='double'){toneOsc(ctx,'sine',880,1180,t,.12,a*.85);toneOsc(ctx,'sine',1047,1397,t+.15,.14,a*.75);}
  else if(tone==='soft'){toneOsc(ctx,'sine',523,784,t,.24,a*.55);}
  else {toneOsc(ctx,'sine',880,1320,t,.17,a);}
}
function journeyKey(p){
  const meta=parsedMetadata(p);
  const pid=(p.packet_id!==null&&p.packet_id!==undefined&&Number(p.packet_id)!==0)?p.packet_id:(meta.id!==null&&meta.id!==undefined&&Number(meta.id)!==0?meta.id:null);
  if(pid!==null) return `pid:${pid}:${packetNodeNum(p,'from')}:${p.portnum||p.portnum_name||''}`;
  // TXs gerados internamente nem sempre carregam packet_id no log. Neste caso,
  // cada linha TX é tratada como o início de uma nova viagem.
  if(String(p.direction||'').toLowerCase()==='tx') return `tx:${trafficKey(p)}`;
  // Fallback conservador para RX sem id: agrega cópias próximas do mesmo quadro.
  return `rx:${packetNodeNum(p,'from')}:${packetNodeNum(p,'to')}:${p.portnum||p.portnum_name||''}:${Math.floor(packetTime(p)/3000)}`;
}
function nodePointForActivity(nodeNum,p=null){
  const t=topologyPoint(nodeNum); if(t) return t;
  // Para POSITION_APP, a própria posição decodificada pode servir de fallback
  // para o nó de origem, sem fabricar coordenadas para outros nós.
  if(p && Number(nodeNum)===packetNodeNum(p,'from')){
    const meta=parsedMetadata(p), d=meta.decoded_payload;
    if(d && typeof d==='object'){
      let lat=d.latitude ?? d.latitudeI, lon=d.longitude ?? d.longitudeI;
      lat=Number(lat); lon=Number(lon);
      if(Number.isFinite(lat)&&Number.isFinite(lon)){
        if(Math.abs(lat)>90) lat/=1e7; if(Math.abs(lon)>180) lon/=1e7;
        if(Math.abs(lat)<=90&&Math.abs(lon)<=180) return {nodeNum:Number(nodeNum),nodeId:p.from_node_id||'',name:packetNode(p,'from'),lat,lon};
      }
    }
  }
  return null;
}
function resolveRelayNodeNum(relay){
  const rv=Number(relay); if(!Number.isFinite(rv)||rv<=0) return null;
  const nodes=(topology?.nodes||[]).filter(n=>Number.isFinite(Number(n.nodeNum)));
  const exact=nodes.find(n=>(Number(n.nodeNum)>>>0)===(rv>>>0));
  if(exact) return Number(exact.nodeNum)>>>0;
  if(rv<=255){
    const matches=nodes.filter(n=>((Number(n.nodeNum)>>>0)&0xff)===(rv&0xff) && topologyPoint(Number(n.nodeNum)));
    if(matches.length===1) return Number(matches[0].nodeNum)>>>0;
  }
  return null;
}
function activityPulseAtPoint(pt,nodeNum,kind='origin'){
  if(!document.getElementById('activityAnimationEnabled').checked) return;
  if(kind==='relay' && !document.getElementById('activityRelayEnabled').checked) return;
  if(kind!=='relay' && !document.getElementById('activityOriginEnabled').checked) return;
  if(!pt || !Number.isFinite(Number(pt.lat)) || !Number.isFinite(Number(pt.lon))) return;
  const key=`${kind}:${nodeNum}`;
  const old=activityMarkers.get(key); if(old){try{activityLayer.removeLayer(old)}catch{} clearTimeout(old.__taTimer);}
  const symbol=kind==='relay'?'↻':'📡';
  const cls=kind==='relay'?'relay':(kind==='response'?'response':'origin');
  const duration=Math.max(400,Number(document.getElementById('activityDuration').value||1000));
  const icon=L.divIcon({className:'activityLeafletIcon',iconSize:[46,46],iconAnchor:[23,23],html:`<div class="activityPulse ${cls}" style="--taDur:${duration}ms"><div class="activityCore">${symbol}</div></div>`});
  const marker=L.marker([Number(pt.lat),Number(pt.lon)],{icon,interactive:false,zIndexOffset:1200}).addTo(activityLayer);
  marker.__taTimer=setTimeout(()=>{try{activityLayer.removeLayer(marker)}catch{} if(activityMarkers.get(key)===marker)activityMarkers.delete(key);},duration);
  activityMarkers.set(key,marker);
}
function activityPulse(nodeNum,kind='origin',p=null){
  const pt=nodePointForActivity(nodeNum,p); if(!pt) return;
  activityPulseAtPoint(pt,nodeNum,kind);
}
function animatePacketActivity(p,isNewJourney){
  if(!document.getElementById('activityAnimationEnabled').checked) return;
  const from=packetNodeNum(p,'from');
  const relay=resolveRelayNodeNum(p.relay_node);
  const dir=String(p.direction||'').toLowerCase();
  // Toda atividade observada realça a origem do pacote. Assim TXs, respostas RX
  // e novas cópias observadas podem mostrar imediatamente qual nó está ativo.
  if(from!==null) activityPulse(from,dir==='rx'?'response':'origin',p);
  // O relay_node é apenas o último relay observado. Só anima quando o byte
  // resolve de forma não ambígua para um nó posicionado.
  if(relay!==null && relay!==from) activityPulse(relay,'relay',p);
}
function mergeTraffic(rows, notify){
  const existing=new Set(trafficPackets.map(trafficKey)); const fresh=[];
  for(const p of rows||[]){
    const k=trafficKey(p); if(existing.has(k))continue; existing.add(k); trafficPackets.push(p); fresh.push(p);
    const t=packetTime(p); if(t>trafficLastTs)trafficLastTs=t;
    // O carregamento inicial também semeia as viagens conhecidas para não tocar som retroativo.
    if(!notify) journeySeen.add(journeyKey(p));
  }
  trafficPackets.sort((a,b)=>packetTime(b)-packetTime(a)); if(trafficPackets.length>1500)trafficPackets=trafficPackets.slice(0,1500);
  if(notify) fresh.slice().sort((a,b)=>packetTime(a)-packetTime(b)).forEach(p=>{
    const jk=journeyKey(p); const newJourney=!journeySeen.has(jk);
    if(newJourney){journeySeen.add(jk);playNotification(false);}
    animatePacketActivity(p,newJourney);
    handleNodeInfoPacket(p);
  });
  if(journeySeen.size>6000) journeySeen=new Set([...journeySeen].slice(-3000));
  renderTraffic();
}
async function fetchTraffic(url){ const r=await fetch(url,{cache:'no-store'}); if(!r.ok)throw new Error(`HTTP ${r.status}`); return r.json(); }
function downloadTrafficDump(){
  const btn=document.getElementById('trafficDump');
  if(!btn)return;
  const old=btn.textContent;
  btn.disabled=true; btn.textContent='Preparando dump…';
  const a=document.createElement('a');
  a.href='/api/archive/dump';
  a.download='';
  a.style.display='none';
  document.body.appendChild(a);
  a.click();
  setTimeout(()=>{ try{a.remove();}catch{} btn.disabled=false; btn.textContent=old; },2500);
}
async function loadTrafficInitial(){
  try{ const body=await fetchTraffic('/api/packets?limit=250'); trafficTotal=Number(body.total||0); trafficPackets=[]; trafficLastTs=0; journeySeen=new Set(); mergeTraffic(body.data||[],false); trafficInitialized=true; document.getElementById('trafficLive').textContent='● AO VIVO'; startTrafficPolling(); }
  catch(e){ document.getElementById('trafficLive').textContent=`erro: ${e}`; }
}
async function pollTraffic(){
  if(trafficPaused)return;
  try{ const since=trafficLastTs?`&since=${trafficLastTs+1}`:''; const body=await fetchTraffic(`/api/packets?limit=250${since}`); trafficTotal=Math.max(trafficTotal,Number(body.total||0)); mergeTraffic(body.data||[],trafficInitialized); trafficInitialized=true; document.getElementById('trafficLive').textContent='● AO VIVO'; }
  catch(e){ document.getElementById('trafficLive').textContent=`erro ${e}`; }
}
function startTrafficPolling(){ if(trafficTimer)clearInterval(trafficTimer); trafficTimer=setInterval(pollTraffic,2000); }
function toggleTrafficPause(){ trafficPaused=!trafficPaused; document.getElementById('trafficPause').textContent=trafficPaused?'Retomar':'Pausar'; document.getElementById('trafficLive').textContent=trafficPaused?'● PAUSADO':'● AO VIVO'; if(!trafficPaused)pollTraffic(); }


let healthLoadedAt=0, anomalyLoadedAt=0;
function fmtNum(v,dec=0){ const n=Number(v); return Number.isFinite(n)?n.toLocaleString('pt-BR',{minimumFractionDigits:dec,maximumFractionDigits:dec}):'—'; }
function healthCard(value,label,sub=''){return `<div class="dashCard"><div class="value">${esc(value)}</div><div class="label">${esc(label)}</div>${sub?`<div class="sub">${esc(sub)}</div>`:''}</div>`;}
async function loadNetworkHealth(force=false){
  if(!force && Date.now()-healthLoadedAt<30000)return;
  const cards=document.getElementById('healthCards');
  cards.innerHTML=healthCard('…','Calculando indicadores');
  try{
    const r=await fetch('/api/network-health',{cache:'no-store'}); if(!r.ok)throw new Error(`HTTP ${r.status}`); const b=await r.json();
    healthLoadedAt=Date.now(); document.getElementById('healthUpdated').textContent=`atualizado ${new Date(b.generatedAtMs).toLocaleTimeString('pt-BR')}`;
    cards.innerHTML=[
      healthCard(b.nodes.active2h,'Nós ativos - 2 h',`${b.nodes.total} nós conhecidos`),
      healthCard(b.nodes.active24h,'Nós ativos - 24 h',`${b.nodes.silent24h} sem tráfego > 24 h`),
      healthCard(b.traffic.packets24h,'Pacotes - 24 h',`${b.traffic.rx24h} RX · ${b.traffic.tx24h} TX`),
      healthCard(b.links.observed,'Enlaces observados',`${b.links.recent24h} vistos nas últimas 24 h`),
      healthCard(b.traceroutes.total,'Traceroutes','histórico carregado'),
      healthCard(`${fmtNum(b.traceroutes.roundTripRate,1)}%`,'Com ida e volta',`${b.traceroutes.roundTrip} completos nos 2 sentidos`),
      healthCard(fmtNum(b.traceroutes.medianHops,1),'Mediana de hops','por perna observada'),
      healthCard(b.nodes.noTraffic,'Sem registro','nós sem timestamp confiável')
    ].join('');
    const daily=b.daily||[], max=Math.max(1,...daily.map(x=>Number(x.packets||0)));
    document.getElementById('healthDaily').innerHTML=daily.map(x=>{const pct=Math.max(2,Math.round(90*Number(x.packets||0)/max));return `<div class="miniBarWrap"><div class="miniBarValue" style="--h:${pct}px">${fmtNum(x.packets)}</div><div class="miniBar" style="height:${pct}px"></div><div class="miniBarLabel">${esc(x.label)}</div></div>`}).join('')||'<div class="emptyPanel">Sem dados no período.</div>';
    document.getElementById('healthRoutes').innerHTML=`<div class="dashGrid">${healthCard(b.traceroutes.forward,'Idas observadas')}${healthCard(b.traceroutes.return,'Voltas observadas')}${healthCard(b.traceroutes.incomplete,'Traceroutes incompletos')}${healthCard(fmtNum(b.traceroutes.avgHops,1),'Média de hops')}</div>`;
    document.getElementById('healthChatRows').innerHTML=(b.chatInteractions||[]).map(n=>`<tr><td><b>${esc(n.name||n.nodeId||'Nó desconhecido')}</b>${n.nodeId?`<br><span class="settingDesc">${esc(n.nodeId)}</span>`:''}</td><td><b>${fmtNum(n.interactions)}</b></td></tr>`).join('')||'<tr><td colspan="2" class="emptyPanel">Nenhuma interação de chat registrada no canal primário.</td></tr>';
    document.getElementById('healthSilentRows').innerHTML=(b.attentionNodes||[]).map(n=>`<tr><td><b>${esc(n.name||n.nodeId)}</b><br><span class="settingDesc">${esc(n.nodeId||'')}</span></td><td>${n.lastSeen?new Date(n.lastSeen).toLocaleString('pt-BR'):'—'}</td><td>${esc(n.lastSeen?humanAge(n.lastSeen):'sem registro')}</td><td>${fmtNum(n.packets7d)}</td><td>${n.avgSnr7d==null?'—':`${fmtNum(n.avgSnr7d,1)} dB`}</td></tr>`).join('')||'<tr><td colspan="5" class="emptyPanel">Nenhum nó requer atenção pelo critério atual.</td></tr>';
  }catch(e){cards.innerHTML=healthCard('Erro','Não foi possível calcular',String(e));}
}
function sevLabel(s){return s==='critical'?'Crítica':s==='warning'?'Atenção':s==='info'?'Informativa':'OK';}
async function loadAnomalies(force=false){
  if(!force && Date.now()-anomalyLoadedAt<30000)return;
  try{
    const r=await fetch('/api/anomalies',{cache:'no-store'}); if(!r.ok)throw new Error(`HTTP ${r.status}`); const b=await r.json(); anomalyLoadedAt=Date.now();
    document.getElementById('anomalyUpdated').textContent=`analisado ${new Date(b.generatedAtMs).toLocaleTimeString('pt-BR')}`;
    document.getElementById('anomalyCards').innerHTML=[healthCard(b.summary.total,'Anomalias'),healthCard(b.summary.critical,'Críticas'),healthCard(b.summary.warning,'Atenção'),healthCard(b.summary.info,'Informativas')].join('');
    document.getElementById('anomalyList').innerHTML=(b.data||[]).map(a=>`<div class="anomalyRow"><div><span class="severity sev-${esc(a.severity)}">${esc(sevLabel(a.severity))}</span></div><div><div class="anomalyTitle">${esc(a.title)}</div><div class="anomalyEvidence">${esc(a.subject||'')}</div></div><div class="anomalyMsg">${esc(a.message)}${a.evidence?`<div class="anomalyEvidence">${esc(a.evidence)}</div>`:''}</div><div class="anomalyTime">${a.timestampMs?esc(humanAge(a.timestampMs)):'—'}</div></div>`).join('')||'<div class="emptyPanel"><span class="severity sev-ok">OK</span> Nenhuma anomalia foi detectada pelos critérios atuais.</div>';
  }catch(e){document.getElementById('anomalyList').innerHTML=`<div class="emptyPanel">Erro ao analisar: ${esc(e)}</div>`;}
}
document.getElementById('healthReload').addEventListener('click',()=>loadNetworkHealth(true));
document.getElementById('anomalyReload').addEventListener('click',()=>loadAnomalies(true));

async function loadNodeTrafficActivity(){
  try{
    const r=await fetch('/api/archive/nodes',{cache:'no-store'});
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    const body=await r.json();
    nodeTrafficLastSeen.clear();
    for(const row of body.data||[]){
      const n=Number(row.nodeNum), ts=Number(row.lastSeen);
      if(Number.isFinite(n)&&Number.isFinite(ts)&&ts>0) nodeTrafficLastSeen.set(n,ts);
    }
  }catch(e){ console.warn('Não foi possível atualizar a atividade dos nós:',e); }
}

async function load(fit=false){
  try{
    const r = await fetch('/api/topology', {cache:'no-store'});
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    topology = await r.json();
    await loadNodeTrafficActivity();
    render();
    map.invalidateSize();
    if(document.getElementById('playMode').value === 'history') updatePlaybackStatusIdle();
    if(fit && lastBounds && lastBounds.isValid()) map.fitBounds(lastBounds.pad(.08));
  }catch(e){
    console.error('Erro ao carregar topologia:', e);
    document.getElementById('summary').innerHTML = `<span class="metric warn">Erro ao carregar topologia: ${esc(e.message||e)}</span>`;
  }
}

for(const id of ['ageHours','minObs','onlyIdentified']) document.getElementById(id).addEventListener('change', () => { historyIndex=0; savePrefs(); render(); });
document.getElementById('showShortNames').addEventListener('change', () => { savePrefs(); render(); });
for(const id of ['showLines','showNodes','showHeatmap']) document.getElementById(id).addEventListener('change', () => { savePrefs(); render(); });
document.getElementById('mapType').addEventListener('change', (ev) => { setBaseMap(ev.target.value); savePrefs(); });
document.getElementById('mapBrightness').addEventListener('input', () => { applyBrightness(); savePrefs(); });
document.getElementById('lineColor').addEventListener('input', () => { savePrefs(); render(); });
document.getElementById('animSpeed').addEventListener('change', savePrefs);
document.getElementById('playMode').addEventListener('change', () => {
  stopAnimation(); stopLivePolling();
  if(document.getElementById('playMode').value === 'live') startLivePolling(); else updatePlaybackStatusIdle();
});
document.getElementById('playTrace').addEventListener('click', () => {
  if(document.getElementById('playMode').value === 'live'){ playbackRunning=true; if(!livePollTimer) startLivePolling(); else processLiveQueue(); }
  else playHistoryLoop();
});
document.getElementById('pauseTrace').addEventListener('click', () => { stopAnimation(); });
document.getElementById('prevTrace').addEventListener('click', () => { if(document.getElementById('playMode').value==='history') playHistoryOnce(historyIndex-1); });
document.getElementById('nextTrace').addEventListener('click', () => { if(document.getElementById('playMode').value==='history') playHistoryOnce(historyIndex+1); });
document.getElementById('reload').addEventListener('click', () => load(false));
document.getElementById('fit').addEventListener('click', () => { if(lastBounds && lastBounds.isValid()) map.fitBounds(lastBounds.pad(.08)); });



// ===== Canal primário / chat =====
let primaryMessages=[];
let messagesInitialized=false;
let messageFetchLimit=250;
let messageNewestSeen=0;
let messageSeenIds=new Set();
const MESSAGE_READ_KEY='trafficAnalyzerPrimaryLastReadV117';
function msgTimeMs(m){return Number(m.receivedAt||m.createdAt||m.timestamp||0)||0;}
function messageKey(m){return String(m.id||`${m.fromNodeId||''}|${m.requestId||''}|${msgTimeMs(m)}|${m.text||''}`);}
function dateKey(ms){const d=new Date(ms);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}
function dayLabel(ms){const d=new Date(ms),now=new Date();const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());const that=new Date(d.getFullYear(),d.getMonth(),d.getDate());const delta=Math.round((today-that)/86400000);if(delta===0)return 'Hoje';if(delta===1)return 'Ontem';return d.toLocaleDateString('pt-BR',{day:'2-digit',month:'long',year:'numeric'});}
function lastReadMs(){return Number(localStorage.getItem(MESSAGE_READ_KEY)||0)||0;}
function markMessagesRead(){if(!primaryMessages.length)return;const newest=Math.max(...primaryMessages.filter(m=>!m.mine).map(msgTimeMs),0);if(newest>lastReadMs())localStorage.setItem(MESSAGE_READ_KEY,String(newest));updateUnreadBadge();renderMessages();}
function updateUnreadBadge(){const lr=lastReadMs();const unread=primaryMessages.filter(m=>!m.mine&&msgTimeMs(m)>lr).length;const nav=document.getElementById('messagesNav'),count=document.getElementById('messagesUnreadCount');count.textContent=String(unread);nav.classList.toggle('unread',unread>0);nav.title=unread?`${unread} mensagem(ns) não lida(s)`:'Sem mensagens não lidas';}
function deliveryVisual(m){const st=String(m.deliveryState||'').toLowerCase();if(m.ackFailed||m.routingErrorReceived||st==='failed')return {icon:'!',cls:'failed',tip:'Falha de entrega/roteamento reportada pelo MeshMonitor'};if(st==='confirmed'||m.ackFromNode)return {icon:'✓✓',cls:'confirmed',tip:'ACK confirmado pelo protocolo; não significa leitura humana'};if(st==='delivered')return {icon:'✓',cls:'',tip:'Transmitida para a malha pelo rádio local'};if(st==='queued'||st==='pending'||!st)return {icon:'◷',cls:'',tip:'Aguardando confirmação de transmissão'};return {icon:'✓',cls:'',tip:`Estado: ${st}`};}
function renderMessages(keepBottom=false){const el=document.getElementById('messageList');if(!primaryMessages.length){el.innerHTML='<div class="emptyPanel">Nenhuma mensagem encontrada no canal primário.</div>';return;}const lr=lastReadMs();let html='',lastDay='';for(const m of primaryMessages){const ms=msgTimeMs(m),dk=dateKey(ms);if(dk!==lastDay){html+=`<div class="msgDay"><span>${esc(dayLabel(ms))}</span></div>`;lastDay=dk;}const dv=deliveryVisual(m);const transport=m.viaMqtt?'MQTT':(m.viaStoreForward?'Store&Forward':'RF');const unread=!m.mine&&ms>lr;html+=`<div class="msgRow ${m.mine?'mine':'theirs'}" data-mid="${esc(m.id||'')}"><div class="msgBubble">${!m.mine?`<div class="msgSender">${esc(m.fromName||m.fromNodeId||'Nó')} ${unread?'<span class="msgNewMark">nova</span>':''}</div>`:''}<div class="msgText">${esc(m.text||'')}</div><div class="msgMeta">${new Date(ms).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}${m.mine?`<span class="msgStatus ${dv.cls}" title="${esc(dv.tip)}">${dv.icon}</span>`:`<span class="msgTransport">${transport}</span>`}</div></div></div>`;}el.innerHTML=html;if(keepBottom||document.getElementById('viewMessages').classList.contains('active'))el.scrollTop=el.scrollHeight;}
async function loadPrimaryMessages(force=false,preserveScroll=false){
  const list=document.getElementById('messageList');
  const oldHeight=list.scrollHeight,oldTop=list.scrollTop;
  try{
    const r=await fetch(`/api/messages?limit=${messageFetchLimit}&_=${Date.now()}`,{cache:'no-store'});
    const b=await r.json();
    if(!r.ok||!b.success)throw new Error(b.message||`HTTP ${r.status}`);
    const rows=(b.data||[]).slice().sort((a,b)=>msgTimeMs(a)-msgTimeMs(b));
    const previousNewest=messageNewestSeen;
    primaryMessages=rows;
    messageNewestSeen=Math.max(...rows.map(msgTimeMs),0);
    document.getElementById('messageStatus').textContent=`${rows.length} mensagens · atualizado ${new Date().toLocaleTimeString('pt-BR')}`;
    if(!messagesInitialized){
      messagesInitialized=true;
      messageSeenIds=new Set(rows.map(messageKey));
      if(!localStorage.getItem(MESSAGE_READ_KEY))localStorage.setItem(MESSAGE_READ_KEY,String(messageNewestSeen));
    }else{
      for(const m of rows)messageSeenIds.add(messageKey(m));
    }
    updateUnreadBadge();
    renderMessages(force||messageNewestSeen>previousNewest);
    if(document.getElementById('viewMessages').classList.contains('active'))markMessagesRead();
    if(preserveScroll){
      const delta=Math.max(0,list.scrollHeight-oldHeight);
      list.scrollTop=oldTop+delta;
    }
    return true;
  }catch(e){
    document.getElementById('messageStatus').textContent=`Erro: ${e}`;
    return false;
  }
}
async function reloadPrimaryMessages(){
  const btn=document.getElementById('messageReload');
  btn.disabled=true;
  document.getElementById('messageStatus').textContent='Atualizando...';
  try{await loadPrimaryMessages(false,false);}finally{btn.disabled=false;}
}
async function loadOlderPrimaryMessages(){
  const btn=document.getElementById('messageLoadOlder');
  btn.disabled=true;
  try{
    if(messageFetchLimit>=1500){
      document.getElementById('messageStatus').textContent='Limite de 1.500 mensagens já carregado.';
      return;
    }
    const before=primaryMessages.map(msgTimeMs).filter(Boolean);
    const oldestBefore=before.length?Math.min(...before):Infinity;
    messageFetchLimit=Math.min(1500,messageFetchLimit+250);
    document.getElementById('messageStatus').textContent=`Carregando histórico anterior (até ${messageFetchLimit})...`;
    const ok=await loadPrimaryMessages(false,true);
    if(!ok)return;
    const after=primaryMessages.map(msgTimeMs).filter(Boolean);
    const oldestAfter=after.length?Math.min(...after):Infinity;
    document.getElementById('messageStatus').textContent=oldestAfter<oldestBefore
      ? `${primaryMessages.length} mensagens · histórico ampliado`
      : 'Nenhuma mensagem anterior adicional disponível.';
  }finally{btn.disabled=false;}
}
async function sendPrimaryMessage(){const input=document.getElementById('messageInput');const text=input.value.trim();if(!text)return;const bytes=new TextEncoder().encode(text).length;if(bytes>600){alert('Mensagem muito longa. Reduza o texto para até aproximadamente 600 bytes.');return;}const btn=document.getElementById('messageSend');btn.disabled=true;document.getElementById('messageStatus').textContent='Enviando...';try{const r=await fetch('/api/messages/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});const b=await r.json();if(!r.ok||!b.success)throw new Error(b.message||b.error||`HTTP ${r.status}`);input.value='';updateMessageCounter();document.getElementById('messageStatus').textContent='Mensagem enviada ao MeshMonitor';setTimeout(()=>loadPrimaryMessages(true),450);}catch(e){document.getElementById('messageStatus').textContent=`Falha no envio: ${e}`;alert(`Não foi possível enviar: ${e}`);}finally{btn.disabled=false;input.focus();}}
function updateMessageCounter(){const el=document.getElementById('messageInput'),n=new TextEncoder().encode(el.value).length,c=document.getElementById('messageCounter');c.textContent=`${n} B`;c.classList.toggle('over',n>600);}
document.getElementById('messageReload').addEventListener('click',reloadPrimaryMessages);document.getElementById('messageLoadOlder').addEventListener('click',loadOlderPrimaryMessages);document.getElementById('messageSend').addEventListener('click',sendPrimaryMessage);document.getElementById('messageInput').addEventListener('input',updateMessageCounter);document.getElementById('messageInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendPrimaryMessage();}});updateMessageCounter();setInterval(()=>loadPrimaryMessages(false),2500);loadPrimaryMessages(false);


document.querySelectorAll('.navbtn').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
for(const id of ['trafficDirection','trafficType']) document.getElementById(id).addEventListener('change',renderTraffic);
document.getElementById('trafficSearch').addEventListener('input',renderTraffic);
document.getElementById('trafficPause').addEventListener('click',toggleTrafficPause);
document.getElementById('trafficReload').addEventListener('click',async()=>{ trafficPackets=[];trafficInitialized=false;selectedPacketId=null;journeySeen=new Set();await loadTrafficInitial(); });
document.getElementById('trafficDump').addEventListener('click',downloadTrafficDump);
document.getElementById('soundEnabled').addEventListener('change',()=>{ ensureAudio(); savePrefs(); });
document.getElementById('soundVolume').addEventListener('input',()=>{ document.getElementById('soundVolumeValue').textContent=`${document.getElementById('soundVolume').value}%`; savePrefs(); });
document.getElementById('soundTone').addEventListener('change',savePrefs);
document.getElementById('soundTest').addEventListener('click',()=>playNotification(true));
for(const id of ['activityAnimationEnabled','activityOriginEnabled','activityRelayEnabled','activityDuration']) document.getElementById(id).addEventListener('change',()=>{savePrefs(); if(!document.getElementById('activityAnimationEnabled').checked){activityLayer.clearLayers();activityMarkers.clear();}});
document.getElementById('autoZoomTraceroute').addEventListener('change',()=>{savePrefs(); if(!document.getElementById('autoZoomTraceroute').checked) disableAutoZoomAndRestore();});
document.getElementById('nodeInfoFlowEnabled').addEventListener('change',()=>{savePrefs(); if(!document.getElementById('nodeInfoFlowEnabled').checked){flowGeneration++;flowLayer.clearLayers();}});
document.getElementById('flowToast').addEventListener('click',()=>setView('map'));

const legend = L.control({position:'bottomright'});
legend.onAdd = () => {
  const d = L.DomUtil.create('div','legend');
  d.innerHTML = '<b>Último tráfego</b><br><span class="dot trafficFresh"></span>até 2 h<br><span class="dot trafficWarm"></span>2 a 24 h<br><span class="dot trafficOld"></span>mais de 24 h<br><span class="dot trafficUnknown"></span>sem registro';
  return d;
};
legend.addTo(map);

initVisualPrefs();
load(true).then(()=>{ if(document.getElementById('playMode').value==='live') startLivePolling(); });
loadTrafficInitial();
setInterval(() => load(false), 60000);
</script>
</body>
</html>'''.replace('__TITLE__', TITLE.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')).replace('__DISPLAY_TITLE__', DISPLAY_TITLE.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))


def _mm_api_request(path: str, method: str = "GET", payload=None):
    if not MM_API_TOKEN:
        raise RuntimeError("MM_API_TOKEN não configurado; integração com MeshMonitor indisponível")
    url = f"{MM_BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {MM_API_TOKEN}", "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"MeshMonitor HTTP {e.code}: {raw[:800]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Falha ao acessar MeshMonitor: {e}") from e


def _mm_api_get(path: str):
    return _mm_api_request(path, "GET")


def _mm_api_post(path: str, payload: dict):
    return _mm_api_request(path, "POST", payload)


def _message_name_index():
    try:
        top = json.loads(TOPOLOGY_FILE.read_text(encoding="utf-8"))
    except Exception:
        top = {}
    by_num, by_id = {}, {}
    for n in top.get("nodes", []) or []:
        name = n.get("longName") or n.get("name") or n.get("shortName") or n.get("nodeId")
        try:
            by_num[int(n.get("nodeNum"))] = name
        except Exception:
            pass
        if n.get("nodeId"):
            by_id[str(n.get("nodeId"))] = name
    return by_num, by_id


def _primary_messages(limit: int = 250):
    source = urllib.parse.quote(MM_SOURCE, safe="")
    body = _mm_api_get(f"/api/v1/sources/{source}/messages?channel=0&limit={max(1, min(limit, 1500))}")
    rows = body.get("data", []) if isinstance(body, dict) else []
    by_num, by_id = _message_name_index()
    keep = {
        "id", "fromNodeNum", "toNodeNum", "fromNodeId", "toNodeId", "text", "channel",
        "requestId", "timestamp", "createdAt", "hopStart", "hopLimit", "relayNode",
        "viaMqtt", "viaStoreForward", "xeddsaSigned", "rxSnr", "rxRssi", "ackFailed",
        "routingErrorReceived", "deliveryState", "wantAck", "ackFromNode", "routingErrorCode",
        "sourcePath", "spoofSuspected"
    }
    out = []
    for row in rows:
        if not isinstance(row, dict) or int(row.get("channel") or 0) != 0:
            continue
        item = {k: row.get(k) for k in keep if k in row}
        fnum = row.get("fromNodeNum")
        fid = row.get("fromNodeId")
        try:
            item["fromName"] = by_num.get(int(fnum)) or by_id.get(str(fid)) or fid
        except Exception:
            item["fromName"] = by_id.get(str(fid)) or fid
        item["receivedAt"] = row.get("createdAt") or row.get("timestamp")
        item["mine"] = bool(row.get("sourcePath") == "http_api" and not row.get("spoofSuspected"))
        out.append(item)
    return {"success": True, "count": len(out), "data": out}


def _send_primary_message(text: str):
    clean = str(text or "").strip()
    if not clean:
        raise ValueError("Mensagem vazia")
    if len(clean.encode("utf-8")) > 800:
        raise ValueError("Mensagem excede o limite de segurança do Traffic Analyzer")
    source = urllib.parse.quote(MM_SOURCE, safe="")
    return _mm_api_post(f"/api/v1/sources/{source}/messages", {"text": clean, "channel": 0})


def _live_traceroutes(limit: int):
    source = urllib.parse.quote(MM_SOURCE, safe="")
    body = _mm_api_get(f"/api/v1/sources/{source}/traceroutes?limit={limit}")
    rows = body.get("data", []) if isinstance(body, dict) else []
    # Projeção mínima: não devolve token, configuração, PSK nem outros dados da API.
    keep = {
        "id", "packetId", "fromNodeNum", "toNodeNum", "fromNodeId", "toNodeId",
        "route", "routeBack", "snrTowards", "snrBack", "routePositions",
        "channel", "timestamp", "createdAt",
    }
    return [{k: row.get(k) for k in keep if k in row} for row in rows if isinstance(row, dict)]




PACKET_KEEP_FIELDS = {
    "id", "packet_id", "timestamp", "from_node", "from_node_id", "from_node_longName",
    "to_node", "to_node_id", "to_node_longName", "channel", "portnum", "portnum_name",
    "encrypted", "snr", "rssi", "hop_limit", "hop_start", "relay_node", "payload_size",
    "want_ack", "priority", "payload_preview", "metadata", "direction", "created_at",
    "decrypted_by", "decrypted_channel_id", "transport_mechanism", "spoof_suspected",
    "xeddsa_signed",
}


def _sanitize_packet(row: dict):
    item = {k: row.get(k) for k in PACKET_KEEP_FIELDS if k in row}
    # Privacidade: broadcasts são públicos no canal e podem preservar o payload.
    # Mensagens diretas têm conteúdo/metadata removidos antes de chegar ao navegador
    # OU ao arquivo histórico persistente.
    portnum = item.get("portnum")
    try:
        is_text = item.get("portnum_name") == "TEXT_MESSAGE_APP" or int(portnum) == 1
    except (TypeError, ValueError):
        is_text = item.get("portnum_name") == "TEXT_MESSAGE_APP"
    if is_text:
        to_num = item.get("to_node")
        to_id = str(item.get("to_node_id") or "").lower()
        is_broadcast = to_num in {0xFFFFFFFF, -1} or to_id in {"!ffffffff", "broadcast"}
        if not is_broadcast:
            item["payload_preview"] = "[conteúdo oculto]"
            item["metadata"] = None
    return item


def _mm_packets_raw(limit: int, since=None, offset: int = 0):
    source = urllib.parse.quote(MM_SOURCE, safe="")
    params = {"limit": str(limit), "offset": str(offset)}
    if since is not None:
        params["since"] = str(since)
    body = _mm_api_get(f"/api/v1/sources/{source}/packets?{urllib.parse.urlencode(params)}")
    rows = body.get("data", []) if isinstance(body, dict) else []
    return body if isinstance(body, dict) else {}, [row for row in rows if isinstance(row, dict)]


def _packets(limit: int, since=None, offset: int = 0):
    body, rows = _mm_packets_raw(limit, since=since, offset=offset)
    projected = [_sanitize_packet(row) for row in rows]
    return {
        "success": True,
        "count": len(projected),
        "total": body.get("total", len(projected)),
        "offset": body.get("offset", offset),
        "limit": body.get("limit", limit),
        "data": projected,
    }


def _archive_connect():
    TRAFFIC_ARCHIVE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(TRAFFIC_ARCHIVE_DB), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _archive_init():
    with _archive_connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS packets (
          archive_id INTEGER PRIMARY KEY AUTOINCREMENT,
          archive_key TEXT NOT NULL UNIQUE,
          source_id TEXT NOT NULL,
          mm_row_id INTEGER,
          packet_id INTEGER,
          timestamp INTEGER NOT NULL,
          created_at INTEGER,
          direction TEXT,
          from_node INTEGER,
          from_node_id TEXT,
          from_node_long_name TEXT,
          to_node INTEGER,
          to_node_id TEXT,
          to_node_long_name TEXT,
          channel INTEGER,
          portnum INTEGER,
          portnum_name TEXT,
          encrypted INTEGER,
          snr REAL,
          rssi REAL,
          hop_limit INTEGER,
          hop_start INTEGER,
          relay_node INTEGER,
          payload_size INTEGER,
          want_ack INTEGER,
          priority INTEGER,
          payload_preview TEXT,
          metadata TEXT,
          decrypted_by TEXT,
          decrypted_channel_id TEXT,
          transport_mechanism INTEGER,
          spoof_suspected INTEGER,
          xeddsa_signed INTEGER,
          archived_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_packets_timestamp ON packets(timestamp);
        CREATE INDEX IF NOT EXISTS idx_packets_packet_id ON packets(packet_id);
        CREATE INDEX IF NOT EXISTS idx_packets_from_node ON packets(from_node);
        CREATE INDEX IF NOT EXISTS idx_packets_to_node ON packets(to_node);
        CREATE INDEX IF NOT EXISTS idx_packets_portnum_name ON packets(portnum_name);
        CREATE INDEX IF NOT EXISTS idx_packets_direction ON packets(direction);
        CREATE INDEX IF NOT EXISTS idx_packets_relay_node ON packets(relay_node);
        """)


def _archive_key(item: dict):
    rid = item.get("id")
    if rid is not None:
        return f"{MM_SOURCE}:row:{rid}:{item.get('timestamp') or item.get('created_at') or ''}"
    return ":".join([
        MM_SOURCE,
        "fallback",
        str(item.get("packet_id") or ""),
        str(item.get("timestamp") or ""),
        str(item.get("direction") or ""),
        str(item.get("from_node") or ""),
        str(item.get("to_node") or ""),
        str(item.get("relay_node") or ""),
        str(item.get("portnum") or item.get("portnum_name") or ""),
    ])


def _archive_metadata(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return str(value)


def _archive_insert_rows(rows):
    if not rows:
        return 0
    now_ms = int(time.time() * 1000)
    sql = """
      INSERT OR IGNORE INTO packets (
        archive_key, source_id, mm_row_id, packet_id, timestamp, created_at, direction,
        from_node, from_node_id, from_node_long_name, to_node, to_node_id, to_node_long_name,
        channel, portnum, portnum_name, encrypted, snr, rssi, hop_limit, hop_start, relay_node,
        payload_size, want_ack, priority, payload_preview, metadata, decrypted_by,
        decrypted_channel_id, transport_mechanism, spoof_suspected, xeddsa_signed, archived_at
      ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """
    values = []
    for raw in rows:
        item = _sanitize_packet(raw)
        ts = item.get("timestamp") or item.get("created_at") or now_ms
        try:
            ts = int(ts)
        except Exception:
            ts = now_ms
        if ts < 10_000_000_000:
            ts *= 1000
        values.append((
            _archive_key(item), MM_SOURCE, item.get("id"), item.get("packet_id"), ts,
            item.get("created_at"), item.get("direction"), item.get("from_node"),
            item.get("from_node_id"), item.get("from_node_longName"), item.get("to_node"),
            item.get("to_node_id"), item.get("to_node_longName"), item.get("channel"),
            item.get("portnum"), item.get("portnum_name"), int(bool(item.get("encrypted"))) if item.get("encrypted") is not None else None,
            item.get("snr"), item.get("rssi"), item.get("hop_limit"), item.get("hop_start"),
            item.get("relay_node"), item.get("payload_size"), int(bool(item.get("want_ack"))) if item.get("want_ack") is not None else None,
            item.get("priority"), item.get("payload_preview"), _archive_metadata(item.get("metadata")),
            item.get("decrypted_by"), item.get("decrypted_channel_id"), item.get("transport_mechanism"),
            int(bool(item.get("spoof_suspected"))) if item.get("spoof_suspected") is not None else None,
            int(bool(item.get("xeddsa_signed"))) if item.get("xeddsa_signed") is not None else None,
            now_ms,
        ))
    with _archive_connect() as conn:
        before = conn.total_changes
        conn.executemany(sql, values)
        return conn.total_changes - before


def _archive_last_timestamp():
    with _archive_connect() as conn:
        row = conn.execute("SELECT MAX(timestamp) AS ts FROM packets WHERE source_id=?", (MM_SOURCE,)).fetchone()
        return int(row["ts"]) if row and row["ts"] is not None else None


def _archive_cleanup():
    if ARCHIVE_RETENTION_DAYS <= 0:
        return 0
    cutoff = int(time.time() * 1000) - ARCHIVE_RETENTION_DAYS * 86400 * 1000
    with _archive_connect() as conn:
        cur = conn.execute("DELETE FROM packets WHERE timestamp < ?", (cutoff,))
        return max(0, cur.rowcount or 0)


def _archive_sync_pass(since):
    offset = 0
    inserted = 0
    pages = 0
    while pages < 10000:
        body, rows = _mm_packets_raw(ARCHIVE_PAGE_SIZE, since=since, offset=offset)
        if not rows:
            break
        inserted += _archive_insert_rows(rows)
        pages += 1
        got = len(rows)
        offset += got
        try:
            total = int(body.get("total"))
        except Exception:
            total = None
        if total is not None and offset >= total:
            break
        if total is None and got < ARCHIVE_PAGE_SIZE:
            break
    return inserted


def _archive_sync_once(full=False):
    last_ts = None if full else _archive_last_timestamp()
    since = None if last_ts is None else max(0, last_ts - ARCHIVE_OVERLAP_MS)
    # O endpoint por fonte usa paginação por offset. Como novos pacotes podem
    # chegar enquanto as páginas são percorridas, fazemos duas passagens sobre
    # a mesma janela. INSERT OR IGNORE torna a segunda passagem barata e reduz
    # o risco de lacunas causadas por deslocamento das páginas.
    inserted = _archive_sync_pass(since)
    inserted += _archive_sync_pass(since)
    _archive_cleanup()
    return inserted


def _archive_worker():
    with _archive_status_lock:
        _archive_status["running"] = True
    first_success = False
    while not _archive_stop.is_set():
        try:
            # Na primeira sincronização, pagina tudo o que ainda está retido no
            # Packet Monitor. Depois trabalha apenas sobre uma janela sobreposta.
            inserted = _archive_sync_once(full=not first_success)
            first_success = True
            with _archive_status_lock:
                _archive_status.update({
                    "last_sync_ms": int(time.time() * 1000),
                    "last_error": None,
                    "inserted_last_sync": inserted,
                })
        except Exception as exc:
            with _archive_status_lock:
                _archive_status.update({
                    "last_sync_ms": int(time.time() * 1000),
                    "last_error": str(exc),
                    "inserted_last_sync": 0,
                })
        _archive_stop.wait(ARCHIVE_POLL_SECONDS)
    with _archive_status_lock:
        _archive_status["running"] = False


def _archive_status_snapshot():
    try:
        with _archive_connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n, MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts FROM packets").fetchone()
            count = int(row["n"] or 0)
            first_ts = row["first_ts"]
            last_ts = row["last_ts"]
    except Exception:
        count, first_ts, last_ts = 0, None, None
    with _archive_status_lock:
        status = dict(_archive_status)
    return {
        "db": str(TRAFFIC_ARCHIVE_DB),
        "packets": count,
        "firstTimestamp": first_ts,
        "lastTimestamp": last_ts,
        "retentionDays": ARCHIVE_RETENTION_DAYS,
        "schemaVersion": 1,
        **status,
    }


def _archive_where(query):
    clauses = []
    params = []
    def add_num(name, op):
        raw = (query.get(name) or [None])[0]
        if raw not in (None, ""):
            clauses.append(f"timestamp {op} ?")
            params.append(int(raw))
    add_num("since", ">=")
    add_num("until", "<=")
    direction = (query.get("direction") or [None])[0]
    if direction in {"rx", "tx"}:
        clauses.append("direction = ?")
        params.append(direction)
    ptype = (query.get("type") or [None])[0]
    if ptype:
        clauses.append("portnum_name = ?")
        params.append(ptype)
    node = (query.get("node") or [None])[0]
    if node not in (None, ""):
        try:
            n = int(node, 0)
            clauses.append("(from_node = ? OR to_node = ?)")
            params.extend([n, n])
        except ValueError:
            clauses.append("(from_node_id = ? OR to_node_id = ? OR from_node_long_name LIKE ? OR to_node_long_name LIKE ?)")
            params.extend([node, node, f"%{node}%", f"%{node}%"])
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def _archive_row_to_dict(row):
    d = dict(row)
    meta = d.get("metadata")
    if meta:
        try:
            d["metadata"] = json.loads(meta)
        except Exception:
            pass
    for key in ("encrypted", "want_ack", "spoof_suspected", "xeddsa_signed"):
        if d.get(key) is not None:
            d[key] = bool(d[key])
    # Mantém aliases compatíveis com os nomes expostos pelo Packet Monitor.
    d["id"] = d.pop("mm_row_id", None)
    d["from_node_longName"] = d.pop("from_node_long_name", None)
    d["to_node_longName"] = d.pop("to_node_long_name", None)
    return d


def _archive_packets_query(query):
    limit = max(1, min(int((query.get("limit") or ["1000"])[0]), 5000))
    offset = max(0, int((query.get("offset") or ["0"])[0]))
    where, params = _archive_where(query)
    with _archive_connect() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) AS n FROM packets{where}", params).fetchone()["n"])
        rows = conn.execute(
            f"SELECT * FROM packets{where} ORDER BY timestamp DESC, archive_id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    data = [_archive_row_to_dict(r) for r in rows]
    return {"success": True, "count": len(data), "total": total, "offset": offset, "limit": limit, "data": data}


def _archive_stats_query(query):
    where, params = _archive_where(query)
    with _archive_connect() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS total, SUM(direction='rx') AS rx, SUM(direction='tx') AS tx, MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts, COUNT(DISTINCT from_node) AS origin_nodes FROM packets{where}",
            params,
        ).fetchone()
        types = conn.execute(
            f"SELECT COALESCE(portnum_name, CAST(portnum AS TEXT), 'UNKNOWN') AS type, COUNT(*) AS count FROM packets{where} GROUP BY COALESCE(portnum_name, CAST(portnum AS TEXT), 'UNKNOWN') ORDER BY count DESC",
            params,
        ).fetchall()
    return {
        "success": True,
        "total": int(row["total"] or 0),
        "rx": int(row["rx"] or 0),
        "tx": int(row["tx"] or 0),
        "firstTimestamp": row["first_ts"],
        "lastTimestamp": row["last_ts"],
        "originNodes": int(row["origin_nodes"] or 0),
        "byType": [{"type": r["type"], "count": int(r["count"])} for r in types],
    }


def _archive_nodes_query(query):
    where, params = _archive_where(query)
    with _archive_connect() as conn:
        rows = conn.execute(
            f"""SELECT from_node AS nodeNum, MAX(from_node_id) AS nodeId,
                       MAX(from_node_long_name) AS longName, COUNT(*) AS packets,
                       AVG(snr) AS avgSnr, AVG(rssi) AS avgRssi, MAX(timestamp) AS lastSeen
                FROM packets{where}
                WHERE_APPEND
                GROUP BY from_node ORDER BY packets DESC""".replace(
                    "WHERE_APPEND",
                    (" AND from_node IS NOT NULL" if where else " WHERE from_node IS NOT NULL")
                ),
            params,
        ).fetchall()
    return {"success": True, "count": len(rows), "data": [dict(r) for r in rows]}


def _archive_links_query(query):
    where, params = _archive_where(query)
    suffix = " AND from_node IS NOT NULL AND to_node IS NOT NULL" if where else " WHERE from_node IS NOT NULL AND to_node IS NOT NULL"
    with _archive_connect() as conn:
        rows = conn.execute(
            f"""SELECT from_node AS fromNode, MAX(from_node_id) AS fromNodeId,
                       to_node AS toNode, MAX(to_node_id) AS toNodeId,
                       COUNT(*) AS packets, AVG(snr) AS avgSnr, AVG(rssi) AS avgRssi,
                       MAX(timestamp) AS lastSeen
                FROM packets{where}{suffix}
                GROUP BY from_node, to_node ORDER BY packets DESC""",
            params,
        ).fetchall()
    return {"success": True, "count": len(rows), "data": [dict(r) for r in rows]}


def _archive_export(query, fmt="jsonl"):
    export_query = dict(query)
    export_query["limit"] = [str(max(1, min(int((query.get("limit") or ["100000"])[0]), 100000)))]
    export_query["offset"] = ["0"]
    data = _archive_packets_query(export_query)["data"]
    if fmt == "csv":
        out = io.StringIO()
        fields = [
            "archive_id", "source_id", "id", "packet_id", "timestamp", "created_at", "direction",
            "from_node", "from_node_id", "from_node_longName", "to_node", "to_node_id", "to_node_longName",
            "channel", "portnum", "portnum_name", "encrypted", "snr", "rssi", "hop_limit", "hop_start",
            "relay_node", "payload_size", "want_ack", "priority", "payload_preview", "metadata",
            "decrypted_by", "decrypted_channel_id", "transport_mechanism", "spoof_suspected", "xeddsa_signed", "archived_at",
        ]
        w = csv.DictWriter(out, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in data:
            r = dict(row)
            if isinstance(r.get("metadata"), (dict, list)):
                r["metadata"] = json.dumps(r["metadata"], ensure_ascii=False)
            w.writerow(r)
        return "text/csv; charset=utf-8", out.getvalue().encode("utf-8")
    body = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in data)
    return "application/x-ndjson; charset=utf-8", body.encode("utf-8")



def _load_topology_safe():
    try:
        raw = json.loads(TOPOLOGY_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _node_last_seen_map(topology):
    result = {}
    for n in topology.get("nodes", []) or []:
        try:
            num = int(n.get("nodeNum"))
        except Exception:
            continue
        heard = n.get("lastHeard")
        try:
            heard_ms = int(float(heard) * 1000) if float(heard or 0) < 10_000_000_000 else int(float(heard))
        except Exception:
            heard_ms = 0
        result[num] = {"lastSeen": heard_ms, "name": n.get("name") or n.get("longName") or n.get("nodeId"), "nodeId": n.get("nodeId")}
    with _archive_connect() as conn:
        rows = conn.execute("""SELECT from_node AS nodeNum, MAX(timestamp) AS lastSeen, MAX(from_node_long_name) AS longName, MAX(from_node_id) AS nodeId FROM packets WHERE from_node IS NOT NULL GROUP BY from_node""").fetchall()
    for r in rows:
        num = int(r["nodeNum"])
        cur = result.setdefault(num, {"lastSeen": 0, "name": None, "nodeId": None})
        cur["lastSeen"] = max(int(cur.get("lastSeen") or 0), int(r["lastSeen"] or 0))
        cur["name"] = cur.get("name") or r["longName"] or r["nodeId"] or f"!{num & 0xffffffff:08x}"
        cur["nodeId"] = cur.get("nodeId") or r["nodeId"] or f"!{num & 0xffffffff:08x}"
    return result


def _trace_leg_hops(path):
    if not isinstance(path, list) or len(path) < 2:
        return None
    return max(0, len(path) - 1)


def _network_health():
    now = int(time.time() * 1000)
    topology = _load_topology_safe()
    nodes = _node_last_seen_map(topology)
    cutoff2 = now - 2 * 3600 * 1000
    cutoff24 = now - 24 * 3600 * 1000
    cutoff7 = now - 7 * 86400 * 1000
    seen = [int(x.get("lastSeen") or 0) for x in nodes.values()]
    active2 = sum(1 for ts in seen if ts >= cutoff2)
    active24 = sum(1 for ts in seen if ts >= cutoff24)
    active7 = sum(1 for ts in seen if ts >= cutoff7)
    no_traffic = sum(1 for ts in seen if ts <= 0)
    silent24 = sum(1 for ts in seen if 0 < ts < cutoff24)

    with _archive_connect() as conn:
        r24 = conn.execute("""SELECT COUNT(*) AS total, SUM(direction='rx') AS rx, SUM(direction='tx') AS tx FROM packets WHERE timestamp>=?""", (cutoff24,)).fetchone()
        daily_rows = conn.execute("""SELECT strftime('%Y-%m-%d', timestamp/1000, 'unixepoch', 'localtime') AS day, COUNT(*) AS packets, COUNT(DISTINCT from_node) AS nodes FROM packets WHERE timestamp>=? GROUP BY day ORDER BY day""", (cutoff7,)).fetchall()
        node7 = conn.execute("""SELECT from_node AS nodeNum, COUNT(*) AS packets, AVG(snr) AS avgSnr, MAX(timestamp) AS lastSeen, MAX(from_node_long_name) AS longName, MAX(from_node_id) AS nodeId FROM packets WHERE timestamp>=? AND from_node IS NOT NULL GROUP BY from_node""", (cutoff7,)).fetchall()
        chat_rows = conn.execute("""
            SELECT
              from_node AS nodeNum,
              COUNT(DISTINCT (CAST(from_node AS TEXT) || ':' || COALESCE(CAST(packet_id AS TEXT), archive_key))) AS interactions,
              MAX(from_node_long_name) AS longName,
              MAX(from_node_id) AS nodeId
            FROM packets
            WHERE from_node IS NOT NULL
              AND channel = 0
              AND portnum_name = 'TEXT_MESSAGE_APP'
              AND (
                to_node IN (4294967295, -1)
                OR lower(COALESCE(to_node_id,'')) IN ('!ffffffff','broadcast')
              )
            GROUP BY from_node
            ORDER BY interactions DESC, longName COLLATE NOCASE
        """).fetchall()
    by_node7 = {int(r['nodeNum']): dict(r) for r in node7}
    chat_interactions = []
    for r in chat_rows:
        num = int(r["nodeNum"])
        info = nodes.get(num, {})
        node_id = info.get("nodeId") or r["nodeId"] or f"!{num & 0xffffffff:08x}"
        name = info.get("name") or r["longName"] or node_id
        chat_interactions.append({
            "nodeNum": num,
            "nodeId": node_id,
            "name": name,
            "interactions": int(r["interactions"] or 0),
        })
    daily_map = {r['day']: dict(r) for r in daily_rows}
    daily=[]
    for i in range(6,-1,-1):
        ts = now - i*86400*1000
        day = datetime.fromtimestamp(ts/1000).strftime('%Y-%m-%d')
        row=daily_map.get(day,{})
        daily.append({"day":day,"label":datetime.fromtimestamp(ts/1000).strftime('%d/%m'),"packets":int(row.get('packets') or 0),"nodes":int(row.get('nodes') or 0)})

    traces = topology.get("traces", []) or []
    forward=ret=roundtrip=incomplete=0; hop_samples=[]
    for tr in traces:
        fh=_trace_leg_hops(tr.get('forwardPath')); rh=_trace_leg_hops(tr.get('returnPath'))
        if fh is not None: forward += 1; hop_samples.append(fh)
        if rh is not None: ret += 1; hop_samples.append(rh)
        if fh is not None and rh is not None: roundtrip += 1
        if fh is None or rh is None: incomplete += 1
    avg_hops = round(sum(hop_samples)/len(hop_samples),2) if hop_samples else None
    med_hops = round(float(statistics.median(hop_samples)),2) if hop_samples else None

    edges=topology.get('edges',[]) or []
    recent_edges=sum(1 for e in edges if int(e.get('lastSeenMs') or 0)>=cutoff24)
    attention=[]
    for num, info in nodes.items():
        ts=int(info.get('lastSeen') or 0)
        if ts and ts>=cutoff24: continue
        seven=by_node7.get(num,{})
        attention.append({"nodeNum":num,"nodeId":info.get('nodeId'),"name":info.get('name'),"lastSeen":ts or None,"packets7d":int(seven.get('packets') or 0),"avgSnr7d":round(float(seven['avgSnr']),2) if seven.get('avgSnr') is not None else None})
    attention.sort(key=lambda x: (x['lastSeen'] is None, x['lastSeen'] or 0))
    attention=attention[:25]
    total_tr=len(traces)
    return {"success":True,"generatedAtMs":now,"nodes":{"total":len(nodes),"active2h":active2,"active24h":active24,"active7d":active7,"silent24h":silent24,"noTraffic":no_traffic},"traffic":{"packets24h":int(r24['total'] or 0),"rx24h":int(r24['rx'] or 0),"tx24h":int(r24['tx'] or 0)},"links":{"observed":len(edges),"recent24h":recent_edges},"traceroutes":{"total":total_tr,"forward":forward,"return":ret,"roundTrip":roundtrip,"incomplete":incomplete,"roundTripRate":round(100*roundtrip/total_tr,2) if total_tr else 0,"avgHops":avg_hops,"medianHops":med_hops},"daily":daily,"chatInteractions":chat_interactions,"attentionNodes":attention}


def _path_signature(path):
    if not isinstance(path,list) or len(path)<2: return None
    vals=[]
    for p in path:
        if isinstance(p,dict): vals.append(str(p.get('nodeNum') or p.get('nodeId') or p.get('name') or '?'))
        else: vals.append(str(p))
    return ' > '.join(vals)


def _anomalies():
    now=int(time.time()*1000); topology=_load_topology_safe(); nodes=_node_last_seen_map(topology); data=[]
    cutoff24=now-24*3600*1000
    for num,info in nodes.items():
        ts=int(info.get('lastSeen') or 0)
        if ts<=0: continue
        age=now-ts
        if age>7*86400*1000:
            data.append({"severity":"critical","type":"node_silent","title":"Nó silencioso há mais de 7 dias","subject":info.get('name') or info.get('nodeId'),"message":"Não há tráfego recente deste nó no histórico disponível.","evidence":f"Última observação: {datetime.fromtimestamp(ts/1000).strftime('%d/%m/%Y %H:%M')}","timestampMs":ts})
        elif age>24*3600*1000:
            data.append({"severity":"warning","type":"node_silent","title":"Nó silencioso há mais de 24 h","subject":info.get('name') or info.get('nodeId'),"message":"O nó ultrapassou a janela de 24 horas sem tráfego observado.","evidence":f"Última observação: {datetime.fromtimestamp(ts/1000).strftime('%d/%m/%Y %H:%M')}","timestampMs":ts})

    for e in topology.get('edges',[]) or []:
        recent=[]; prev=[]
        for ev in e.get('events',[]) or []:
            sn=ev.get('snr'); ts=int(ev.get('timestampMs') or 0)
            if sn is None: continue
            try: sn=float(sn)
            except Exception: continue
            if ts>=cutoff24: recent.append(sn)
            elif ts>=now-48*3600*1000: prev.append(sn)
        if len(recent)>=2 and len(prev)>=2:
            a=sum(recent)/len(recent); b=sum(prev)/len(prev); delta=a-b
            if delta<=-4.0:
                data.append({"severity":"warning" if delta>-8 else "critical","type":"snr_degradation","title":"Queda de SNR no enlace","subject":f"{e.get('aName') or e.get('aId')} ↔ {e.get('bName') or e.get('bId')}","message":f"SNR médio caiu {abs(delta):.1f} dB entre as duas janelas de 24 h.","evidence":f"Anterior: {b:.1f} dB · Atual: {a:.1f} dB · amostras {len(prev)}/{len(recent)}","timestampMs":int(e.get('lastSeenMs') or now)})

    groups={}
    for tr in topology.get('traces',[]) or []:
        a=tr.get('fromNodeNum'); b=tr.get('toNodeNum')
        if a is None or b is None: continue
        key=(int(a),int(b)); groups.setdefault(key,[]).append(tr)
    for key,arr in groups.items():
        arr=sorted(arr,key=lambda x:int(x.get('timestampMs') or 0))
        latest=arr[-1]; fh=_trace_leg_hops(latest.get('forwardPath')); rh=_trace_leg_hops(latest.get('returnPath'))
        subj=f"{latest.get('fromName')} → {latest.get('toName')}"
        if (fh is None) != (rh is None):
            data.append({"severity":"info","type":"asymmetric_trace","title":"Traceroute assimétrico","subject":subj,"message":"A observação mais recente contém apenas um dos sentidos do traceroute.","evidence":f"Ida: {'sem rota' if fh is None else str(fh)+' hops'} · Volta: {'sem rota' if rh is None else str(rh)+' hops'}","timestampMs":int(latest.get('timestampMs') or now)})
        current=fh if fh is not None else rh
        historical=[]
        for tr in arr[:-1][-12:]:
            h=_trace_leg_hops(tr.get('forwardPath'))
            if h is None: h=_trace_leg_hops(tr.get('returnPath'))
            if h is not None: historical.append(h)
        if current is not None and len(historical)>=2:
            base=float(statistics.median(historical)); diff=current-base
            if abs(diff)>=2:
                data.append({"severity":"warning","type":"route_hops_change","title":"Mudança relevante de hops","subject":subj,"message":f"O traceroute mais recente mudou {diff:+.0f} hops em relação à mediana recente.","evidence":f"Atual: {current} hops · mediana anterior: {base:.1f} · {_path_signature(latest.get('forwardPath') or latest.get('returnPath')) or ''}","timestampMs":int(latest.get('timestampMs') or now)})

    rank={'critical':0,'warning':1,'info':2}
    data.sort(key=lambda x:(rank.get(x['severity'],9),-int(x.get('timestampMs') or 0)))
    summary={"total":len(data),"critical":sum(1 for x in data if x['severity']=='critical'),"warning":sum(1 for x in data if x['severity']=='warning'),"info":sum(1 for x in data if x['severity']=='info')}
    return {"success":True,"generatedAtMs":now,"summary":summary,"data":data[:100],"method":"Heurísticas sobre silêncio, SNR e traceroutes; resultados devem ser interpretados com contexto RF."}


def _archive_dump_zip():
    """Build a ZIP containing one valid JSON document with every archived packet.

    JSON is written directly into the compressed member in SQLite batches, so
    the complete archive is never materialized in RAM. Direct text messages are
    already redacted by _sanitize_packet before persistence.
    """
    generated = datetime.now().astimezone()
    stamp = generated.strftime("%Y-%m-%d_%H%M%S")
    download_name = f"traffic-analyzer-dump-{stamp}.zip"
    fd, tmp_name = tempfile.mkstemp(prefix="traffic-analyzer-dump-", suffix=".zip")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with _archive_connect() as conn:
            stats = conn.execute(
                "SELECT COUNT(*) AS n, MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts FROM packets"
            ).fetchone()
            metadata = {
                "traffic_analyzer_version": APP_VERSION,
                "generated_at": generated.isoformat(timespec="seconds"),
                "source_id": MM_SOURCE,
                "packet_count": int(stats["n"] or 0),
                "first_packet_timestamp": stats["first_ts"],
                "last_packet_timestamp": stats["last_ts"],
                "archive_schema_version": 1,
                "privacy": "Direct TEXT_MESSAGE_APP payloads are redacted before archival.",
            }
            cursor = conn.execute("SELECT * FROM packets ORDER BY timestamp ASC, archive_id ASC")
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as zf:
                with zf.open("traffic.json", "w", force_zip64=True) as member:
                    member.write(b'{"export":')
                    member.write(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                    member.write(b',"packets":[')
                    first = True
                    while True:
                        rows = cursor.fetchmany(1000)
                        if not rows:
                            break
                        for row in rows:
                            if not first:
                                member.write(b',')
                            first = False
                            packet = _archive_row_to_dict(row)
                            member.write(json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                    member.write(b']}')
        return tmp_path, download_name
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


class Handler(BaseHTTPRequestHandler):
    server_version = "TrafficAnalyzer/1.16.0"

    def _send(self, status, content_type, body: bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str, download_name: str):
        size = path.stat().st_size
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with path.open("rb") as src:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
            return
        if path in ("/api/topology", "/topology.json"):
            try:
                raw = TOPOLOGY_FILE.read_bytes()
                json.loads(raw.decode("utf-8"))
                self._send(200, "application/json; charset=utf-8", raw)
            except FileNotFoundError:
                self._send(503, "application/json; charset=utf-8", json.dumps({
                    "error": "topology_not_ready",
                    "message": "topology.json ainda não foi gerado",
                }).encode("utf-8"))
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({
                    "error": "topology_invalid",
                    "message": str(e),
                }).encode("utf-8"))
            return
        if path == "/api/live-traceroutes":
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                limit = int((query.get("limit") or ["100"])[0])
                limit = max(1, min(limit, 200))
                rows = _live_traceroutes(limit)
                self._send(200, "application/json; charset=utf-8", json.dumps({
                    "success": True, "count": len(rows), "data": rows,
                }, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(502, "application/json; charset=utf-8", json.dumps({
                    "success": False, "error": "live_unavailable", "message": str(e),
                }, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/packets":
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                limit = max(1, min(int((query.get("limit") or ["250"])[0]), 1000))
                offset = max(0, int((query.get("offset") or ["0"])[0]))
                since_raw = (query.get("since") or [None])[0]
                since = int(since_raw) if since_raw not in (None, "") else None
                body = _packets(limit, since=since, offset=offset)
                self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(502, "application/json; charset=utf-8", json.dumps({
                    "success": False, "error": "packet_monitor_unavailable", "message": str(e),
                }, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/messages":
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                limit = max(1, min(int((query.get("limit") or ["250"])[0]), 1500))
                body = _primary_messages(limit)
                self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(502, "application/json; charset=utf-8", json.dumps({"success": False, "error": "messages_unavailable", "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/network-health":
            try:
                self._send(200, "application/json; charset=utf-8", json.dumps(_network_health(), ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({"success": False, "error": "health_error", "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/anomalies":
            try:
                self._send(200, "application/json; charset=utf-8", json.dumps(_anomalies(), ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({"success": False, "error": "anomaly_error", "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/archive/dump":
            tmp_path = None
            try:
                tmp_path, download_name = _archive_dump_zip()
                self._send_file(tmp_path, "application/zip", download_name)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:
                try:
                    self._send(500, "application/json; charset=utf-8", json.dumps({
                        "success": False, "error": "archive_dump_error", "message": str(e),
                    }, ensure_ascii=False).encode("utf-8"))
                except Exception:
                    pass
            finally:
                if tmp_path is not None:
                    try:
                        tmp_path.unlink(missing_ok=True)
                    except Exception:
                        pass
            return
        if path.startswith("/api/archive/"):
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                if path == "/api/archive/status":
                    body = {"success": True, **_archive_status_snapshot()}
                    self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
                    return
                if path == "/api/archive/packets":
                    body = _archive_packets_query(query)
                    self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
                    return
                if path == "/api/archive/stats":
                    body = _archive_stats_query(query)
                    self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
                    return
                if path == "/api/archive/nodes":
                    body = _archive_nodes_query(query)
                    self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
                    return
                if path == "/api/archive/links":
                    body = _archive_links_query(query)
                    self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
                    return
                if path == "/api/archive/export":
                    fmt = (query.get("format") or ["jsonl"])[0].lower()
                    if fmt not in {"jsonl", "csv"}:
                        raise ValueError("format deve ser jsonl ou csv")
                    ctype, raw = _archive_export(query, fmt=fmt)
                    self._send(200, ctype, raw)
                    return
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({
                    "success": False, "error": "archive_error", "message": str(e),
                }, ensure_ascii=False).encode("utf-8"))
                return
        if path == "/health":
            ok = TOPOLOGY_FILE.exists()
            self._send(200 if ok else 503, "application/json; charset=utf-8", json.dumps({
                "ok": ok,
                "topologyFile": str(TOPOLOGY_FILE),
                "archive": _archive_status_snapshot(),
            }, ensure_ascii=False).encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"Not found\n")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/messages/send":
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length <= 0 or length > 8192:
                    raise ValueError("Corpo da requisição inválido")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                body = _send_primary_message(payload.get("text") if isinstance(payload, dict) else "")
                status = 201 if body.get("success") else 502
                self._send(status, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except ValueError as e:
                self._send(400, "application/json; charset=utf-8", json.dumps({"success": False, "error": "bad_request", "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(502, "application/json; charset=utf-8", json.dumps({"success": False, "error": "send_failed", "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        self._send(404, "text/plain; charset=utf-8", b"Not found\n")

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}", flush=True)


def main():
    _archive_init()
    archive_thread = threading.Thread(target=_archive_worker, name="traffic-archive", daemon=True)
    archive_thread.start()
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"Traffic Analyzer v{APP_VERSION} ouvindo em http://{BIND}:{PORT}/", flush=True)
    print(f"Topologia: {TOPOLOGY_FILE}", flush=True)
    print(f"Arquivo histórico de tráfego: {TRAFFIC_ARCHIVE_DB}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        _archive_stop.set()
        httpd.server_close()


if __name__ == "__main__":
    main()
