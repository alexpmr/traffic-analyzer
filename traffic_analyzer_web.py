#!/usr/bin/env python3
"""Interface web do Traffic Analyzer v1.24.1 para MeshMonitor."""

import csv
import io
import json
import os
import sqlite3
import statistics
import subprocess
import sys
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

APP_VERSION = "1.24.1"
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
_topology_refresh_lock = threading.Lock()
_version_status_lock = threading.Lock()
_version_status_cache = {"checked_at": 0.0, "data": None}
VERSION_CHECK_TTL_SECONDS = 900
GITHUB_RELEASES_LATEST_URL = "https://api.github.com/repos/alexpmr/traffic-analyzer/releases/latest"
UPDATE_SETTINGS_FILE = Path(os.getenv("UPDATE_SETTINGS_FILE", "/var/lib/traffic-analyzer/update-settings.json"))
UPDATE_REQUEST_FILE = Path(os.getenv("UPDATE_REQUEST_FILE", "/var/lib/traffic-analyzer/update-request.json"))
UPDATE_STATUS_FILE = Path(os.getenv("UPDATE_STATUS_FILE", "/var/lib/traffic-analyzer/update-status.json"))
LAST_INSTALL_FILE = Path(os.getenv("LAST_INSTALL_FILE", "/var/lib/traffic-analyzer/last-install.json"))
AUTO_UPDATE_RETRY_BACKOFF_SECONDS = 6 * 3600

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
  .trafficTable th:nth-child(1),.trafficTable td:nth-child(1){width:72px}.trafficTable th:nth-child(2),.trafficTable td:nth-child(2){width:48px}.trafficTable th:nth-child(3),.trafficTable td:nth-child(3){width:185px;max-width:185px}.trafficTable th:nth-child(4),.trafficTable td:nth-child(4){width:185px;max-width:185px}.trafficTable th:nth-child(5),.trafficTable td:nth-child(5){width:118px;max-width:118px}.trafficTable th:nth-child(6),.trafficTable td:nth-child(6){width:58px}.trafficTable th:nth-child(7),.trafficTable td:nth-child(7){width:58px}.trafficTable th:nth-child(8),.trafficTable td:nth-child(8){width:48px}
  .badge{display:inline-block;padding:2px 6px;border-radius:10px;font-size:10px;font-weight:800}.rx{background:#174f37;color:#7af0ad}.tx{background:#164a64;color:#7ddcff}.typeBadge{background:#374657;color:#e8edf2}.type-text{background:#5d3b7c}.type-position{background:#365f3a}.type-nodeinfo{background:#795628}.type-telemetry{background:#1f5d69}.type-traceroute{background:#5a487d}.type-routing{background:#754044}.type-neighbor{background:#4d5b25}
  #packetDetail{overflow:auto;border-left:1px solid #293744;background:#111a24;padding:14px}.detailTitle{font-size:16px;font-weight:800;margin-bottom:8px}.detailGrid{display:grid;grid-template-columns:120px minmax(0,1fr);gap:7px;font-size:12px}.detailGrid b{color:#9fb0bf}.emptyDetail{color:#8194a5;font-size:13px;padding-top:8px}.payloadBox{background:#172532;border:1px solid #304353;border-radius:7px;padding:9px;line-height:1.45;overflow-wrap:anywhere}.payloadRows{display:grid;grid-template-columns:minmax(110px,38%) minmax(0,1fr);gap:4px 9px}.payloadRows .k{color:#9fb0bf;font-weight:700}.payloadRows .v{overflow-wrap:anywhere}.techDetails{margin-top:8px}.techDetails summary{cursor:pointer;color:#9fc6e4;font-weight:700}.techDetails .payloadBox{margin-top:7px}.rawJson{margin-top:9px;border-top:1px solid #304353;padding-top:7px}.rawJson summary{font-size:11px;color:#8194a5;font-weight:600}.techDetails pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0d1620;border:1px solid #2e4050;border-radius:6px;padding:8px;font-size:10px;max-height:320px;overflow:auto}.broadcastTag{display:inline-block;background:#345d39;color:#a8f0b0;border-radius:9px;padding:2px 6px;font-size:10px;font-weight:800;margin-left:6px}
  #viewSettings{overflow:auto}.settingsCard{max-width:900px;margin:24px auto;background:#17212b;border:1px solid #304353;border-radius:10px;padding:20px;width:calc(100% - 48px);box-sizing:border-box}.settingsCard h2{margin-top:0}.settingsCard h3{margin:20px 0 4px;color:#e9d46d}.settingRow{padding:12px 0;border-bottom:1px solid #293744}.settingRow:last-child{border-bottom:0}.settingDesc{color:#99aaba;font-size:12px;margin-top:5px}.soundTest{margin-left:8px}.settingsGrid{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:10px 22px}.settingsGrid .settingRow{min-width:0}.mapActions{margin-left:auto;display:flex;gap:7px}@media(max-width:760px){.settingsGrid{grid-template-columns:1fr}.mapActions{margin-left:0}}
  @media(max-width:1150px){#trafficBody{grid-template-columns:minmax(0,1fr)}#packetDetail{display:none}header{align-items:flex-start}.trafficTable{min-width:760px}}
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
  #viewMessages{background:#0b141a;min-height:0;position:relative;--message-font-size:13px}
  #messageHeader{padding:7px 12px;background:#17212b;border-bottom:1px solid #293744;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  #messageHeader .msgTitle{font-weight:800}.msgHint{font-size:11px;color:#91a4b3}.msgSpacer{flex:1}
  #messageList{flex:1;overflow:auto;padding:12px 14px;box-sizing:border-box;background:linear-gradient(rgba(11,20,26,.96),rgba(11,20,26,.96));scroll-behavior:smooth}
  .msgDay{text-align:center;margin:12px 0}.msgDay span{background:#182229;color:#b8c7d1;padding:5px 10px;border-radius:8px;font-size:11px;box-shadow:0 1px 2px rgba(0,0,0,.25)}
  .msgRow{display:flex;margin:4px 0}.msgRow.mine{justify-content:flex-end}.msgBubble{max-width:min(92%,1200px);min-width:120px;border-radius:9px;padding:6px 8px 5px;box-shadow:0 1px 2px rgba(0,0,0,.28);overflow-wrap:anywhere;position:relative}.msgRow.theirs .msgBubble{background:#202c33;border-top-left-radius:2px}.msgRow.mine .msgBubble{background:#005c4b;border-top-right-radius:2px}
  .msgSender{font-size:calc(var(--message-font-size,13px) - 2px);color:#70cfff;font-weight:800;margin-bottom:2px}.msgText{white-space:pre-wrap;font-size:var(--message-font-size,13px);line-height:1.35;padding-right:58px}.msgMeta{font-size:calc(var(--message-font-size,13px) - 3px);color:#b8c4ca;text-align:right;margin-top:-1px;white-space:nowrap}.msgStatus{font-size:12px;margin-left:4px;letter-spacing:-2px}.msgStatus.confirmed{color:#53bdeb}.msgStatus.failed{color:#ff8f8f}.msgTransport{font-size:9px;color:#8194a5;margin-left:5px}
  .msgNewMark{display:inline-block;background:#1f6f8b;color:white;border-radius:8px;padding:1px 5px;font-size:9px;margin-left:5px}
  #messageComposer{display:flex;gap:8px;align-items:flex-end;padding:8px 12px;background:#202c33;border-top:1px solid #293744;box-sizing:border-box}#messageInput{flex:1;min-height:38px;max-height:120px;resize:none;border-radius:18px;padding:9px 12px;font-family:inherit;font-size:var(--message-font-size,13px);line-height:1.25;background:#2a3942;color:#fff;caret-color:#fff}#messageInput::placeholder{color:#9fb0bf;opacity:1}#messageSend{width:42px;height:42px;border-radius:50%;font-size:20px;background:#00a884;border-color:#00a884;color:#fff;padding:0;display:flex;align-items:center;justify-content:center}.msgCounter{font-size:10px;color:#91a4b3;min-width:52px;text-align:right;padding-bottom:11px}.msgCounter.over{color:#ff8f8f;font-weight:800}
  #messagesNav.unread{animation:messagesUnread 1.15s ease-in-out infinite;border-color:#53bdeb;box-shadow:0 0 0 1px rgba(83,189,235,.25)}@keyframes messagesUnread{0%,100%{background:#233443;color:#edf3f8}50%{background:#0b6f81;color:#fff}}
  .unreadCount{display:none;background:#25d366;color:#07140c;border-radius:10px;min-width:18px;padding:1px 5px;margin-left:4px;font-size:10px;font-weight:900}.unread .unreadCount{display:inline-block}
  @media(max-width:650px){.msgBubble{max-width:88%}.msgText{padding-right:46px}#messageList{padding:10px 8px}#messageComposer{padding:8px}.msgCounter{display:none}}

  /* v1.20 - versão disponível e tema claro */
  .versionBadge{font-size:11px;font-weight:800;padding:5px 8px;border-radius:999px;white-space:nowrap;cursor:pointer}
  .versionBadge.checking{background:#263744;border-color:#405668;color:#cbd6df}.versionBadge.current{background:#174f37;border-color:#2f8b5e;color:#a9f5c5}.versionBadge.update{background:#6a4a13;border-color:#b98220;color:#ffe099}.versionBadge.error{background:#4c3940;border-color:#76535d;color:#f2bdca}
  .versionModalBackdrop{position:fixed;inset:0;z-index:5000;background:rgba(0,0,0,.58);display:none;align-items:center;justify-content:center;padding:18px;box-sizing:border-box}.versionModalBackdrop.open{display:flex}.versionModal{width:min(720px,96vw);max-height:min(78vh,760px);overflow:auto;background:#17212b;border:1px solid #405668;border-radius:12px;box-shadow:0 18px 55px rgba(0,0,0,.48);padding:18px;box-sizing:border-box}.versionModalHead{display:flex;align-items:center;gap:10px}.versionModalHead h2{margin:0;flex:1;font-size:18px}.versionClose{font-size:20px;line-height:1}.versionNotes{white-space:pre-wrap;background:#101820;border:1px solid #304353;border-radius:8px;padding:12px;font-size:12px;line-height:1.45;max-height:360px;overflow:auto}.versionActions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px}.versionActions a{display:inline-block;background:#234d63;color:#fff;border:1px solid #4c7e96;border-radius:6px;padding:6px 9px;text-decoration:none;font-weight:700}.updateCmd{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#101820;border:1px solid #304353;border-radius:6px;padding:6px 8px;font-size:12px}

  body[data-theme="light"]{background:#f2f5f7;color:#18232d}
  body[data-theme="light"] header{background:#ffffff;border-bottom-color:#cbd5dd}
  body[data-theme="light"] #summary,body[data-theme="light"] #trafficToolbar{background:#f5f7f9;border-color:#cbd5dd}
  body[data-theme="light"] #playback,body[data-theme="light"] #trafficStats{background:#edf2f5;border-color:#cbd5dd}
  body[data-theme="light"] .metric,body[data-theme="light"] .settingsCard,body[data-theme="light"] .dashCard,body[data-theme="light"] .dashSection,body[data-theme="light"] #packetDetail{background:#ffffff;border-color:#cbd5dd;color:#18232d}
  body[data-theme="light"] .dashSection h3,body[data-theme="light"] .trafficTable th,body[data-theme="light"] .dashTable th{background:#e9eef2;color:#263746;border-color:#cbd5dd}
  body[data-theme="light"] .trafficTable td,body[data-theme="light"] .dashTable td,body[data-theme="light"] .settingRow,body[data-theme="light"] .anomalyRow{border-color:#dce3e8}
  body[data-theme="light"] .trafficTable tbody tr:hover{background:#edf4f8}body[data-theme="light"] .trafficTable tbody tr.selected{background:#dcebf4}
  body[data-theme="light"] select,body[data-theme="light"] input,body[data-theme="light"] button,body[data-theme="light"] textarea{background:#ffffff;color:#17212b;border-color:#aebbc5}
  body[data-theme="light"] .navbtn.active{background:#e4b800;color:#101820;border-color:#b99700}
  body[data-theme="light"] label,body[data-theme="light"] #playStatus{color:#344654}
  body[data-theme="light"] .settingDesc,body[data-theme="light"] .methodNote,body[data-theme="light"] .emptyDetail,body[data-theme="light"] .emptyPanel{color:#627582}
  body[data-theme="light"] #viewHealth,body[data-theme="light"] #viewAnomalies{background:#f2f5f7}
  body[data-theme="light"] #viewMessages{background:#efeae2}
  body[data-theme="light"] #messageHeader{background:#ffffff;border-color:#cbd5dd;color:#18232d}
  body[data-theme="light"] #messageList{background:#efeae2}
  body[data-theme="light"] .msgRow.theirs .msgBubble{background:#ffffff;color:#17212b}.msgRow.mine .msgBubble{color:#ffffff}
  body[data-theme="light"] .msgRow.mine .msgBubble{background:#d9fdd3;color:#17212b}
  body[data-theme="light"] .msgMeta{color:#5f6f78}body[data-theme="light"] .msgSender{color:#087c9d}
  body[data-theme="light"] #messageComposer{background:#f0f2f5;border-color:#cbd5dd}body[data-theme="light"] #messageInput{background:#ffffff;color:#17212b;caret-color:#17212b}body[data-theme="light"] #messageInput::placeholder{color:#778894}
  body[data-theme="light"] .legend,body[data-theme="light"] .traceHud{background:rgba(255,255,255,.96);color:#17212b;border-color:#aebbc5}
  body[data-theme="light"] .short-label{background:rgba(255,255,255,.93);color:#17212b;border-color:#8ca0ae}
  body[data-theme="light"] .leaflet-popup-content-wrapper,body[data-theme="light"] .leaflet-popup-tip{background:#ffffff;color:#17212b}
  body[data-theme="light"] .versionModal{background:#ffffff;color:#17212b;border-color:#aebbc5}body[data-theme="light"] .versionNotes,body[data-theme="light"] .updateCmd{background:#f5f7f9;color:#17212b;border-color:#cbd5dd}

  /* v1.21 - tracklog e menções */
  #viewTracklog{min-height:0}.tracklogToolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;padding:8px 12px;background:#111c27;border-bottom:1px solid #293744}.tracklogSummary{font-size:11px;color:#9fb0bf;margin-left:auto}.tracklogMap{flex:1;min-height:260px}.tracklogLegend{background:rgba(23,33,43,.95);border:1px solid #405668;border-radius:7px;padding:7px 9px;color:#edf3f8;font-size:11px;max-width:280px}.tracklogLegend .trackNode{display:flex;align-items:center;gap:6px;margin:3px 0}.trackSwatch{width:20px;height:4px;border-radius:3px;display:inline-block}.trackPointPopup{font-size:12px;line-height:1.45}.trackCurrent{font-weight:800}
  #messageComposer{position:relative}.mentionSuggestions{position:absolute;left:12px;bottom:58px;width:min(560px,calc(100% - 88px));max-height:260px;overflow:auto;background:#17212b;border:1px solid #405668;border-radius:9px;box-shadow:0 10px 28px rgba(0,0,0,.42);z-index:1500;display:none}.mentionSuggestions.open{display:block}.mentionItem{display:grid;grid-template-columns:minmax(70px,100px) minmax(0,1fr);gap:8px;padding:8px 10px;cursor:pointer;border-bottom:1px solid #293744}.mentionItem:last-child{border-bottom:0}.mentionItem:hover,.mentionItem.active{background:#263b4d}.mentionShort{font-weight:900;color:#e9d46d}.mentionLong{font-weight:700;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.mentionId{font-size:10px;color:#8194a5}.chatMention{color:#70cfff;font-weight:800}.mentionHelp{font-size:10px;color:#91a4b3;margin-left:6px}
  body[data-theme="light"] .tracklogToolbar{background:#f5f7f9;border-color:#cbd5dd}body[data-theme="light"] .tracklogSummary{color:#627582}body[data-theme="light"] .tracklogLegend{background:rgba(255,255,255,.96);color:#17212b;border-color:#aebbc5}body[data-theme="light"] .mentionSuggestions{background:#ffffff;border-color:#aebbc5;color:#17212b}body[data-theme="light"] .mentionItem{border-color:#dce3e8}body[data-theme="light"] .mentionItem:hover,body[data-theme="light"] .mentionItem.active{background:#e7f1f7}body[data-theme="light"] .mentionShort{color:#8a6b00}body[data-theme="light"] .mentionId{color:#6f808c}body[data-theme="light"] .chatMention{color:#087c9d}

  /* v1.22 - internacionalização e ajuda */
  .languageControl{display:flex;align-items:center;gap:5px;font-size:11px;color:#cbd6df;white-space:nowrap}.languageControl select{font-size:11px;padding:4px 6px}.languageControl span{font-weight:700}
  #viewHelp{overflow:auto}.helpCard{max-width:1100px;margin:18px auto;background:#17212b;border:1px solid #304353;border-radius:10px;padding:22px;width:calc(100% - 36px);box-sizing:border-box;line-height:1.5}.helpCard h2{margin:0 0 8px}.helpCard h3{margin:22px 0 7px;color:#e9d46d}.helpCard h4{margin:15px 0 5px;color:#9fc6e4}.helpCard p,.helpCard li{font-size:13px}.helpCard ul{padding-left:22px}.helpCard code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#101820;border:1px solid #304353;border-radius:4px;padding:1px 4px}.helpCode{white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#101820;border:1px solid #304353;border-radius:7px;padding:10px 12px;font-size:12px;overflow:auto}.helpCallout{background:#132a38;border-left:4px solid #3a8fbd;border-radius:6px;padding:10px 12px;margin:10px 0;font-size:12px}.helpWarn{background:#382d13;border-left-color:#d6a700}.helpGrid{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:10px 18px}.helpMini{background:#111a24;border:1px solid #293744;border-radius:8px;padding:11px}.helpMini b{display:block;margin-bottom:4px}.i18nNoTranslate{unicode-bidi:plaintext}
  body[data-theme="light"] .languageControl{color:#344654}body[data-theme="light"] .helpCard{background:#fff;border-color:#cbd5dd;color:#18232d}body[data-theme="light"] .helpCard h3{color:#7a6500}body[data-theme="light"] .helpCard h4{color:#245f7c}body[data-theme="light"] .helpMini{background:#f5f7f9;border-color:#dce3e8}body[data-theme="light"] .helpCode,body[data-theme="light"] .helpCard code{background:#f5f7f9;border-color:#cbd5dd;color:#17212b}body[data-theme="light"] .helpCallout{background:#e8f3f8}body[data-theme="light"] .helpWarn{background:#fff6d9}
  @media(max-width:780px){.helpGrid{grid-template-columns:1fr}.helpCard{width:calc(100% - 20px);margin:10px auto;padding:15px}}

  /* v1.23 - conforto visual, filtros e atualização automática */
  #viewMessages{--message-font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;--message-font-weight:400;--message-font-style:normal;--message-text-decoration:none;--message-line-height:1.35;--message-row-gap:4px}
  .msgRow{margin-top:var(--message-row-gap,4px)!important;margin-bottom:var(--message-row-gap,4px)!important}
  .msgText{font-family:var(--message-font-family)!important;font-weight:var(--message-font-weight)!important;font-style:var(--message-font-style)!important;text-decoration:var(--message-text-decoration)!important;line-height:var(--message-line-height)!important}
  #messageInput{font-family:var(--message-font-family)!important;font-weight:var(--message-font-weight)!important;font-style:var(--message-font-style)!important;text-decoration:var(--message-text-decoration)!important;line-height:var(--message-line-height)!important}
  .styleChecks{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:7px}.styleChecks label{font-size:12px}
  .anomalyFilter{display:flex;gap:5px;align-items:center}
  .updateStatusBox{background:#111a24;border:1px solid #293744;border-radius:8px;padding:10px 12px;font-size:12px;line-height:1.5;min-height:48px}.updateStatusBox b{color:#dbe6ee}
  .updateState-running,.updateState-pending{color:#ffd166;font-weight:800}.updateState-success,.updateState-no_change{color:#7af0ad;font-weight:800}.updateState-failed,.updateState-rolled_back{color:#ff9c9c;font-weight:800}
  body[data-theme="light"] .updateStatusBox{background:#f5f7f9;border-color:#dce3e8;color:#263746}body[data-theme="light"] .updateStatusBox b{color:#18232d}
  .whatsNewList{white-space:pre-wrap;line-height:1.55}.whatsNewList .wnItem{margin:0 0 7px}

</style>
</head>
<body>
<div id="flowToast" title="Clique para abrir o mapa"></div>
<div id="versionModalBackdrop" class="versionModalBackdrop" role="dialog" aria-modal="true" aria-labelledby="versionModalTitle">
  <div class="versionModal">
    <div class="versionModalHead"><h2 id="versionModalTitle">Versão do Traffic Analyzer</h2><button id="versionModalClose" class="versionClose" type="button" title="Fechar">×</button></div>
    <p id="versionModalSummary" class="settingDesc">Consultando a versão publicada…</p>
    <div id="versionNotes" class="versionNotes">Sem informações carregadas.</div>
    <div class="versionActions"><a id="versionReleaseLink" href="https://github.com/alexpmr/traffic-analyzer/releases/latest" target="_blank" rel="noopener noreferrer">Ver Release no GitHub</a><button id="versionContinue" type="button">Continuar</button></div>
  </div>
</div>
<div id="whatsNewBackdrop" class="versionModalBackdrop" role="dialog" aria-modal="true" aria-labelledby="whatsNewTitle">
  <div class="versionModal">
    <div class="versionModalHead"><h2 id="whatsNewTitle">Traffic Analyzer atualizado</h2><button id="whatsNewClose" class="versionClose" type="button" title="Fechar">×</button></div>
    <p id="whatsNewSummary" class="settingDesc"></p>
    <div id="whatsNewNotes" class="versionNotes whatsNewList"></div>
    <div class="versionActions"><a id="whatsNewReleaseLink" href="https://github.com/alexpmr/traffic-analyzer/releases/latest" target="_blank" rel="noopener noreferrer">Ver Release no GitHub</a><button id="whatsNewOk" type="button">Fechar</button></div>
  </div>
</div>
<div id="app">
<header>
  <h1>__DISPLAY_TITLE__</h1>
  <label class="languageControl"><span>Idioma:</span><select id="uiLanguage" aria-label="Idioma da interface"><option value="pt-BR" selected>🇧🇷 Português</option><option value="en">🇺🇸 English</option></select></label>
  <button id="versionBadge" class="versionBadge checking" type="button" title="Verificar versão">v__APP_VERSION__ · verificando…</button>
  <div id="nav">
    <button class="navbtn active" data-view="map">Mapa</button>
    <button class="navbtn" data-view="tracklog">Tracklog</button>
    <button class="navbtn" data-view="traffic">Tráfego</button>
    <button class="navbtn" id="messagesNav" data-view="messages">Mensagens <span id="messagesUnreadCount" class="unreadCount">0</span></button>
    <button class="navbtn" data-view="health">Saúde da Rede</button>
    <button class="navbtn" data-view="anomalies">Anomalias</button>
    <button class="navbtn" data-view="settings">Configurações</button>
    <button class="navbtn" data-view="help">Ajuda</button>
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
  <button id="playTrace" title="Pausar animações ao vivo">⏸</button>
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
<section id="viewTracklog" class="view">
  <div class="tracklogToolbar">
    <b>Tracklog de estações móveis</b>
    <label>Período: <select id="tracklogHours"><option value="1">1 h</option><option value="6">6 h</option><option value="24" selected>24 h</option><option value="168">7 dias</option><option value="720">30 dias</option></select></label>
    <label>Nó: <select id="tracklogNode"><option value="all">Todos com mobilidade observada</option></select></label>
    <button id="tracklogReload">Atualizar</button>
    <button id="tracklogFit">Enquadrar</button>
    <span id="tracklogSummary" class="tracklogSummary">Aguardando dados…</span>
  </div>
  <div id="tracklogMap" class="tracklogMap"></div>
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
        <thead><tr><th>Hora</th><th>DIR</th><th>Origem</th><th>Destino</th><th>Tipo</th><th>SNR</th><th>RSSI</th><th>Hops</th></tr></thead>
        <tbody id="trafficRows"><tr><td colspan="8">Carregando pacotes...</td></tr></tbody>
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
    <div id="mentionSuggestions" class="mentionSuggestions"></div>
    <textarea id="messageInput" rows="1" placeholder="Digite uma mensagem"></textarea><span id="messageCounter" class="msgCounter">0 B</span><span class="mentionHelp">Use @ para localizar um nó; o @ é removido antes da transmissão.</span><button id="messageSend" title="Enviar">➤</button>
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
    <div class="dashboardToolbar"><h2>Detecção de Anomalias</h2><span id="anomalyUpdated" class="settingDesc"></span><label class="anomalyFilter">Severidade: <select id="anomalySeverity"><option value="all" selected>Todas</option><option value="critical">Crítica</option><option value="warning">Atenção</option><option value="info">Informativa</option></select></label><button id="anomalyReload">Reanalisar</button></div>
    <div id="anomalyCards" class="dashGrid"><div class="dashCard"><div class="label">Analisando...</div></div></div>
    <div class="dashSection"><h3>Ocorrências detectadas</h3><div id="anomalyList"></div></div>
    <div class="dashSection"><h3>Como interpretar</h3><div class="dashSectionBody methodNote">As anomalias são heurísticas: silêncio prolongado, degradação de SNR, mudança relevante na quantidade de hops e traceroute assimétrico. Elas servem para priorizar investigação e não constituem prova isolada de defeito, indisponibilidade ou causalidade.</div></div>
  </div>
</section>

<section id="viewSettings" class="view">
  <div class="settingsCard">
    <h2>Configurações do Traffic Analyzer</h2>

    <h3>Aparência</h3>
    <div class="settingsGrid">
      <div class="settingRow">
        <label>Tema da interface: <select id="uiTheme"><option value="dark" selected>Escuro (padrão)</option><option value="light">Claro</option></select></label>
        <div class="settingDesc">Altera a interface inteira. O mapa-base continua sendo configurado separadamente.</div>
      </div>
    </div>

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
        <label>Espessura das linhas: <input id="lineWidth" type="range" min="1" max="8" step="1" value="3" style="width:150px;vertical-align:middle"> <span id="lineWidthValue">3 px</span></label>
        <div class="settingDesc">Ajusta apenas a visualização dos enlaces; não altera a topologia nem os cálculos.</div>
        <button id="lineStyleReset" type="button" style="margin-top:7px">Restaurar padrão</button>
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

    <h3>Temas sonoros</h3>
    <div class="settingsGrid">
      <div class="settingRow">
        <label><input id="soundEnabled" type="checkbox"> Ativar sonificação da malha</label>
        <div class="settingDesc">Os sons acompanham eventos realmente observados. O Traffic Analyzer não inventa retransmissões para produzir efeitos.</div>
      </div>
      <div class="settingRow">
        <label>Tema: <select id="soundTheme"><option value="pinball70">Fliperama anos 70</option><option value="formal" selected>Formal</option><option value="radio">Rádio / Telecom</option><option value="silent">Silencioso</option></select></label>
        <button id="soundTest" class="soundTest" type="button">Testar tema</button>
        <div class="settingDesc">Os efeitos são sintetizados localmente pelo navegador; nenhum arquivo de áudio é baixado.</div>
      </div>
      <div class="settingRow">
        <label>Volume: <input id="soundVolume" type="range" min="0" max="100" step="5" value="35" style="width:180px;vertical-align:middle"> <span id="soundVolumeValue">35%</span></label><br>
        <label>Densidade sonora: <select id="soundDensity"><option value="low">Baixa</option><option value="normal" selected>Normal</option><option value="high">Alta</option></select></label>
        <div class="settingDesc">Em densidade baixa, parte dos ricochetes é suprimida em malhas muito movimentadas. Normal e Alta preservam mais eventos observados.</div>
      </div>
      <div class="settingRow">
        <label>Intervalo mínimo: <input id="soundMinInterval" type="range" min="40" max="800" step="20" value="120" style="width:150px;vertical-align:middle"> <span id="soundMinIntervalValue">120 ms</span></label><br>
        <label>Máximo simultâneo: <input id="soundMaxVoices" type="number" min="1" max="8" step="1" value="3" style="width:60px"> sons</label>
        <div class="settingDesc">Limita sobreposição e evita uma sequência de efeitos excessivamente densa.</div>
      </div>
      <div class="settingRow">
        <label><input id="soundRoutingEnabled" type="checkbox" checked> Sons de roteamento e traceroute</label><br>
        <label><input id="soundMessagesEnabled" type="checkbox" checked> Sons de mensagens</label><br>
        <label><input id="soundAlertsEnabled" type="checkbox" checked> Sons de alertas e falhas</label>
      </div>
      <div class="settingRow">
        <label><input id="soundStereoEnabled" type="checkbox"> Estéreo espacial</label>
        <div class="settingDesc">Quando ativado, eventos visíveis no mapa recebem leve deslocamento esquerda/direita conforme a posição. Desligado por padrão.</div>
      </div>
      <div class="settingRow">
        <b>Fliperama anos 70</b>
        <div class="settingDesc">Origem do pacote: lançador mecânico. Retransmissor observado: ricochete metálico. Destino/ACK: alvo e pontuação. Falha: efeito de bola perdida.</div>
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

    <h3>Mensagens</h3>
    <div class="settingsGrid">
      <div class="settingRow">
        <label>Tamanho da fonte:
          <input id="messageFontSize" type="range" min="10" max="20" step="1" value="13">
          <span id="messageFontSizeValue">13 px</span>
        </label>
        <div class="settingDesc">Ajusta o tamanho do texto do chat, do remetente, do horário e do campo de composição. A preferência fica salva neste navegador.</div>
      </div>
      <div class="settingRow">
        <label>Fonte: <select id="messageFontFamily"><option value="system" selected>Sistema</option><option value="arial">Arial / Helvetica</option><option value="verdana">Verdana</option><option value="tahoma">Tahoma</option><option value="georgia">Georgia</option><option value="mono">Monoespaçada</option></select></label>
        <div class="styleChecks"><label><input id="messageBold" type="checkbox"> <b>Negrito</b></label><label><input id="messageItalic" type="checkbox"> <i>Itálico</i></label><label><input id="messageUnderline" type="checkbox"> <u>Sublinhado</u></label></div>
        <div class="settingDesc">Formatação somente visual. Nenhum marcador de estilo é enviado pela malha.</div>
      </div>
      <div class="settingRow">
        <label>Altura da linha: <input id="messageLineHeight" type="range" min="1.10" max="2.00" step="0.05" value="1.35" style="width:150px;vertical-align:middle"> <span id="messageLineHeightValue">1,35</span></label><br>
        <label>Espaço entre mensagens: <input id="messageRowGap" type="range" min="1" max="14" step="1" value="4" style="width:150px;vertical-align:middle"> <span id="messageRowGapValue">4 px</span></label>
      </div>
      <div class="settingRow">
        <b>Uso da tela</b>
        <div class="settingDesc">A tela de Mensagens usa praticamente toda a largura e altura disponíveis, preservando apenas margens mínimas para leitura.</div>
      </div>
    </div>

    <h3>Atualizações</h3>
    <div class="settingsGrid">
      <div class="settingRow">
        <label><input id="autoUpdateEnabled" type="checkbox"> Atualizar automaticamente ao detectar nova versão estável</label>
        <div class="settingDesc">A aplicação apenas cria uma solicitação. Um serviço systemd dedicado executa o update como root, sem conceder privilégios genéricos ao processo web.</div>
      </div>
      <div class="settingRow">
        <label><input id="rollbackEnabled" type="checkbox" checked> Rollback automático se a nova versão não ficar saudável</label>
        <div class="settingDesc">Em caso de falha, restaura a aplicação e os units do systemd preservados antes da atualização.</div>
      </div>
      <div class="settingRow">
        <button id="updateNow" type="button">Atualizar agora</button>
        <div class="settingDesc">Instala somente a Latest Release estável publicada no repositório oficial.</div>
      </div>
      <div class="settingRow">
        <div id="updateStatusBox" class="updateStatusBox">Carregando status de atualização...</div>
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
<section id="viewHelp" class="view">
  <div id="helpContent" class="helpCard"></div>
</section>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
 integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>
<script>
const LANGUAGE_KEY='trafficAnalyzerLanguageV122';
let currentLang=localStorage.getItem(LANGUAGE_KEY)==='en'?'en':'pt-BR';
function uiLocale(){return currentLang==='en'?'en-US':'pt-BR';}

const I18N_PAIRS=[
  ['Mapa','Map'],['Tráfego','Traffic'],['Mensagens','Messages'],['Saúde da Rede','Network Health'],['Anomalias','Anomalies'],['Configurações','Settings'],['Ajuda','Help'],
  ['Idioma:','Language:'],['Idioma da interface','Interface language'],['Português','Portuguese'],
  ['Reprodução:','Playback:'],['Histórico','History'],['Ao vivo','Live'],['Velocidade:','Speed:'],['Enquadrar','Fit'],['Atualizar','Refresh'],
  ['Traceroute anterior','Previous traceroute'],['Próximo traceroute','Next traceroute'],['Pausar animações ao vivo','Pause live animations'],['Retomar animações ao vivo','Resume live animations'],['Reproduzir/retomar histórico','Play/resume history'],['Pausar histórico','Pause history'],
  ['Tráfego ao vivo','Live traffic'],['Direção:','Direction:'],['Todos','All'],['Tipo:','Type:'],['Mensagem','Message'],['Buscar:','Search:'],['Pausar','Pause'],['Retomar','Resume'],['Baixar dump JSON (.zip)','Download JSON dump (.zip)'],
  ['Baixa todo o histórico persistente em traffic.json dentro de um ZIP','Downloads the entire persistent history as traffic.json inside a ZIP'],['Hora','Time'],['DIR','DIR'],['Origem','Source'],['Destino','Destination'],['Tipo','Type'],['Hops','Hops'],
  ['Clique em um pacote para ver os detalhes.','Click a packet to view details.'],['Clique para ver o payload formatado','Click to view the formatted payload'],['Nenhum pacote corresponde ao filtro.','No packet matches the filter.'],
  ['Tracklog de estações móveis','Mobile station tracklog'],['Período:','Period:'],['Nó:','Node:'],['Todos com mobilidade observada','All with observed mobility'],['Aguardando dados…','Waiting for data…'],['Sem trajetos carregados','No tracks loaded'],['posição mais recente do período','latest position in the period'],
  ['Canal primário','Primary channel'],['Canal 0 - mensagens de broadcast','Channel 0 - broadcast messages'],['Carregando...','Loading...'],['Carregar anteriores','Load older'],['Carregar mais mensagens antigas','Load older messages'],['Consultar novas mensagens agora','Check for new messages now'],['Digite uma mensagem','Type a message'],['Digite @ para mencionar um nó','Type @ to mention a node'],['Enviar','Send'],['nova','new'],['Sem mensagens não lidas','No unread messages'],['Nenhuma mensagem encontrada no canal primário.','No messages found on the primary channel.'],
  ['Saúde da Rede','Network Health'],['Atividade dos últimos 7 dias','Activity over the last 7 days'],['Traceroutes e roteamento','Traceroutes and routing'],['Interações por chat no canal primário','Chat interactions on the primary channel'],['Nós que merecem atenção','Nodes that need attention'],['Último tráfego','Last traffic'],['Tempo sem ouvir','Time since heard'],['Pacotes 7d','Packets 7d'],['SNR médio 7d','Average SNR 7d'],['Reanalisar','Reanalyze'],
  ['Os indicadores usam o histórico persistente do Traffic Analyzer e a topologia observada pelo MeshMonitor. O ranking de chat conta interações acumuladas registradas no canal primário. Ausência de tráfego não prova falha física; pode representar um nó silencioso, desligado ou fora do alcance da fonte.','Indicators use the Traffic Analyzer persistent history and the topology observed by MeshMonitor. The chat ranking counts accumulated interactions recorded on the primary channel. Lack of traffic does not prove a physical failure; it may represent a silent node, a powered-off node, or a node outside the source range.'],
  ['Detecção de Anomalias','Anomaly Detection'],['Ocorrências detectadas','Detected occurrences'],['Como interpretar','How to interpret'],['As anomalias são heurísticas: silêncio prolongado, degradação de SNR, mudança relevante na quantidade de hops e traceroute assimétrico. Elas servem para priorizar investigação e não constituem prova isolada de defeito, indisponibilidade ou causalidade.','Anomalies are heuristics: prolonged silence, SNR degradation, significant hop-count changes, and asymmetric traceroutes. They help prioritize investigation and are not standalone proof of failure, outage, or causality.'],
  ['Configurações do Traffic Analyzer','Traffic Analyzer Settings'],['Aparência','Appearance'],['Tema da interface:','Interface theme:'],['Escuro (padrão)','Dark (default)'],['Escuro','Dark'],['Claro','Light'],['Altera a interface inteira. O mapa-base continua sendo configurado separadamente.','Changes the entire interface. The base map remains configured separately.'],
  ['Mapa e topologia','Map and topology'],['Janela:','Window:'],['Filtra enlaces e traceroutes pela idade da observação.','Filters links and traceroutes by observation age.'],['Mínimo de observações:','Minimum observations:'],['Oculta enlaces com menos observações que o valor escolhido.','Hides links with fewer observations than the selected value.'],['Mapa base:','Base map:'],['Ruas (OSM)','Streets (OSM)'],['Topográfico','Topographic'],['Satélite','Satellite'],['Brilho:','Brightness:'],['Cor das linhas:','Line color:'],['Mostrar linhas','Show lines'],['Mostrar nós','Show nodes'],['Mapa de calor','Heat map'],['Mostrar nomes curtos','Show short names'],['Mostrar somente identificados','Show identified only'],['Auto Zoom durante traceroutes','Auto Zoom during traceroutes'],['Enquadra automaticamente todos os nós envolvidos nas animações de traceroute. Se houver animações simultâneas, usa a área combinada. Cinco segundos após a última terminar, retorna ao enquadramento anterior.','Automatically fits all nodes involved in traceroute animations. If animations overlap, it uses the combined area. Five seconds after the last one finishes, it returns to the previous framing.'],
  ['Notificações sonoras','Sound notifications'],['Som no início de uma nova viagem de pacote','Sound at the start of a new packet journey'],['O som toca uma única vez quando uma nova viagem de pacote é observada. Cópias/retransmissões do mesmo packet_id não geram novos sons.','The sound plays once when a new packet journey is observed. Copies/retransmissions of the same packet_id do not generate new sounds.'],['Som:','Sound:'],['Plim','Chime'],['Campainha','Bell'],['Duplo','Double'],['Suave','Soft'],['Testar som','Test sound'],['Todos os sons são sintetizados localmente; nenhum arquivo de áudio é baixado.','All sounds are synthesized locally; no audio file is downloaded.'],['Volume:','Volume:'],['A preferência fica salva neste navegador. O primeiro clique libera o Web Audio quando exigido pelo navegador.','The preference is saved in this browser. The first click enables Web Audio when required by the browser.'],
  ['Atividade em tempo real no mapa','Real-time map activity'],['Animar atividade dos nós','Animate node activity'],['Realçar origem/resposta','Highlight source/response'],['Realçar retransmissor observado','Highlight observed relay'],['Cada atividade observada recebe um pulso visual no mapa. Só são destacados nós que podem ser identificados com segurança.','Each observed activity gets a visual pulse on the map. Only nodes that can be identified safely are highlighted.'],['Duração do realce:','Highlight duration:'],['Origem/resposta usa pulso azul/roxo; relay observado usa pulso amarelo. O Traffic Analyzer não inventa relays intermediários.','Source/response uses a blue/purple pulse; the observed relay uses a yellow pulse. Traffic Analyzer does not invent intermediate relays.'],
  ['Tamanho da fonte:','Font size:'],['Ajusta o tamanho do texto do chat, do remetente, do horário e do campo de composição. A preferência fica salva neste navegador.','Adjusts chat text, sender, timestamp, and composer font sizes. The preference is saved in this browser.'],['Uso da tela','Screen usage'],['A tela de Mensagens usa praticamente toda a largura e altura disponíveis, preservando apenas margens mínimas para leitura.','The Messages screen uses nearly all available width and height while preserving minimal reading margins.'],
  ['Fluxos e privacidade','Flows and privacy'],['Mostrar fluxo de NodeInfo no mapa','Show NodeInfo flow on the map'],['O mapa liga origem e destino. A animação por hops só usa rota observada quando existe traceroute completo compatível; sem evidência suficiente, nenhum hop é inventado.','The map connects source and destination. Hop-by-hop animation only uses an observed route when a compatible complete traceroute exists; without sufficient evidence, no hop is invented.'],['Conteúdo dos pacotes','Packet content'],['Mensagens TEXT_MESSAGE em broadcast mostram o payload no detalhe. Mensagens diretas continuam ocultas por padrão. Payloads e dados técnicos são apresentados com rótulos amigáveis; o JSON bruto fica disponível apenas como diagnóstico secundário.','Broadcast TEXT_MESSAGE packets show their payload in details. Direct messages remain hidden by default. Payloads and technical data are shown with friendly labels; raw JSON remains available only as secondary diagnostics.'],['Segurança','Security'],['O token mm_v1 permanece no processo servidor e não é enviado ao navegador.','The mm_v1 token remains in the server process and is never sent to the browser.'],
  ['Versão do Traffic Analyzer','Traffic Analyzer Version'],['Consultando a versão publicada…','Checking the published version…'],['Sem informações carregadas.','No information loaded.'],['Ver Release no GitHub','View Release on GitHub'],['Continuar','Continue'],['Fechar','Close'],['Verificar versão','Check version'],['Esta é a versão mais recente publicada','This is the latest published version'],['Nova versão disponível - clique para ver as novidades','New version available - click to see what is new'],['Não foi possível verificar a versão mais recente','Could not check the latest version'],['Não há notas de versão disponíveis.','No release notes are available.'],
  ['Último tráfego','Last traffic'],['até 2 h','up to 2 h'],['2 a 24 h','2 to 24 h'],['mais de 24 h','more than 24 h'],['sem registro','no record'],['Sem tráfego registrado','No traffic recorded'],['Tráfego nas últimas 2 h','Traffic in the last 2 h'],['Tráfego entre 2 e 24 h','Traffic between 2 and 24 h'],['Tráfego há mais de 24 h','Traffic more than 24 h ago'],
  ['enlaces no filtro','links in filter'],['nós no mapa','nodes on map'],['identificados','identified'],['traceroutes no histórico','traceroutes in history'],['círculos visíveis','visible circles'],['Calor = atividade de roteamento observada','Heat = observed routing activity'],['armazenados no MM','stored in MM'],['carregados','loaded'],['último minuto','last minute'],['no filtro','in filter'],
  ['Observações:','Observations:'],['Ida:','Outbound:'],['Volta:','Return:'],['SNR médio:','Average SNR:'],['Faixa SNR:','SNR range:'],['Última observação:','Last observation:'],['canal:','channel:'],['Estado:','State:'],['Posição:','Position:'],['Último tráfego:','Last traffic:'],['Situação:','Status:'],['Public key:','Public key:'],['Short name:','Short name:'],['sim','yes'],['não','no'],
  ['Dados técnicos','Technical data'],['Nenhum dado técnico adicional disponível.','No additional technical data available.'],['Ver JSON bruto','View raw JSON'],['Mostrar fluxo','Show flow'],['Criptografado','Encrypted'],['Canal','Channel'],['Nome','Name'],['Nome curto','Short name'],['Chave pública','Public key'],['Licenciado','Licensed'],['Nó','Node'],['Última recepção','Last reception'],['Vizinhos','Neighbors'],['Rota','Route'],['Rota de volta','Return route'],['Erro de roteamento','Routing error'],['Motivo','Reason'],['ID da solicitação','Request ID'],['ID da resposta','Reply ID'],['ID do pacote','Packet ID'],['Tipo de telemetria','Telemetry type'],['Solicita resposta','Requests response'],['Solicita ACK','Requests ACK'],['Tipo de pacote','Packet type'],['Transporte','Transport'],['Recebido em','Received at'],['Prioridade','Priority'],['Métricas do dispositivo','Device metrics'],['Métricas ambientais','Environmental metrics'],['Estatísticas locais','Local statistics'],['Métricas de energia','Power metrics'],['Qualidade do ar','Air quality'],['Bateria','Battery'],['Tensão','Voltage'],['Utilização do canal','Channel utilization'],['Horário','Time'],['Temperatura','Temperature'],['Umidade','Humidity'],['Pressão','Pressure'],['Resistência do gás','Gas resistance'],['Corrente','Current'],['Luminosidade','Illuminance'],
  ['Calculando indicadores','Calculating indicators'],['Nós ativos - 2 h','Active nodes - 2 h'],['nós conhecidos','known nodes'],['Nós ativos - 24 h','Active nodes - 24 h'],['sem tráfego > 24 h','no traffic > 24 h'],['Pacotes - 24 h','Packets - 24 h'],['Enlaces observados','Observed links'],['vistos nas últimas 24 h','seen in the last 24 h'],['histórico carregado','loaded history'],['Com ida e volta','With outbound and return'],['completos nos 2 sentidos','complete in both directions'],['Mediana de hops','Median hops'],['por perna observada','per observed leg'],['Sem registro','No record'],['nós sem timestamp confiável','nodes without a reliable timestamp'],['Idas observadas','Observed outbound legs'],['Voltas observadas','Observed return legs'],['Traceroutes incompletos','Incomplete traceroutes'],['Média de hops','Average hops'],['Nenhuma interação de chat registrada no canal primário.','No chat interaction recorded on the primary channel.'],['Nenhum nó requer atenção pelo critério atual.','No node requires attention under the current criterion.'],['Não foi possível calcular','Could not calculate'],
  ['Crítica','Critical'],['Críticas','Critical anomalies'],['Atenção','Warning'],['Informativa','Informational'],['Informativas','Informational anomalies'],['Nenhuma anomalia foi detectada pelos critérios atuais.','No anomaly was detected by the current criteria.'],['Erro ao analisar:','Analysis error:'],['Nó silencioso há mais de 24 h','Node silent for more than 24 h'],['Nó silencioso há mais de 7 dias','Node silent for more than 7 days'],['Não há tráfego recente deste nó no histórico disponível.','There is no recent traffic from this node in the available history.'],['O nó ultrapassou a janela de 24 horas sem tráfego observado.','The node exceeded the 24-hour window without observed traffic.'],['Queda de SNR no enlace','SNR drop on link'],['Mudança relevante de hops','Significant hop-count change'],['Traceroute assimétrico','Asymmetric traceroute'],['A observação mais recente contém apenas um dos sentidos do traceroute.','The latest observation contains only one direction of the traceroute.'],
  ['AO VIVO','LIVE'],['● PAUSADO','● PAUSED'],['ANIMAÇÃO PAUSADA','ANIMATION PAUSED'],['conectando…','connecting…'],['IDA','OUTBOUND'],['VOLTA','RETURN'],['Total ida + volta:','Total outbound + return:'],['sem percurso completo','no complete path'],['Histórico pausado.','History paused.'],['Histórico: nenhum traceroute completamente mapeável no filtro atual.','History: no fully mappable traceroute in the current filter.'],['A atualização excedeu 90 segundos.','The update exceeded 90 seconds.'],['Atualizando...','Updating...'],['Atualizado ✓','Updated ✓'],['Erro','Error'],
  ['● AO VIVO','● LIVE'],['Carregando mensagens...','Loading messages...'],['Carregando pacotes...','Loading packets...'],['Histórico pronto.','History ready.'],['Interações','Interactions'],['Clique para abrir o mapa','Click to open the map'],['nó, ID, tipo...','node, ID, type...'],['data não informada','date not provided'],
  ['Mensagem muito longa. Reduza o texto para até aproximadamente 600 bytes.','Message too long. Reduce the text to approximately 600 bytes or less.'],['Enviando...','Sending...'],['Mensagem enviada ao MeshMonitor','Message sent to MeshMonitor'],['Limite de 1.500 mensagens já carregado.','The 1,500-message limit is already loaded.'],['Nenhuma mensagem anterior adicional disponível.','No additional older messages are available.'],['Nó desconhecido','Unknown node'],['pedido provável','probable request'],
  ['Linha lógica exibida; procurando um traceroute próximo no tempo para não inventar hops.','Logical line displayed; looking for a nearby traceroute in time so no hops are invented.'],['Sem coordenadas suficientes para desenhar o fluxo no mapa.','Not enough coordinates to draw the flow on the map.'],['O pacote comum não carrega a cadeia completa de relays. A linha tracejada é apenas origem/destino; nenhum hop foi inventado.','A regular packet does not carry the complete relay chain. The dashed line is only source/destination; no hop was invented.'],['caminho intermediário ainda não observado','intermediate path not observed yet'],
  ['Nenhuma mobilidade observada neste período.','No mobility observed in this period.'],['Hoje','Today'],['Ontem','Yesterday'],['há poucos segundos','a few seconds ago'],['[conteúdo oculto]','[content hidden]'],
  ['Severidade:','Severity:'],['Todas','All'],['Sistema','System'],['Monoespaçada','Monospace'],['Fonte:','Font:'],['Negrito','Bold'],['Itálico','Italic'],['Sublinhado','Underline'],
  ['Altura da linha:','Line height:'],['Espaço entre mensagens:','Space between messages:'],['Formatação somente visual. Nenhum marcador de estilo é enviado pela malha.','Visual formatting only. No style marker is transmitted over the mesh.'],
  ['Espessura das linhas:','Line thickness:'],['Ajusta apenas a visualização dos enlaces; não altera a topologia nem os cálculos.','Only changes link rendering; it does not change topology or calculations.'],['Restaurar padrão','Restore default'],
  ['Atualizações','Updates'],['Atualizar automaticamente ao detectar nova versão estável','Automatically update when a new stable version is detected'],['A aplicação apenas cria uma solicitação. Um serviço systemd dedicado executa o update como root, sem conceder privilégios genéricos ao processo web.','The application only creates a request. A dedicated systemd service performs the update as root without granting generic privileges to the web process.'],
  ['Rollback automático se a nova versão não ficar saudável','Automatic rollback if the new version does not become healthy'],['Em caso de falha, restaura a aplicação e os units do systemd preservados antes da atualização.','On failure, restores the application and systemd units saved before the update.'],['Atualizar agora','Update now'],['Instala somente a Latest Release estável publicada no repositório oficial.','Installs only the stable Latest Release published in the official repository.'],['Carregando status de atualização...','Loading update status...'],
  ['Traffic Analyzer atualizado','Traffic Analyzer updated'],['Versão anterior:','Previous version:'],['Versão atual:','Current version:'],['Última atualização:','Last update:'],['Destino','Target'],
  ['Pendente','Pending'],['Atualizando','Updating'],['Concluída','Completed'],['Falhou','Failed'],['Rollback executado','Rollback completed'],['Nunca','Never'],['Status:','Status:'],
  ['Solicitação de atualização enviada.','Update request sent.'],['Nenhuma atualização disponível.','No update is available.'],
  ['Temas sonoros','Sound themes'],['Ativar sonificação da malha','Enable mesh sonification'],['Os sons acompanham eventos realmente observados. O Traffic Analyzer não inventa retransmissões para produzir efeitos.','Sounds follow events that were actually observed. Traffic Analyzer does not invent relays to produce effects.'],
  ['Tema:','Theme:'],['Fliperama anos 70','1970s Pinball'],['Formal','Formal'],['Rádio / Telecom','Radio / Telecom'],['Silencioso','Silent'],['Testar tema','Test theme'],
  ['Os efeitos são sintetizados localmente pelo navegador; nenhum arquivo de áudio é baixado.','Effects are synthesized locally by the browser; no audio file is downloaded.'],['Densidade sonora:','Sound density:'],['Baixa','Low'],['Normal','Normal'],['Alta','High'],
  ['Em densidade baixa, parte dos ricochetes é suprimida em malhas muito movimentadas. Normal e Alta preservam mais eventos observados.','At low density, some ricochets are suppressed on very busy meshes. Normal and High preserve more observed events.'],
  ['Intervalo mínimo:','Minimum interval:'],['Máximo simultâneo:','Maximum simultaneous:'],['sons','sounds'],['Limita sobreposição e evita uma sequência de efeitos excessivamente densa.','Limits overlap and prevents an excessively dense sequence of effects.'],
  ['Sons de roteamento e traceroute','Routing and traceroute sounds'],['Sons de mensagens','Message sounds'],['Sons de alertas e falhas','Alert and failure sounds'],['Estéreo espacial','Spatial stereo'],
  ['Quando ativado, eventos visíveis no mapa recebem leve deslocamento esquerda/direita conforme a posição. Desligado por padrão.','When enabled, visible map events receive slight left/right panning based on position. Off by default.'],
  ['Origem do pacote: lançador mecânico. Retransmissor observado: ricochete metálico. Destino/ACK: alvo e pontuação. Falha: efeito de bola perdida.','Packet source: mechanical plunger. Observed relay: metallic ricochet. Destination/ACK: target and scoring. Failure: lost-ball effect.'],
  ['Use @ para localizar um nó; o @ é removido antes da transmissão.','Use @ to find a node; @ is removed before transmission.'],
  ['Adiciona bandeiras do Brasil e dos Estados Unidos ao seletor de idioma.','Adds Brazil and United States flags to the language selector.'],
  ['Remove o caractere @ das menções antes de transmitir a mensagem, preservando apenas o nome do nó.','Removes the @ character from mentions before transmitting the message, preserving only the node name.'],
  ['Adiciona controles visuais de fonte, negrito, itálico, sublinhado, altura de linha e espaçamento entre mensagens.','Adds visual controls for font, bold, italic, underline, line height, and message spacing.'],
  ['Adiciona filtro de severidade na aba Anomalias: Todas, Críticas, Atenção e Informativas.','Adds a severity filter to the Anomalies tab: All, Critical, Warning, and Informational.'],
  ['Adiciona ajuste de espessura das linhas do mapa e restauração de cor/espessura ao padrão.','Adds map line thickness control and reset of color/thickness to defaults.'],
  ['Adiciona auto-update opcional por Latest Release estável, executado por serviço systemd dedicado.','Adds optional auto-update from the stable Latest Release, executed by a dedicated systemd service.'],
  ['Adiciona verificação de saúde, lock contra atualizações simultâneas e rollback automático em caso de falha.','Adds health verification, a lock against concurrent updates, and automatic rollback on failure.'],
  ['Adiciona status de atualização, botão Atualizar agora e persistência das preferências de auto-update no servidor.','Adds update status, an Update now button, and server-side persistence of auto-update preferences.'],
  ['Adiciona popup de novidades exibido uma única vez ao iniciar após uma atualização.','Adds a what\'s-new popup shown once when the application starts after an update.'],
  ['O atualizador manual traffic-analyzer-update passa a usar a mesma cadeia segura de Latest Release estável do auto-update.','The manual traffic-analyzer-update command now uses the same secure stable Latest Release chain as auto-update.'],
  ['O atualizador manual `traffic-analyzer-update` passa a usar a mesma cadeia segura de Latest Release estável do auto-update.','The manual `traffic-analyzer-update` command now uses the same secure stable Latest Release chain as auto-update.'],
];
const I18N_PT_EN=new Map(I18N_PAIRS);
const I18N_EN_PT=new Map(I18N_PAIRS.map(([pt,en])=>[en,pt]));
function translateDynamic(text,target){
  let s=String(text??'');
  if(target==='en'){
    s=s.replace(/^Histórico pausado · posição (\d+)\/(\d+)$/,'History paused · position $1/$2');
    s=s.replace(/^Histórico: (\d+) traceroutes animáveis · posição (\d+)\/(\d+)$/,'History: $1 animatable traceroutes · position $2/$3');
    s=s.replace(/^Histórico concluído · (\d+) traceroutes reproduzidos$/,'History complete · $1 traceroutes played');
    s=s.replace(/^Histórico (\d+)\/(\d+)$/,'History $1/$2');
    s=s.replace(/^· ANIMAÇÃO PAUSADA · (\d+) traceroute\(s\) represado\(s\) · (\d+) pulso\(s\) represado\(s\) · (\d+) congelado\(s\)( · (\d+) descartado\(s\) por limite)?$/,(m,a,b,c,d,e)=>`· ANIMATION PAUSED · ${a} queued traceroute(s) · ${b} queued pulse(s) · ${c} frozen${e?` · ${e} dropped by limit`:''}`);
    s=s.replace(/^· conectando…$/,'· connecting…');
    s=s.replace(/^· direta (.+) · percurso (.+)$/,'· direct $1 · path $2');
    s=s.replace(/^Total ida \+ volta: (.+)$/,'Total outbound + return: $1');
    s=s.replace(/^Ida: (.+) \| Volta: (.+)$/,'Outbound: $1 | Return: $2');
    s=s.replace(/^· (\d+) traceroutes simultâneos$/,'· $1 simultaneous traceroutes');
    s=s.replace(/^· 1 traceroute em animação$/,'· 1 traceroute animating');
    s=s.replace(/^· erro: (.+)$/,'· error: $1');
    s=s.replace(/^(\d+) mensagens · atualizado (.+)$/,'$1 messages · updated $2');
    s=s.replace(/^(\d+) mensagens · histórico ampliado$/,'$1 messages · history expanded');
    s=s.replace(/^(\d+) mensagem\(ns\) não lida\(s\)$/,'$1 unread message(s)');
    s=s.replace(/^Carregando histórico anterior \(até (\d+)\)\.\.\.$/,'Loading older history (up to $1)...');
    s=s.replace(/^Falha no envio: (.+)$/,'Send failed: $1');
    s=s.replace(/^Não foi possível enviar: (.+)$/,'Could not send: $1');
    s=s.replace(/^Erro: (.+)$/,'Error: $1').replace(/^erro: (.+)$/,'error: $1').replace(/^erro (.+)$/,'error $1');
    s=s.replace(/^Falha ao atualizar: (.+)$/,'Update failed: $1');
    s=s.replace(/^Atualizando v([^ ]+) para v([^ ]+)\.$/,'Updating v$1 to v$2.');
    s=s.replace(/^Atualização concluída: v([^ ]+) → v([^ ]+)\.$/,'Update complete: v$1 → v$2.');
    s=s.replace(/^Erro ao carregar topologia: (.+)$/,'Error loading topology: $1');
    s=s.replace(/^(\d+) nó\(s\) · (\d+) pontos · (.+) acumulados$/,'$1 node(s) · $2 points · $3 accumulated');
    s=s.replace(/^Instalada: v([^ ]+) · disponível: v([^ ]+) · publicada em (.+)\.$/,'Installed: v$1 · available: v$2 · published $3.');
    s=s.replace(/^Instalada: v([^ ]+)\. Esta é a versão mais recente publicada\.$/,'Installed: v$1. This is the latest published version.');
    s=s.replace(/^Instalada: v([^ ]+)\. Não foi possível consultar o GitHub agora\.$/,'Installed: v$1. GitHub could not be checked right now.');
    s=s.replace(/^v([^ ]+) → v([^ ]+) disponível$/,'v$1 → v$2 available');
    s=s.replace(/^v([^ ]+) · não verificado$/,'v$1 · not checked');
    s=s.replace(/^v([^ ]+) · ATUALIZADO$/,'v$1 · UP TO DATE');
    s=s.replace(/^analisado (.+)$/,'analyzed $1').replace(/^atualizado (.+)$/,'updated $1');
    s=s.replace(/^há (\d+) segundos$/,'$1 seconds ago').replace(/^há (\d+) minuto$/,'$1 minute ago').replace(/^há (\d+) minutos$/,'$1 minutes ago');
    s=s.replace(/^há (\d+) hora$/,'$1 hour ago').replace(/^há (\d+) horas$/,'$1 hours ago');
    s=s.replace(/^há (\d+) dia$/,'$1 day ago').replace(/^há (\d+) dias$/,'$1 days ago');
    s=s.replace(/^há (\d+) hora e (\d+) minuto$/,'$1 hour and $2 minute ago').replace(/^há (\d+) hora e (\d+) minutos$/,'$1 hour and $2 minutes ago').replace(/^há (\d+) horas e (\d+) minuto$/,'$1 hours and $2 minute ago').replace(/^há (\d+) horas e (\d+) minutos$/,'$1 hours and $2 minutes ago');
    s=s.replace(/^há (\d+) dia e (\d+) hora$/,'$1 day and $2 hour ago').replace(/^há (\d+) dia e (\d+) horas$/,'$1 day and $2 hours ago').replace(/^há (\d+) dias e (\d+) hora$/,'$1 days and $2 hour ago').replace(/^há (\d+) dias e (\d+) horas$/,'$1 days and $2 hours ago');
    s=s.replace(/^Estado: (.+)$/,'State: $1').replace(/^Posição: (.+)$/,'Position: $1').replace(/^Último tráfego: (.+)$/,'Last traffic: $1').replace(/^Situação: (.+)$/,'Status: $1');
    s=s.replace(/^Observações: (.+)$/,'Observations: $1').replace(/^Ida: (.+)$/,'Outbound: $1').replace(/^Volta: (.+)$/,'Return: $1').replace(/^SNR médio: (.+)$/,'Average SNR: $1').replace(/^Faixa SNR: (.+)$/,'SNR range: $1').replace(/^Última observação: (.+)$/,'Last observation: $1').replace(/ \| canal: /,' | channel: ');
    s=s.replace(/^NodeInfo (.+) · caminho intermediário ainda não observado$/,'NodeInfo $1 · intermediate path not observed yet');
    s=s.replace(/^Rota observada por traceroute próximo \((\d+)s\) · não prova que o NodeInfo usou exatamente os mesmos relays$/,'Route observed by a nearby traceroute ($1s) · this does not prove NodeInfo used exactly the same relays');
    s=s.replace(/^por Alex, PT2VHF$/,'by Alex, PT2VHF').replace(/ - por Alex, PT2VHF$/,' - by Alex, PT2VHF');
  }else{
    s=s.replace(/^History paused · position (\d+)\/(\d+)$/,'Histórico pausado · posição $1/$2');
    s=s.replace(/^History: (\d+) animatable traceroutes · position (\d+)\/(\d+)$/,'Histórico: $1 traceroutes animáveis · posição $2/$3');
    s=s.replace(/^History complete · (\d+) traceroutes played$/,'Histórico concluído · $1 traceroutes reproduzidos');
    s=s.replace(/^History (\d+)\/(\d+)$/,'Histórico $1/$2');
    s=s.replace(/^· ANIMATION PAUSED · (\d+) queued traceroute\(s\) · (\d+) queued pulse\(s\) · (\d+) frozen( · (\d+) dropped by limit)?$/,(m,a,b,c,d,e)=>`· ANIMAÇÃO PAUSADA · ${a} traceroute(s) represado(s) · ${b} pulso(s) represado(s) · ${c} congelado(s)${e?` · ${e} descartado(s) por limite`:''}`);
    s=s.replace(/^· connecting…$/,'· conectando…');
    s=s.replace(/^· direct (.+) · path (.+)$/,'· direta $1 · percurso $2');
    s=s.replace(/^Total outbound \+ return: (.+)$/,'Total ida + volta: $1');
    s=s.replace(/^Outbound: (.+) \| Return: (.+)$/,'Ida: $1 | Volta: $2');
    s=s.replace(/^· (\d+) simultaneous traceroutes$/,'· $1 traceroutes simultâneos').replace(/^· 1 traceroute animating$/,'· 1 traceroute em animação').replace(/^· error: (.+)$/,'· erro: $1');
    s=s.replace(/^(\d+) messages · updated (.+)$/,'$1 mensagens · atualizado $2').replace(/^(\d+) messages · history expanded$/,'$1 mensagens · histórico ampliado').replace(/^(\d+) unread message\(s\)$/,'$1 mensagem(ns) não lida(s)');
    s=s.replace(/^Loading older history \(up to (\d+)\)\.\.\.$/,'Carregando histórico anterior (até $1)...').replace(/^Send failed: (.+)$/,'Falha no envio: $1').replace(/^Could not send: (.+)$/,'Não foi possível enviar: $1');
    s=s.replace(/^Error: (.+)$/,'Erro: $1').replace(/^error: (.+)$/,'erro: $1').replace(/^error (.+)$/,'erro $1').replace(/^Update failed: (.+)$/,'Falha ao atualizar: $1').replace(/^Error loading topology: (.+)$/,'Erro ao carregar topologia: $1');
    s=s.replace(/^Updating v([^ ]+) to v([^ ]+)\.$/,'Atualizando v$1 para v$2.');
    s=s.replace(/^Update complete: v([^ ]+) → v([^ ]+)\.$/,'Atualização concluída: v$1 → v$2.');
    s=s.replace(/^(\d+) node\(s\) · (\d+) points · (.+) accumulated$/,'$1 nó(s) · $2 pontos · $3 acumulados');
    s=s.replace(/^Installed: v([^ ]+) · available: v([^ ]+) · published (.+)\.$/,'Instalada: v$1 · disponível: v$2 · publicada em $3.').replace(/^Installed: v([^ ]+)\. This is the latest published version\.$/,'Instalada: v$1. Esta é a versão mais recente publicada.').replace(/^Installed: v([^ ]+)\. GitHub could not be checked right now\.$/,'Instalada: v$1. Não foi possível consultar o GitHub agora.');
    s=s.replace(/^v([^ ]+) → v([^ ]+) available$/,'v$1 → v$2 disponível').replace(/^v([^ ]+) · not checked$/,'v$1 · não verificado').replace(/^v([^ ]+) · UP TO DATE$/,'v$1 · ATUALIZADO');
    s=s.replace(/^analyzed (.+)$/,'analisado $1').replace(/^updated (.+)$/,'atualizado $1');
    s=s.replace(/^(\d+) seconds ago$/,'há $1 segundos').replace(/^(\d+) minute ago$/,'há $1 minuto').replace(/^(\d+) minutes ago$/,'há $1 minutos').replace(/^(\d+) hour ago$/,'há $1 hora').replace(/^(\d+) hours ago$/,'há $1 horas').replace(/^(\d+) day ago$/,'há $1 dia').replace(/^(\d+) days ago$/,'há $1 dias');
    s=s.replace(/^State: (.+)$/,'Estado: $1').replace(/^Position: (.+)$/,'Posição: $1').replace(/^Last traffic: (.+)$/,'Último tráfego: $1').replace(/^Status: (.+)$/,'Situação: $1');
    s=s.replace(/^Observations: (.+)$/,'Observações: $1').replace(/^Outbound: (.+)$/,'Ida: $1').replace(/^Return: (.+)$/,'Volta: $1').replace(/^Average SNR: (.+)$/,'SNR médio: $1').replace(/^SNR range: (.+)$/,'Faixa SNR: $1').replace(/^Last observation: (.+)$/,'Última observação: $1').replace(/ \| channel: /,' | canal: ');
    s=s.replace(/^NodeInfo (.+) · intermediate path not observed yet$/,'NodeInfo $1 · caminho intermediário ainda não observado');
    s=s.replace(/^Route observed by a nearby traceroute \((\d+)s\) · this does not prove NodeInfo used exactly the same relays$/,'Rota observada por traceroute próximo ($1s) · não prova que o NodeInfo usou exatamente os mesmos relays');
    s=s.replace(/^by Alex, PT2VHF$/,'por Alex, PT2VHF').replace(/ - by Alex, PT2VHF$/,' - por Alex, PT2VHF');
  }
  return s;
}
function translateUiString(value,target=currentLang){
  const raw=String(value??'');
  const lead=(raw.match(/^\s*/)||[''])[0],trail=(raw.match(/\s*$/)||[''])[0];
  const core=raw.slice(lead.length,raw.length-trail.length);
  if(!core)return raw;
  const map=target==='en'?I18N_PT_EN:I18N_EN_PT;
  const exact=map.get(core);
  const out=exact!==undefined?exact:translateDynamic(core,target);
  return lead+out+trail;
}
function tr(value){return translateUiString(value,currentLang);}
function skipI18nElement(el){return !!el?.closest?.('script,style,.msgText,.msgSender,.mentionLong,.mentionShort,.mentionId,.versionNotes,.rawJson,pre,.updateCmd,.i18nNoTranslate');}
function translateUiElement(el){
  if(!el||el.nodeType!==1||skipI18nElement(el))return;
  for(const attr of ['title','placeholder','aria-label']){
    if(el.hasAttribute?.(attr)){const old=el.getAttribute(attr),neu=translateUiString(old,currentLang);if(neu!==old)el.setAttribute(attr,neu);}
  }
}
function translateUiTree(root){
  if(!root)return;
  if(root.nodeType===3){const p=root.parentElement;if(!skipI18nElement(p)){const neu=translateUiString(root.data,currentLang);if(neu!==root.data)root.data=neu;}return;}
  if(root.nodeType!==1 && root.nodeType!==9)return;
  if(root.nodeType===1)translateUiElement(root);
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT|NodeFilter.SHOW_ELEMENT);
  let n; while((n=walker.nextNode())){if(n.nodeType===3){if(!skipI18nElement(n.parentElement)){const neu=translateUiString(n.data,currentLang);if(neu!==n.data)n.data=neu;}}else translateUiElement(n);}
}
let i18nBusy=false,i18nObserver=null;
function initI18nObserver(){
  if(i18nObserver)return;
  i18nObserver=new MutationObserver(ms=>{
    if(i18nBusy)return;i18nBusy=true;
    try{for(const m of ms){if(m.type==='characterData')translateUiTree(m.target);else if(m.type==='attributes')translateUiElement(m.target);else for(const n of m.addedNodes)translateUiTree(n);}}finally{i18nBusy=false;}
  });
  i18nObserver.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','placeholder','aria-label']});
}
function renderHelp(){
  const el=document.getElementById('helpContent');if(!el)return;
  if(currentLang==='en'){
    el.innerHTML=`<h2>Traffic Analyzer Help</h2>
      <p>Traffic Analyzer is a companion web application for MeshMonitor. It analyzes Meshtastic traffic, observed RF topology, traceroutes, messages, node activity, historical positions, network health, and anomalies without taking over the radio connection used by MeshMonitor.</p>
      <div class="helpCallout"><b>Important:</b> the application only shows what its configured MeshMonitor source has observed. A missing link, route, position, or packet is not proof that it never existed on the mesh.</div>
      <h3>1. Map</h3><p>The Map tab shows nodes with known coordinates and observed routing relationships. Node color indicates the age of the last observed traffic. Use <b>Fit</b> to tightly frame visible nodes and <b>Refresh</b> to force topology regeneration.</p>
      <ul><li><b>History:</b> replays stored traceroutes chronologically.</li><li><b>Live:</b> animates new complete traceroutes as MeshMonitor reports them.</li><li><b>Pause:</b> freezes visual animations only. Collection and processing continue, and queued animations are released when playback resumes.</li><li><b>Auto Zoom:</b> optionally follows the nodes involved in traceroute animations.</li></ul>
      <h3>2. Tracklog</h3><p>Tracklog uses real decoded POSITION_APP packets stored in <code>traffic.db</code>. Nodes appear when actual movement is observed; the Meshtastic role alone does not classify a node as mobile.</p>
      <ul><li>Choose 1 h, 6 h, 24 h, 7 days, or 30 days.</li><li>Select all moving nodes or one specific node.</li><li>Click a point to inspect timestamp, coordinates, altitude, SNR, and RSSI when available.</li><li>Very small GPS jitter and clearly impossible terrestrial jumps are filtered.</li></ul>
      <h3>3. Traffic</h3><p>The Traffic tab displays RX/TX packets observed by MeshMonitor. Filters can narrow direction, packet type, and text search. Click a row to inspect the formatted payload and technical fields. Direct text-message contents remain hidden by the server privacy policy.</p>
      <h3>4. Messages</h3><p>The Messages tab works with the primary channel (channel 0). Enter sends a message; Shift+Enter inserts a line break. Delivery symbols represent protocol state/ACK and do <b>not</b> mean that a human read the message.</p>
      <h4>Node mentions</h4><p>Type <code>@</code> and start entering a short name, full name, or node ID. Use the arrow keys and Enter/Tab, or click a suggestion. The selected shortcut is replaced by the node's full name before transmission. Mentions are plain Meshtastic text, so other clients remain compatible.</p>
      <h3>5. Network Health</h3><p>This tab summarizes recent node activity, packet volume, observed links, traceroute completeness, hop counts, chat interactions, and nodes that deserve attention. These indicators prioritize investigation; they are not proof of a hardware or RF fault.</p>
      <h3>6. Anomalies</h3><p>Anomaly detection uses heuristics such as prolonged silence, SNR degradation, relevant hop-count changes, and asymmetric traceroutes. Always interpret an alert together with RF conditions, node role, power state, and the observation point.</p>
      <h3>7. Settings</h3><div class="helpGrid"><div class="helpMini"><b>Appearance</b>Choose Dark or Light interface theme. The base-map style is independent.</div><div class="helpMini"><b>Map and topology</b>Control time window, minimum observations, map style, line visibility, node labels, heat map, and Auto Zoom.</div><div class="helpMini"><b>Sound</b>Enable and tune notifications for a new packet journey.</div><div class="helpMini"><b>Real-time activity</b>Configure source/response and observed-relay pulses.</div><div class="helpMini"><b>Messages</b>Adjust size, font family, bold, italic, underline, line height, and spacing - interface only.</div><div class="helpMini"><b>Privacy</b>NodeInfo flow uses observed evidence and never invents intermediate hops.</div></div>
      <h3>8. Language</h3><p>Use the language selector at the top of the application. Portuguese is the default. Switching to English translates navigation, settings, help, status messages, labels, tooltips, map interface text, and analytical panels. Node names, user messages, IDs, raw protocol values, and release notes are preserved as source data.</p>
      <h3>9. Version and updates</h3><p>The badge at the top compares the installed version with the latest published GitHub Release. Under Settings → Updates, auto-update can be enabled. The interface only creates a request; a dedicated systemd service downloads the stable Release, validates the package, creates a backup, installs it, checks /health, and rolls back if needed.</p>
      <div class="helpCode i18nNoTranslate">sudo traffic-analyzer-update
cat /opt/traffic-analyzer/VERSION</div>
      <p>After an update that changes JavaScript or CSS, use <b>Ctrl+F5</b> if the browser is still showing cached interface files.</p>
      <h3>10. Interpretation limits</h3><div class="helpCallout helpWarn">Traffic Analyzer describes observed data. RF meshes are dynamic: absence of traffic does not by itself prove an outage; a traceroute is evidence of a route observed at a point in time; a relay byte does not always identify a complete path; tracklog distance depends on the positions actually received.</div>`;
  }else{
    el.innerHTML=`<h2>Ajuda do Traffic Analyzer</h2>
      <p>O Traffic Analyzer é uma aplicação web complementar ao MeshMonitor. Ele analisa tráfego Meshtastic, topologia RF observada, traceroutes, mensagens, atividade dos nós, posições históricas, saúde da rede e anomalias sem assumir a conexão com o rádio utilizada pelo MeshMonitor.</p>
      <div class="helpCallout"><b>Importante:</b> a aplicação mostra somente aquilo que a fonte MeshMonitor configurada conseguiu observar. A ausência de enlace, rota, posição ou pacote não prova que o evento nunca existiu na malha.</div>
      <h3>1. Mapa</h3><p>A aba Mapa mostra nós com coordenadas conhecidas e relações de roteamento observadas. A cor do nó indica a idade do último tráfego observado. Use <b>Enquadrar</b> para ocupar a tela com os nós visíveis e <b>Atualizar</b> para forçar a regeneração da topologia.</p>
      <ul><li><b>Histórico:</b> reproduz traceroutes armazenados em ordem cronológica.</li><li><b>Ao vivo:</b> anima novos traceroutes completos à medida que o MeshMonitor os informa.</li><li><b>Pausa:</b> congela apenas as animações visuais. Coleta e processamento continuam, e o que ficou represado é liberado ao retomar.</li><li><b>Auto Zoom:</b> opcionalmente acompanha os nós envolvidos nas animações de traceroute.</li></ul>
      <h3>2. Tracklog</h3><p>O Tracklog usa pacotes POSITION_APP realmente decodificados e armazenados em <code>traffic.db</code>. Um nó aparece quando existe deslocamento real observado; a role do Meshtastic, isoladamente, não classifica o nó como móvel.</p>
      <ul><li>Escolha 1 h, 6 h, 24 h, 7 dias ou 30 dias.</li><li>Mostre todos os nós móveis ou apenas um nó.</li><li>Clique em um ponto para ver data/hora, coordenadas, altitude, SNR e RSSI quando disponíveis.</li><li>Pequeno jitter de GPS e saltos terrestres claramente impossíveis são filtrados.</li></ul>
      <h3>3. Tráfego</h3><p>A aba Tráfego mostra pacotes RX/TX observados pelo MeshMonitor. Os filtros permitem restringir direção, tipo de pacote e busca textual. Clique em uma linha para examinar payload formatado e campos técnicos. O conteúdo de mensagens diretas permanece oculto pela política de privacidade do servidor.</p>
      <h3>4. Mensagens</h3><p>A aba Mensagens trabalha com o canal primário (canal 0). Enter envia; Shift+Enter cria uma nova linha. Os símbolos de entrega representam estado de protocolo/ACK e <b>não</b> significam que uma pessoa leu a mensagem.</p>
      <h4>Menções de nós</h4><p>Digite <code>@</code> e comece a escrever o short name, nome completo ou node ID. Use as setas e Enter/Tab ou clique em uma sugestão. O atalho selecionado é substituído pelo nome completo do nó antes do envio. A menção continua sendo texto Meshtastic normal, preservando compatibilidade com outros clientes.</p>
      <h3>5. Saúde da Rede</h3><p>Resume atividade recente dos nós, volume de pacotes, enlaces observados, completude dos traceroutes, quantidade de hops, interações por chat e nós que merecem atenção. Os indicadores priorizam investigação; não são prova de defeito de hardware ou RF.</p>
      <h3>6. Anomalias</h3><p>A detecção usa heurísticas como silêncio prolongado, degradação de SNR, mudanças relevantes de hops e traceroutes assimétricos. Interprete cada alerta junto das condições de RF, role, alimentação do nó e ponto de observação.</p>
      <h3>7. Configurações</h3><div class="helpGrid"><div class="helpMini"><b>Aparência</b>Escolha tema Escuro ou Claro. O mapa-base é independente.</div><div class="helpMini"><b>Mapa e topologia</b>Controle janela temporal, mínimo de observações, mapa-base, linhas, nomes, mapa de calor e Auto Zoom.</div><div class="helpMini"><b>Som</b>Ative e ajuste notificações para uma nova viagem de pacote.</div><div class="helpMini"><b>Atividade ao vivo</b>Configure pulsos de origem/resposta e relay observado.</div><div class="helpMini"><b>Mensagens</b>Ajuste tamanho, família da fonte, negrito, itálico, sublinhado, altura de linha e espaçamento - somente na interface.</div><div class="helpMini"><b>Privacidade</b>O fluxo NodeInfo usa evidência observada e não inventa hops intermediários.</div></div>
      <h3>8. Idioma</h3><p>Use o seletor de idioma no topo. Português é o padrão. Ao selecionar English, navegação, configurações, ajuda, estados, rótulos, tooltips, textos da interface do mapa e painéis analíticos passam para inglês. Nomes dos nós, mensagens dos usuários, IDs, valores brutos de protocolo e notas das Releases permanecem como dados de origem.</p>
      <h3>9. Versão e atualização</h3><p>O indicador no topo compara a versão instalada com a Latest Release publicada no GitHub. Em Configurações → Atualizações, o auto-update pode ser ativado. A interface cria apenas uma solicitação e um serviço systemd dedicado baixa a Release estável, valida o pacote, cria backup, instala, verifica /health e executa rollback se necessário.</p>
      <div class="helpCode i18nNoTranslate">sudo traffic-analyzer-update
cat /opt/traffic-analyzer/VERSION</div>
      <p>Depois de uma atualização que altere JavaScript ou CSS, use <b>Ctrl+F5</b> caso o navegador ainda esteja exibindo arquivos antigos em cache.</p>
      <h3>10. Limites de interpretação</h3><div class="helpCallout helpWarn">O Traffic Analyzer descreve dados observados. Malhas RF são dinâmicas: ausência de tráfego não prova, isoladamente, indisponibilidade; um traceroute é evidência de uma rota observada naquele momento; o byte de relay não identifica necessariamente todo o caminho; a distância do Tracklog depende das posições que efetivamente foram recebidas.</div>`;
  }
}
function applyLanguage(lang,persist=true){
  currentLang=lang==='en'?'en':'pt-BR';
  if(persist)localStorage.setItem(LANGUAGE_KEY,currentLang);
  const sel=document.getElementById('uiLanguage');if(sel)sel.value=currentLang;
  document.documentElement.lang=currentLang==='en'?'en':'pt-BR';
  renderHelp();
  i18nBusy=true;try{translateUiTree(document.body);document.title=translateUiString(document.title,currentLang);}finally{i18nBusy=false;}
  if(typeof updatePlaybackStatusIdle==='function')updatePlaybackStatusIdle();
  if(typeof tracklogLoaded!=='undefined'&&tracklogLoaded&&typeof renderTracklog==='function')renderTracklog();
}

document.getElementById('uiLanguage').addEventListener('change',e=>applyLanguage(e.target.value,true));

const map = L.map('map', {preferCanvas:true, zoomSnap:0.05, zoomDelta:0.25}).setView([-15.8,-47.9], 9);

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
let trackMap = null;
let trackBaseLayer = null;
let trackLayer = null;
let trackLegend = null;
let tracklogLoaded = false;
let tracklogData = null;
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
let historyAnimationPaused = false;
let animationGeneration = 0;
let livePollTimer = null;
let liveInitialized = false;
let liveSeen = new Set();
let liveQueue = [];
let liveQueueDropped = 0;
const LIVE_QUEUE_MAX = 5000;
let pausedActivityQueue = [];
const PAUSED_ACTIVITY_MAX = 5000;
let liveProcessing = false;
let liveAnimationSeq = 0;
let liveAnimationPaused = false;
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
    lineWidth: Number(document.getElementById('lineWidth').value || 3),
    showShortNames: document.getElementById('showShortNames').checked,
    showLines: document.getElementById('showLines').checked,
    showNodes: document.getElementById('showNodes').checked,
    showHeatmap: document.getElementById('showHeatmap').checked,
    animSpeed: Number(document.getElementById('animSpeed').value || 150),
    soundEnabled: document.getElementById('soundEnabled').checked,
    soundVolume: Number(document.getElementById('soundVolume').value || 35),
    soundTheme: document.getElementById('soundTheme').value || 'formal',
    soundDensity: document.getElementById('soundDensity').value || 'normal',
    soundMinInterval: Number(document.getElementById('soundMinInterval').value || 120),
    soundMaxVoices: Number(document.getElementById('soundMaxVoices').value || 3),
    soundRoutingEnabled: document.getElementById('soundRoutingEnabled').checked,
    soundMessagesEnabled: document.getElementById('soundMessagesEnabled').checked,
    soundAlertsEnabled: document.getElementById('soundAlertsEnabled').checked,
    soundStereoEnabled: document.getElementById('soundStereoEnabled').checked,
    activityAnimationEnabled: document.getElementById('activityAnimationEnabled').checked,
    activityOriginEnabled: document.getElementById('activityOriginEnabled').checked,
    activityRelayEnabled: document.getElementById('activityRelayEnabled').checked,
    activityDuration: Number(document.getElementById('activityDuration').value || 1000),
    autoZoomTraceroute: document.getElementById('autoZoomTraceroute').checked,
    nodeInfoFlowEnabled: document.getElementById('nodeInfoFlowEnabled').checked,
    messageFontSize: Number(document.getElementById('messageFontSize').value || 13),
    messageFontFamily: document.getElementById('messageFontFamily').value || 'system',
    messageBold: document.getElementById('messageBold').checked,
    messageItalic: document.getElementById('messageItalic').checked,
    messageUnderline: document.getElementById('messageUnderline').checked,
    messageLineHeight: Number(document.getElementById('messageLineHeight').value || 1.35),
    messageRowGap: Number(document.getElementById('messageRowGap').value || 4),
    uiTheme: document.getElementById('uiTheme').value || 'dark'
  };
  localStorage.setItem(PREF_KEY, JSON.stringify(prefs));
}
function setBaseMap(type){
  const cfg = baseMaps[type] || baseMaps.osm;
  if(baseLayer) map.removeLayer(baseLayer);
  baseLayer = L.tileLayer(cfg.url, cfg.options).addTo(map);
  baseLayer.bringToBack();
  applyBrightness();
  setTrackBaseMap();
}
function applyBrightness(){
  const value = Math.max(30, Math.min(150, Number(document.getElementById('mapBrightness').value || 100)));
  document.getElementById('mapBrightnessValue').textContent = `${value}%`;
  const pane = map.getPane('tilePane');
  if(pane) pane.style.filter = `brightness(${value}%)`;
  if(trackMap){const tp=trackMap.getPane('tilePane');if(tp)tp.style.filter=`brightness(${value}%)`;}
}
function setTrackBaseMap(){
  if(!trackMap) return;
  const type=document.getElementById('mapType')?.value||'osm';
  const cfg=baseMaps[type]||baseMaps.osm;
  if(trackBaseLayer) trackMap.removeLayer(trackBaseLayer);
  trackBaseLayer=L.tileLayer(cfg.url,cfg.options).addTo(trackMap);
  trackBaseLayer.bringToBack();
  const pane=trackMap.getPane('tilePane');
  if(pane) pane.style.filter=`brightness(${Math.max(30,Math.min(150,Number(document.getElementById('mapBrightness')?.value||100)))}%)`;
}
function initTrackMap(){
  if(trackMap) return;
  trackMap=L.map('tracklogMap',{preferCanvas:true,zoomSnap:0.1,zoomDelta:0.5}).setView([-15.8,-47.9],9);
  trackLayer=L.layerGroup().addTo(trackMap);
  setTrackBaseMap();
  const ctrl=L.control({position:'bottomright'});
  ctrl.onAdd=()=>{trackLegend=L.DomUtil.create('div','tracklogLegend');trackLegend.innerHTML='<b>Tracklog</b><br>Sem trajetos carregados';return trackLegend;};
  ctrl.addTo(trackMap);
}
function trackColor(nodeNum){
  let x=(Number(nodeNum)>>>0)||1; x=((x*2654435761)>>>0)%360;
  return `hsl(${x} 78% 55%)`;
}
function fmtTrackDistance(m){const n=Number(m||0);return n>=1000?`${(n/1000).toLocaleString(uiLocale(),{maximumFractionDigits:1})} km`:`${Math.round(n)} m`;}
function renderTracklog(){
  initTrackMap();
  trackLayer.clearLayers();
  const tracks=tracklogData?.tracks||[];
  const selected=document.getElementById('tracklogNode').value;
  const visible=tracks.filter(t=>selected==='all'||String(t.nodeNum)===selected);
  const bounds=[];
  for(const t of visible){
    const color=trackColor(t.nodeNum);
    const pts=(t.points||[]).map(p=>[Number(p.lat),Number(p.lon)]).filter(x=>Number.isFinite(x[0])&&Number.isFinite(x[1]));
    if(!pts.length) continue;
    pts.forEach(x=>bounds.push(x));
    if(pts.length>1){
      const line=L.polyline(pts,{color,weight:4,opacity:.82}).addTo(trackLayer);
      line.bindTooltip(`${esc(t.name||t.nodeId)} · ${fmtTrackDistance(t.distanceMeters)} · ${t.pointCount} pontos`);
    }
    (t.points||[]).forEach((p,i)=>{
      const current=i===(t.points.length-1);
      const m=L.circleMarker([p.lat,p.lon],{radius:current?6:3,color,fillColor:color,fillOpacity:current?1:.55,weight:current?2:1}).addTo(trackLayer);
      m.bindPopup(`<div class="trackPointPopup"><b>${esc(t.name||t.nodeId)}</b><br>${new Date(Number(p.timestampMs)).toLocaleString(uiLocale())}<br>Posição: ${Number(p.lat).toFixed(5)}, ${Number(p.lon).toFixed(5)}${p.altitude!=null?`<br>Altitude: ${esc(p.altitude)} m`:''}${p.snr!=null?`<br>SNR: ${esc(p.snr)} dB`:''}${p.rssi!=null?`<br>RSSI: ${esc(p.rssi)} dBm`:''}${current?'<br><span class="trackCurrent">posição mais recente do período</span>':''}</div>`);
    });
  }
  if(trackLegend){
    trackLegend.innerHTML='<b>Tracklog</b>'+visible.map(t=>`<div class="trackNode"><span class="trackSwatch" style="background:${trackColor(t.nodeNum)}"></span><span>${esc(t.shortName||t.name||t.nodeId)} · ${fmtTrackDistance(t.distanceMeters)}</span></div>`).join('');
  }
  document.getElementById('tracklogSummary').textContent=visible.length?`${visible.length} nó(s) · ${visible.reduce((a,t)=>a+Number(t.pointCount||0),0)} pontos · ${fmtTrackDistance(visible.reduce((a,t)=>a+Number(t.distanceMeters||0),0))} acumulados`:'Nenhuma mobilidade observada neste período.';
  if(bounds.length) trackMap.fitBounds(L.latLngBounds(bounds),{padding:[18,18],maxZoom:16});
  setTimeout(()=>trackMap.invalidateSize(),30);
}
async function loadTracklog(force=false){
  initTrackMap();
  const hours=document.getElementById('tracklogHours').value;
  const btn=document.getElementById('tracklogReload'); if(btn) btn.disabled=true;
  try{
    const r=await fetch(`/api/tracklog?hours=${encodeURIComponent(hours)}&_=${Date.now()}`,{cache:'no-store'});
    const b=await r.json(); if(!r.ok||!b.success) throw new Error(b.message||`HTTP ${r.status}`);
    tracklogData=b; tracklogLoaded=true;
    const sel=document.getElementById('tracklogNode'),old=sel.value;
    sel.innerHTML='<option value="all">Todos com mobilidade observada</option>'+(b.tracks||[]).map(t=>`<option value="${esc(t.nodeNum)}">${esc(t.shortName||t.name||t.nodeId)} — ${esc(t.name||t.nodeId)} (${t.pointCount})</option>`).join('');
    if([...sel.options].some(o=>o.value===old)) sel.value=old;
    renderTracklog();
  }catch(e){document.getElementById('tracklogSummary').textContent=`Erro: ${String(e.message||e)}`;}
  finally{if(btn)btn.disabled=false;}
}
function applyTheme(){
  const value=document.getElementById('uiTheme')?.value==='light'?'light':'dark';
  document.body.dataset.theme=value;
}
const MESSAGE_FONT_STACKS={
  system:'system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif',
  arial:'Arial,Helvetica,sans-serif',
  verdana:'Verdana,Geneva,sans-serif',
  tahoma:'Tahoma,Verdana,sans-serif',
  georgia:'Georgia,Times New Roman,serif',
  mono:'ui-monospace,SFMono-Regular,Consolas,Liberation Mono,monospace'
};
function applyMessageAppearance(){
  const view=document.getElementById('viewMessages');if(!view)return;
  const size=Math.max(10,Math.min(20,Number(document.getElementById('messageFontSize')?.value||13)));
  const familyKey=document.getElementById('messageFontFamily')?.value||'system';
  const lineHeight=Math.max(1.10,Math.min(2.00,Number(document.getElementById('messageLineHeight')?.value||1.35)));
  const rowGap=Math.max(1,Math.min(14,Number(document.getElementById('messageRowGap')?.value||4)));
  view.style.setProperty('--message-font-size',`${size}px`);
  view.style.setProperty('--message-font-family',MESSAGE_FONT_STACKS[familyKey]||MESSAGE_FONT_STACKS.system);
  view.style.setProperty('--message-font-weight',document.getElementById('messageBold')?.checked?'700':'400');
  view.style.setProperty('--message-font-style',document.getElementById('messageItalic')?.checked?'italic':'normal');
  view.style.setProperty('--message-text-decoration',document.getElementById('messageUnderline')?.checked?'underline':'none');
  view.style.setProperty('--message-line-height',String(lineHeight));
  view.style.setProperty('--message-row-gap',`${rowGap}px`);
  const sizeLabel=document.getElementById('messageFontSizeValue');if(sizeLabel)sizeLabel.textContent=`${size} px`;
  const lhLabel=document.getElementById('messageLineHeightValue');if(lhLabel)lhLabel.textContent=lineHeight.toLocaleString(uiLocale(),{minimumFractionDigits:2,maximumFractionDigits:2});
  const gapLabel=document.getElementById('messageRowGapValue');if(gapLabel)gapLabel.textContent=`${rowGap} px`;
}
function applyMessageFontSize(){applyMessageAppearance();}
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
  if(Number.isFinite(Number(prefs.lineWidth))) document.getElementById('lineWidth').value = String(Math.max(1,Math.min(8,Number(prefs.lineWidth))));
  if(typeof prefs.showShortNames === 'boolean') document.getElementById('showShortNames').checked = prefs.showShortNames;
  document.getElementById('showLines').checked = (typeof prefs.showLines === 'boolean') ? prefs.showLines : true;
  document.getElementById('showNodes').checked = (typeof prefs.showNodes === 'boolean') ? prefs.showNodes : true;
  document.getElementById('showHeatmap').checked = (typeof prefs.showHeatmap === 'boolean') ? prefs.showHeatmap : false;
  if([80,150,280,500].includes(Number(prefs.animSpeed))) document.getElementById('animSpeed').value = String(prefs.animSpeed);
  document.getElementById('soundEnabled').checked = Boolean(prefs.soundEnabled);
  if(Number.isFinite(Number(prefs.soundVolume))) document.getElementById('soundVolume').value = String(Math.max(0,Math.min(100,Number(prefs.soundVolume))));
  if(['pinball70','formal','radio','silent'].includes(prefs.soundTheme)) document.getElementById('soundTheme').value=prefs.soundTheme;
  else if(prefs.soundTone) document.getElementById('soundTheme').value='formal';
  if(['low','normal','high'].includes(prefs.soundDensity)) document.getElementById('soundDensity').value=prefs.soundDensity;
  if(Number.isFinite(Number(prefs.soundMinInterval))) document.getElementById('soundMinInterval').value=String(Math.max(40,Math.min(800,Number(prefs.soundMinInterval))));
  if(Number.isFinite(Number(prefs.soundMaxVoices))) document.getElementById('soundMaxVoices').value=String(Math.max(1,Math.min(8,Number(prefs.soundMaxVoices))));
  document.getElementById('soundRoutingEnabled').checked=(typeof prefs.soundRoutingEnabled==='boolean')?prefs.soundRoutingEnabled:true;
  document.getElementById('soundMessagesEnabled').checked=(typeof prefs.soundMessagesEnabled==='boolean')?prefs.soundMessagesEnabled:true;
  document.getElementById('soundAlertsEnabled').checked=(typeof prefs.soundAlertsEnabled==='boolean')?prefs.soundAlertsEnabled:true;
  document.getElementById('soundStereoEnabled').checked=Boolean(prefs.soundStereoEnabled);
  document.getElementById('activityAnimationEnabled').checked = (typeof prefs.activityAnimationEnabled === 'boolean') ? prefs.activityAnimationEnabled : true;
  document.getElementById('activityOriginEnabled').checked = (typeof prefs.activityOriginEnabled === 'boolean') ? prefs.activityOriginEnabled : true;
  document.getElementById('activityRelayEnabled').checked = (typeof prefs.activityRelayEnabled === 'boolean') ? prefs.activityRelayEnabled : true;
  if([650,1000,1500,2000].includes(Number(prefs.activityDuration))) document.getElementById('activityDuration').value = String(prefs.activityDuration);
  document.getElementById('autoZoomTraceroute').checked = (typeof prefs.autoZoomTraceroute === 'boolean') ? prefs.autoZoomTraceroute : false;
  document.getElementById('nodeInfoFlowEnabled').checked = (typeof prefs.nodeInfoFlowEnabled === 'boolean') ? prefs.nodeInfoFlowEnabled : true;
  if(Number.isFinite(Number(prefs.messageFontSize))) document.getElementById('messageFontSize').value = String(Math.max(10,Math.min(20,Number(prefs.messageFontSize))));
  if(MESSAGE_FONT_STACKS[prefs.messageFontFamily]) document.getElementById('messageFontFamily').value=prefs.messageFontFamily;
  document.getElementById('messageBold').checked=Boolean(prefs.messageBold);
  document.getElementById('messageItalic').checked=Boolean(prefs.messageItalic);
  document.getElementById('messageUnderline').checked=Boolean(prefs.messageUnderline);
  if(Number.isFinite(Number(prefs.messageLineHeight))) document.getElementById('messageLineHeight').value=String(Math.max(1.10,Math.min(2.00,Number(prefs.messageLineHeight))));
  if(Number.isFinite(Number(prefs.messageRowGap))) document.getElementById('messageRowGap').value=String(Math.max(1,Math.min(14,Number(prefs.messageRowGap))));
  document.getElementById('uiTheme').value = prefs.uiTheme === 'light' ? 'light' : 'dark';
  applyTheme();
  applyMessageAppearance();
  document.getElementById('lineWidthValue').textContent=`${document.getElementById('lineWidth').value} px`;
  document.getElementById('soundVolumeValue').textContent = `${document.getElementById('soundVolume').value}%`;
  document.getElementById('soundMinIntervalValue').textContent = `${document.getElementById('soundMinInterval').value} ms`;
  setBaseMap(document.getElementById('mapType').value);
  applyBrightness();
}

const esc = (x) => String(x ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const dt = (ms) => ms ? new Date(ms).toLocaleString(uiLocale()) : '—';
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
      const lineWidth=Math.max(1,Math.min(8,Number(document.getElementById('lineWidth').value||3)));
      const line = L.polyline(e.geometry, {weight:lineWidth, opacity:.82, color:lineColor});
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
      `Último tráfego: ${trafficAge.ts ? new Date(trafficAge.ts).toLocaleString(uiLocale()) : '—'}<br>`+
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
    (showHeatmap ? `<span class="metric warn">Calor = atividade de roteamento observada</span>` : '');
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
function traceKey(t){
  if(t?.id !== null && t?.id !== undefined && String(t.id)!=='') return `id:${t.id}`;
  if(t?.packetId !== null && t?.packetId !== undefined && String(t.packetId)!=='') return `packet:${t.packetId}:${t.fromNodeNum}:${t.toNodeNum}`;
  return `fallback:${t?.timestamp ?? t?.timestampMs ?? ''}:${t?.fromNodeNum}:${t?.toNodeNum}`;
}
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
  if(v<1000) return `${Math.round(v).toLocaleString(uiLocale())} m`;
  return `${(v/1000).toLocaleString(uiLocale(),{minimumFractionDigits:v<10000?1:0,maximumFractionDigits:1})} km`;
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
function updatePlaybackControl(){
  const btn=document.getElementById('playTrace');
  if(!btn) return;
  const live=document.getElementById('playMode').value==='live';
  const paused=live ? (!playbackRunning || liveAnimationPaused) : (!playbackRunning || historyAnimationPaused);
  btn.textContent=paused?'▶':'⏸';
  btn.title=live
    ? (paused?'Retomar animações ao vivo':'Pausar animações ao vivo')
    : (paused?'Reproduzir/retomar histórico':'Pausar histórico');
}
function updatePlaybackStatusIdle(){
  updatePlaybackControl();
  const el = document.getElementById('playStatus');
  if(document.getElementById('playMode').value === 'live'){
    if(!liveInitialized) el.innerHTML = '<span class="liveBadge">AO VIVO</span> · conectando…';
    else if(liveAnimationPaused){
      const queued=liveQueue.length, activity=pausedActivityQueue.length;
      const dropped=liveQueueDropped ? ` · ${liveQueueDropped} descartado(s) por limite` : '';
      el.innerHTML = `<span class="liveBadge">AO VIVO</span> · ANIMAÇÃO PAUSADA · ${queued} traceroute(s) represado(s) · ${activity} pulso(s) represado(s) · ${activeLiveAnimations.size} congelado(s)${dropped}`;
    }
    else if(!liveQueue.length && activeLiveAnimations.size===0) el.innerHTML = '<span class="liveBadge">AO VIVO</span>';
    else if(activeLiveAnimations.size>1) el.innerHTML = `<span class="liveBadge">AO VIVO</span> · ${activeLiveAnimations.size} traceroutes simultâneos`;
    else if(activeLiveAnimations.size===1) el.innerHTML = '<span class="liveBadge">AO VIVO</span> · 1 traceroute em animação';
    return;
  }
  const list = historyTraces();
  if(historyAnimationPaused){
    if(historyIndex >= list.length) historyIndex = Math.max(0, list.length-1);
    el.textContent = list.length ? `Histórico pausado · posição ${historyIndex+1}/${list.length}` : 'Histórico pausado.';
    return;
  }
  if(playbackRunning) return;
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
  historyAnimationPaused = false;
  liveAnimationPaused = false;
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
function autoMapMotionAllowed(){ return !!document.getElementById('autoZoomTraceroute')?.checked; }
function refitAutoZoom(){
  if(!autoZoomEngaged || !autoMapMotionAllowed()) return;
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
  if(!autoMapMotionAllowed()) return false;
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
function disableAutoZoomAndRestore(restore=true){
  if(autoZoomRestoreTimer){ clearTimeout(autoZoomRestoreTimer); autoZoomRestoreTimer=null; }
  autoZoomActive.clear();
  const center=autoZoomSavedCenter, zoom=autoZoomSavedZoom;
  const shouldRestore=restore && autoZoomEngaged && center && Number.isFinite(Number(zoom));
  autoZoomEngaged=false; autoZoomSavedCenter=null; autoZoomSavedZoom=null;
  if(shouldRestore && document.getElementById('viewMap').classList.contains('active')) map.setView(center,zoom,{animate:true});
}
function animatePath(points, color, isActive, isPaused=()=>false){
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
      playMeshSound(idx===0?'origin':(idx===points.length-1?'destination':'relay'),{category:'routing',point:points[idx]});
    };
    emitNode(0);
    let travelled=0;
    let lastFrame=performance.now();
    function cleanup(){ try{ animationLayer.removeLayer(pulse); }catch{} try{ animationLayer.removeLayer(routeGlow); }catch{} }
    function frame(now){
      if(!isActive()){ cleanup(); resolve(false); return; }
      const dt=Math.max(0,Math.min(250,now-lastFrame)); lastFrame=now;
      if(isPaused()){ requestAnimationFrame(frame); return; }
      travelled += (dt/1000)*speed;
      if(travelled >= total){
        pulse.setLatLng(latlngs[latlngs.length-1]);
        for(let i=1;i<points.length;i++) emitNode(i);
        cleanup(); resolve(true); return;
      }
      let rem=travelled, seg=0;
      while(seg<lengths.length-1 && rem>lengths[seg]){ rem-=lengths[seg]; seg++; }
      for(let i=1;i<=seg;i++) emitNode(i);
      const ratio=lengths[seg] ? Math.max(0,Math.min(1,rem/lengths[seg])) : 1;
      pulse.setLatLng(latLngAt(points,seg,ratio));
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  });
}
async function animateTrace(trace, isActive, idx=0, total=1, hudKey=null, isPaused=()=>false){
  if(trace.forwardPath?.length > 1){
    if(hudKey) setTraceHudLeg(hudKey,'forward');
    setTraceStatus(trace,'forward',idx,total);
    if(!await animatePath(trace.forwardPath,'#00e5ff',isActive,isPaused)) return false;
  }
  if(trace.returnPath?.length > 1){
    if(hudKey) setTraceHudLeg(hudKey,'return');
    setTraceStatus(trace,'return',idx,total);
    if(!await animatePath(trace.returnPath,'#ff4fd8',isActive,isPaused)) return false;
  }
  playMeshSound('complete',{category:'routing'});
  return true;
}
async function playHistoryLoop(){
  stopLivePolling();
  const list=historyTraces();
  if(!list.length){ updatePlaybackStatusIdle(); return; }
  historyAnimationPaused=false;
  playbackRunning=true;
  updatePlaybackControl();
  if(historyIndex>=list.length) historyIndex=0;
  const generation=++animationGeneration;
  const active=()=>playbackRunning && generation===animationGeneration && document.getElementById('playMode').value==='history';
  while(active() && historyIndex<list.length){
    const trace=list[historyIndex];
    const autoKey=`history:${generation}:${historyIndex}`;
    const zoomed=beginAutoZoom(autoKey,trace);
    beginTraceHud(autoKey,trace);
    let ok=false;
    try{ ok=await animateTrace(trace,active,historyIndex,list.length,autoKey,()=>historyAnimationPaused); }
    finally{ endTraceHud(autoKey); if(zoomed) endAutoZoom(autoKey); }
    if(!ok) break;
    historyIndex++;
  }
  if(generation===animationGeneration){
    playbackRunning=false;
    historyAnimationPaused=false;
    updatePlaybackControl();
    if(historyIndex>=list.length){ historyIndex=0; document.getElementById('playStatus').textContent=`Histórico concluído · ${list.length} traceroutes reproduzidos`; }
    else updatePlaybackStatusIdle();
  }
}
async function playHistoryOnce(index){
  stopLivePolling();
  const list=historyTraces();
  if(!list.length){ updatePlaybackStatusIdle(); return; }
  historyIndex=Math.max(0,Math.min(index,list.length-1));
  historyAnimationPaused=false;
  playbackRunning=true;
  updatePlaybackControl();
  const generation=++animationGeneration;
  const active=()=>playbackRunning && generation===animationGeneration && document.getElementById('playMode').value==='history';
  const trace=list[historyIndex];
  const autoKey=`history-once:${generation}:${historyIndex}`;
  const zoomed=beginAutoZoom(autoKey,trace);
  beginTraceHud(autoKey,trace);
  try{ await animateTrace(trace,active,historyIndex,list.length,autoKey,()=>historyAnimationPaused); }
  finally{ endTraceHud(autoKey); if(zoomed) endAutoZoom(autoKey); }
  if(generation===animationGeneration){
    playbackRunning=false;
    historyAnimationPaused=false;
    updatePlaybackStatusIdle();
  }
}
async function pollLive(){
  if(document.getElementById('playMode').value !== 'live') return;
  try{
    const r=await fetch('/api/live-traceroutes?limit=200',{cache:'no-store'});
    if(!r.ok) throw new Error(`HTTP ${r.status}`);
    const body=await r.json();
    const rows=(body.data || []).slice().sort((a,b)=>Number(a.timestamp||a.createdAt||0)-Number(b.timestamp||b.createdAt||0));
    if(!liveInitialized){
      // Traceroutes já completos ao abrir a tela são considerados históricos.
      // Registros ainda incompletos NÃO são marcados como vistos: se o MeshMonitor
      // completar a rota depois, o evento poderá ser animado normalmente.
      for(const row of rows){
        const t=normalizeLiveTrace(row);
        if(t?.animatable) liveSeen.add(traceKey(row));
      }
      liveInitialized=true; updatePlaybackStatusIdle(); return;
    }
    const fresh=[];
    for(const row of rows){
      const key=traceKey(row);
      if(liveSeen.has(key)) continue;
      const t=normalizeLiveTrace(row);
      if(!t?.animatable) continue;
      liveSeen.add(key);
      fresh.push(t);
    }
    if(liveSeen.size>12000) liveSeen=new Set([...liveSeen].slice(-6000));
    if(fresh.length){
      liveQueue.push(...fresh);
      if(liveQueue.length>LIVE_QUEUE_MAX){
        const excess=liveQueue.length-LIVE_QUEUE_MAX;
        liveQueue.splice(0,excess); liveQueueDropped+=excess;
      }
      processLiveQueue();
    }
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
      await animateTrace(trace,active,0,1,autoKey,()=>liveAnimationPaused);
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
  if(!playbackRunning || liveAnimationPaused || document.getElementById('playMode').value !== 'live') return;
  // Cada traceroute novo ganha sua própria animação. Assim, um novo evento começa
  // imediatamente mesmo quando outro traceroute ainda está percorrendo o mapa.
  while(liveQueue.length){ runLiveTrace(liveQueue.shift()); }
  updatePlaybackStatusIdle();
}
function startLivePolling(){
  if(livePollTimer) clearInterval(livePollTimer);
  liveSeen=new Set(); liveQueue=[]; liveQueueDropped=0; pausedActivityQueue=[]; liveInitialized=false; liveProcessing=false; liveAnimationPaused=false;
  activeLiveAnimations.clear();
  playbackRunning=true;
  updatePlaybackControl();
  pollLive();
  livePollTimer=setInterval(pollLive,3000);
}
function stopLivePolling(){
  if(livePollTimer){ clearInterval(livePollTimer); livePollTimer=null; }
  activeLiveAnimations.clear();
  liveQueue=[]; pausedActivityQueue=[]; liveQueueDropped=0;
  liveProcessing=false; liveAnimationPaused=false;
  for(const key of [...traceHudEntries.keys()]) if(String(key).startsWith('live:')) traceHudEntries.delete(key);
  renderTraceHud();
  updatePlaybackControl();
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
  const ids={map:'viewMap',tracklog:'viewTracklog',traffic:'viewTraffic',messages:'viewMessages',health:'viewHealth',anomalies:'viewAnomalies',settings:'viewSettings',help:'viewHelp'};
  const target=document.getElementById(ids[name]||'viewMap');
  target.classList.add('active');
  if(name==='map') setTimeout(()=>map.invalidateSize(),40);
  if(name==='tracklog'){initTrackMap();setTimeout(()=>trackMap.invalidateSize(),40);if(!tracklogLoaded)loadTracklog();}
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
function fmtTime(ms){ return ms?new Date(ms).toLocaleTimeString(uiLocale(),{hour12:false}):'—'; }
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
  if(autoMapMotionAllowed() && document.getElementById('viewMap').classList.contains('active')) map.fitBounds(line.getBounds(),{padding:[18,18],maxZoom:13,animate:true});
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
  if(autoMapMotionAllowed() && document.getElementById('viewMap').classList.contains('active')) map.fitBounds(line.getBounds(),{padding:[18,18],maxZoom:13,animate:true});
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
      `<td>${p.snr==null?'—':fmtNum(p.snr,2)}</td><td>${p.rssi==null?'—':esc(p.rssi)}</td><td>${hops==null?'—':esc(hops)}</td></tr>`;
  }).join(''):'<tr><td colspan="8">Nenhum pacote corresponde ao filtro.</td></tr>';
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
    if((/time|timestamp|lastRxTime/i.test(k)) && v>1000000000){const ms=v<10000000000?v*1000:v;return new Date(ms).toLocaleString(uiLocale());}
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
    `<div class="detailGrid"><b>Hora</b><span>${esc(new Date(packetTime(p)).toLocaleString(uiLocale()))}</span>`+
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
function toneOsc(ctx,type,f0,f1,start,duration,amp,output=ctx.destination){
  const osc=ctx.createOscillator(),gain=ctx.createGain(); osc.type=type; osc.frequency.setValueAtTime(f0,start); if(f1&&f1!==f0) osc.frequency.exponentialRampToValueAtTime(f1,start+duration*.65);
  gain.gain.setValueAtTime(0.0001,start); gain.gain.exponentialRampToValueAtTime(Math.max(0.001,amp),start+0.01); gain.gain.exponentialRampToValueAtTime(0.0001,start+duration);
  osc.connect(gain);gain.connect(output);osc.start(start);osc.stop(start+duration+.02);
}
let activeSoundVoices=0;
let relaySoundCounter=0;
function soundOutput(ctx,pan=0){
  if(!document.getElementById('soundStereoEnabled')?.checked || !ctx.createStereoPanner) return ctx.destination;
  const p=ctx.createStereoPanner();p.pan.value=Math.max(-0.8,Math.min(0.8,Number(pan)||0));p.connect(ctx.destination);return p;
}
function soundPanForPoint(pt){
  if(!pt || !document.getElementById('soundStereoEnabled')?.checked || !map) return 0;
  try{const b=map.getBounds(),center=map.getCenter(),span=Math.max(.01,b.getEast()-b.getWest());return Math.max(-.8,Math.min(.8,(Number(pt.lon)-center.lng)/(span*.5)));}catch{return 0;}
}
function noiseBurst(ctx,start,duration,amp,output,highpass=700){
  const frames=Math.max(1,Math.floor(ctx.sampleRate*duration)),buffer=ctx.createBuffer(1,frames,ctx.sampleRate),data=buffer.getChannelData(0);
  for(let i=0;i<frames;i++)data[i]=(Math.random()*2-1)*(1-i/frames);
  const src=ctx.createBufferSource(),filter=ctx.createBiquadFilter(),gain=ctx.createGain();filter.type='highpass';filter.frequency.value=highpass;
  gain.gain.setValueAtTime(Math.max(.0001,amp),start);gain.gain.exponentialRampToValueAtTime(.0001,start+duration);
  src.buffer=buffer;src.connect(filter);filter.connect(gain);gain.connect(output);src.start(start);src.stop(start+duration+.02);
}
function canPlayMeshSound(event,category,force=false){
  if(!force){
    if(!document.getElementById('soundEnabled')?.checked)return false;
    if(document.getElementById('soundTheme')?.value==='silent')return false;
    if(category==='routing'&&!document.getElementById('soundRoutingEnabled')?.checked)return false;
    if(category==='messages'&&!document.getElementById('soundMessagesEnabled')?.checked)return false;
    if(category==='alerts'&&!document.getElementById('soundAlertsEnabled')?.checked)return false;
    const density=document.getElementById('soundDensity')?.value||'normal';
    if(event==='relay'&&density==='low'&&(++relaySoundCounter%3)!==0)return false;
    const minBase=Math.max(40,Number(document.getElementById('soundMinInterval')?.value||120));
    const min=density==='high'?Math.max(40,minBase*.6):(density==='low'?Math.max(250,minBase*1.8):minBase);
    const now=performance.now();if(now-lastSoundAt<min)return false;lastSoundAt=now;
    const maxVoices=Math.max(1,Math.min(8,Number(document.getElementById('soundMaxVoices')?.value||3)));if(activeSoundVoices>=maxVoices)return false;
  }
  return true;
}
function playMeshSound(event,{category='routing',point=null,force=false}={}){
  if(!canPlayMeshSound(event,category,force))return;
  const ctx=ensureAudio();if(!ctx)return;
  const theme=document.getElementById('soundTheme')?.value||'formal';if(theme==='silent')return;
  const vol=Math.max(0,Math.min(1,Number(document.getElementById('soundVolume')?.value||35)/100));
  const out=soundOutput(ctx,soundPanForPoint(point)),t=ctx.currentTime+.01,a=Math.max(.001,vol*.16);
  activeSoundVoices++;
  const done=(ms=500)=>setTimeout(()=>{activeSoundVoices=Math.max(0,activeSoundVoices-1);},ms);
  if(theme==='pinball70'){
    if(event==='origin'){noiseBurst(ctx,t,.12,a*.42,out,450);toneOsc(ctx,'sawtooth',180,520,t,.16,a*.45,out);toneOsc(ctx,'triangle',880,420,t+.07,.12,a*.25,out);done(260);}
    else if(event==='relay'){noiseBurst(ctx,t,.055,a*.5,out,1200);toneOsc(ctx,'triangle',1900,720,t,.085,a*.62,out);toneOsc(ctx,'sine',2700,1350,t+.012,.07,a*.28,out);done(150);}
    else if(event==='destination'){toneOsc(ctx,'triangle',740,1080,t,.13,a*.6,out);toneOsc(ctx,'sine',1480,1480,t+.08,.20,a*.42,out);done(330);}
    else if(event==='ack'||event==='complete'){toneOsc(ctx,'sine',784,784,t,.13,a*.55,out);toneOsc(ctx,'sine',1047,1047,t+.09,.15,a*.5,out);toneOsc(ctx,'sine',1568,1568,t+.18,.25,a*.38,out);done(520);}
    else if(event==='message'){toneOsc(ctx,'triangle',1047,1047,t,.18,a*.55,out);toneOsc(ctx,'sine',1568,1568,t+.08,.25,a*.4,out);done(420);}
    else {noiseBurst(ctx,t,.10,a*.32,out,500);toneOsc(ctx,'sawtooth',420,110,t,.30,a*.45,out);done(430);}
  }else if(theme==='radio'){
    if(event==='origin'){noiseBurst(ctx,t,.07,a*.22,out,900);toneOsc(ctx,'sine',980,1080,t+.035,.10,a*.5,out);done(200);}
    else if(event==='relay'){toneOsc(ctx,'square',1450,950,t,.045,a*.28,out);done(100);}
    else if(event==='destination'||event==='ack'||event==='complete'){toneOsc(ctx,'sine',1180,1320,t,.12,a*.5,out);toneOsc(ctx,'sine',1520,1520,t+.10,.13,a*.35,out);done(300);}
    else if(event==='message'){toneOsc(ctx,'sine',880,880,t,.09,a*.48,out);toneOsc(ctx,'sine',1320,1320,t+.12,.12,a*.42,out);done(300);}
    else {noiseBurst(ctx,t,.08,a*.18,out,500);toneOsc(ctx,'square',360,180,t,.18,a*.28,out);done(280);}
  }else{
    if(event==='origin'){toneOsc(ctx,'sine',620,760,t,.10,a*.42,out);done(160);}
    else if(event==='relay'){toneOsc(ctx,'sine',1050,900,t,.045,a*.27,out);done(100);}
    else if(event==='destination'){toneOsc(ctx,'sine',820,1040,t,.12,a*.43,out);done(200);}
    else if(event==='ack'||event==='complete'){toneOsc(ctx,'sine',880,880,t,.11,a*.42,out);toneOsc(ctx,'sine',1175,1175,t+.09,.16,a*.35,out);done(320);}
    else if(event==='message'){toneOsc(ctx,'sine',660,880,t,.18,a*.42,out);done(260);}
    else {toneOsc(ctx,'sine',320,190,t,.22,a*.38,out);done(300);}
  }
}
function testSoundTheme(){
  ensureAudio();
  const seq=[['origin',0],['relay',240],['relay',430],['destination',650],['ack',900]];
  seq.forEach(([event,delay])=>setTimeout(()=>playMeshSound(event,{force:true,category:'routing'}),delay));
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
function animatePacketActivityNow(p,isNewJourney){
  const from=packetNodeNum(p,'from');
  const relay=resolveRelayNodeNum(p.relay_node);
  const dir=String(p.direction||'').toLowerCase();
  const port=String(p.portnum_name||p.portnum||'').toUpperCase();
  const isTraceroute=port.includes('TRACEROUTE');
  if(!isTraceroute){
    if(isNewJourney && from!==null){
      playMeshSound('origin',{category:'routing',point:nodePointForActivity(from,p)});
      if(relay!==null && relay!==from){
        const delay=Math.max(90,Number(document.getElementById('soundMinInterval')?.value||120)+20);
        setTimeout(()=>playMeshSound('relay',{category:'routing',point:nodePointForActivity(relay,p)}),delay);
      }
    }else if(relay!==null && relay!==from){
      playMeshSound('relay',{category:'routing',point:nodePointForActivity(relay,p)});
    }
  }
  if(!document.getElementById('activityAnimationEnabled').checked) return;
  if(from!==null) activityPulse(from,dir==='rx'?'response':'origin',p);
  if(relay!==null && relay!==from) activityPulse(relay,'relay',p);
}
function animatePacketActivity(p,isNewJourney){
  if(document.getElementById('playMode').value==='live' && liveAnimationPaused){
    pausedActivityQueue.push({p,isNewJourney});
    if(pausedActivityQueue.length>PAUSED_ACTIVITY_MAX) pausedActivityQueue.splice(0,pausedActivityQueue.length-PAUSED_ACTIVITY_MAX);
    updatePlaybackStatusIdle();
    return;
  }
  animatePacketActivityNow(p,isNewJourney);
}
function flushPausedActivityQueue(){
  if(liveAnimationPaused || !pausedActivityQueue.length) return;
  const queued=pausedActivityQueue.splice(0);
  queued.forEach(x=>animatePacketActivityNow(x.p,x.isNewJourney));
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
    if(newJourney)journeySeen.add(jk);
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


let healthLoadedAt=0, anomalyLoadedAt=0, anomalyPayload=null;
function fmtNum(v,dec=0){ const n=Number(v); return Number.isFinite(n)?n.toLocaleString(uiLocale(),{minimumFractionDigits:dec,maximumFractionDigits:dec}):'—'; }
function healthCard(value,label,sub=''){return `<div class="dashCard"><div class="value">${esc(value)}</div><div class="label">${esc(label)}</div>${sub?`<div class="sub">${esc(sub)}</div>`:''}</div>`;}
async function loadNetworkHealth(force=false){
  if(!force && Date.now()-healthLoadedAt<30000)return;
  const cards=document.getElementById('healthCards');
  cards.innerHTML=healthCard('…','Calculando indicadores');
  try{
    const r=await fetch('/api/network-health',{cache:'no-store'}); if(!r.ok)throw new Error(`HTTP ${r.status}`); const b=await r.json();
    healthLoadedAt=Date.now(); document.getElementById('healthUpdated').textContent=`atualizado ${new Date(b.generatedAtMs).toLocaleTimeString(uiLocale())}`;
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
    document.getElementById('healthSilentRows').innerHTML=(b.attentionNodes||[]).map(n=>`<tr><td><b>${esc(n.name||n.nodeId)}</b><br><span class="settingDesc">${esc(n.nodeId||'')}</span></td><td>${n.lastSeen?new Date(n.lastSeen).toLocaleString(uiLocale()):'—'}</td><td>${esc(n.lastSeen?humanAge(n.lastSeen):'sem registro')}</td><td>${fmtNum(n.packets7d)}</td><td>${n.avgSnr7d==null?'—':`${fmtNum(n.avgSnr7d,1)} dB`}</td></tr>`).join('')||'<tr><td colspan="5" class="emptyPanel">Nenhum nó requer atenção pelo critério atual.</td></tr>';
  }catch(e){cards.innerHTML=healthCard('Erro','Não foi possível calcular',String(e));}
}
function sevLabel(s){if(currentLang==='en')return s==='critical'?'Critical':s==='warning'?'Warning':s==='info'?'Informational':'OK';return s==='critical'?'Crítica':s==='warning'?'Atenção':s==='info'?'Informativa':'OK';}
function renderAnomalies(){
  if(!anomalyPayload)return;
  const b=anomalyPayload;
  const filter=document.getElementById('anomalySeverity')?.value||'all';
  const rows=(b.data||[]).filter(a=>filter==='all'||String(a.severity)===filter);
  document.getElementById('anomalyCards').innerHTML=[healthCard(b.summary.total,'Anomalias'),healthCard(b.summary.critical,'Críticas'),healthCard(b.summary.warning,'Atenção'),healthCard(b.summary.info,'Informativas')].join('');
  document.getElementById('anomalyList').innerHTML=rows.map(a=>`<div class="anomalyRow"><div><span class="severity sev-${esc(a.severity)}">${esc(sevLabel(a.severity))}</span></div><div><div class="anomalyTitle">${esc(a.title)}</div><div class="anomalyEvidence">${esc(a.subject||'')}</div></div><div class="anomalyMsg">${esc(a.message)}${a.evidence?`<div class="anomalyEvidence">${esc(a.evidence)}</div>`:''}</div><div class="anomalyTime">${a.timestampMs?esc(humanAge(a.timestampMs)):'—'}</div></div>`).join('')||'<div class="emptyPanel"><span class="severity sev-ok">OK</span> Nenhuma anomalia foi detectada pelos critérios atuais.</div>';
}
async function loadAnomalies(force=false){
  if(!force && Date.now()-anomalyLoadedAt<30000){renderAnomalies();return;}
  try{
    const r=await fetch('/api/anomalies',{cache:'no-store'}); if(!r.ok)throw new Error(`HTTP ${r.status}`); const b=await r.json(); anomalyLoadedAt=Date.now(); anomalyPayload=b;
    document.getElementById('anomalyUpdated').textContent=`analisado ${new Date(b.generatedAtMs).toLocaleTimeString(uiLocale())}`;
    renderAnomalies();
  }catch(e){document.getElementById('anomalyList').innerHTML=`<div class="emptyPanel">Erro ao analisar: ${esc(e)}</div>`;}
}
document.getElementById('healthReload').addEventListener('click',()=>loadNetworkHealth(true));
document.getElementById('anomalyReload').addEventListener('click',()=>loadAnomalies(true));
document.getElementById('anomalySeverity').addEventListener('change',renderAnomalies);

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
    if(fit && lastBounds && lastBounds.isValid()) await fitMapTight();
  }catch(e){
    console.error('Erro ao carregar topologia:', e);
    document.getElementById('summary').innerHTML = `<span class="metric warn">Erro ao carregar topologia: ${esc(e.message||e)}</span>`;
  }
}

async function refreshTopologyNow(){
  const btn=document.getElementById('reload'); if(btn.disabled) return;
  btn.disabled=true; btn.textContent='Atualizando...';
  try{
    const r=await fetch('/api/topology/refresh',{method:'POST',cache:'no-store'});
    const b=await r.json();
    if(!r.ok||!b.success) throw new Error(b.message||`HTTP ${r.status}`);
    await load(false);
    btn.textContent='Atualizado ✓';
    setTimeout(()=>{btn.textContent='Atualizar';},1600);
  }catch(e){
    console.error('Falha ao atualizar topologia:',e);
    btn.textContent='Erro';
    document.getElementById('playStatus').textContent=`Falha ao atualizar: ${String(e.message||e)}`;
    setTimeout(()=>{btn.textContent='Atualizar';},2500);
  }finally{ btn.disabled=false; }
}
function nextPaint(){
  return new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
}
function mapContentFits(margin=6){
  const size=map.getSize();
  if(!size || size.x<=0 || size.y<=0) return true;

  if(lastBounds && lastBounds.isValid()){
    const sw=map.latLngToContainerPoint(lastBounds.getSouthWest());
    const ne=map.latLngToContainerPoint(lastBounds.getNorthEast());
    const minX=Math.min(sw.x,ne.x), maxX=Math.max(sw.x,ne.x);
    const minY=Math.min(sw.y,ne.y), maxY=Math.max(sw.y,ne.y);
    if(minX<margin || minY<margin || maxX>size.x-margin || maxY>size.y-margin) return false;
  }

  const mapRect=map.getContainer().getBoundingClientRect();
  let fits=true;
  nodeLayer.eachLayer(layer=>{
    if(!fits) return;
    if(typeof layer.getLatLng==='function'){
      const p=map.latLngToContainerPoint(layer.getLatLng());
      const radius=Number(layer?.options?.radius||7)+Number(layer?.options?.weight||0)+2;
      if(p.x-radius<margin || p.y-radius<margin || p.x+radius>size.x-margin || p.y+radius>size.y-margin){
        fits=false; return;
      }
    }
    const tooltip=typeof layer.getTooltip==='function' ? layer.getTooltip() : null;
    if(tooltip?.options?.permanent){
      const el=typeof tooltip.getElement==='function' ? tooltip.getElement() : null;
      if(el){
        const r=el.getBoundingClientRect();
        if(r.left<mapRect.left+margin || r.top<mapRect.top+margin || r.right>mapRect.right-margin || r.bottom>mapRect.bottom-margin){
          fits=false;
        }
      }
    }
  });
  return fits;
}
async function fitMapTight(){
  if(!lastBounds || !lastBounds.isValid()) return;

  map.stop();
  map.fitBounds(lastBounds,{padding:[6,6],animate:false,maxZoom:18});
  await nextPaint();

  let safeZoom=map.getZoom();
  let attempts=0;

  while(!mapContentFits(6) && attempts<20 && safeZoom>map.getMinZoom()){
    safeZoom=Math.max(map.getMinZoom(),safeZoom-0.05);
    map.setZoom(safeZoom,{animate:false});
    await nextPaint();
    attempts++;
  }

  attempts=0;
  while(attempts<20){
    const candidate=Math.min(map.getMaxZoom(),safeZoom+0.05);
    if(candidate<=safeZoom+0.001) break;
    map.setZoom(candidate,{animate:false});
    await nextPaint();
    if(!mapContentFits(6)){
      map.setZoom(safeZoom,{animate:false});
      await nextPaint();
      break;
    }
    safeZoom=candidate;
    attempts++;
  }
}

for(const id of ['ageHours','minObs','onlyIdentified']) document.getElementById(id).addEventListener('change', () => { historyIndex=0; savePrefs(); render(); });
document.getElementById('showShortNames').addEventListener('change', () => { savePrefs(); render(); });
for(const id of ['showLines','showNodes','showHeatmap']) document.getElementById(id).addEventListener('change', () => { savePrefs(); render(); });
document.getElementById('mapType').addEventListener('change', (ev) => { setBaseMap(ev.target.value); savePrefs(); });
document.getElementById('mapBrightness').addEventListener('input', () => { applyBrightness(); savePrefs(); });
document.getElementById('lineColor').addEventListener('input', () => { savePrefs(); render(); });
document.getElementById('lineWidth').addEventListener('input',()=>{document.getElementById('lineWidthValue').textContent=`${document.getElementById('lineWidth').value} px`;savePrefs();render();});
document.getElementById('lineStyleReset').addEventListener('click',()=>{document.getElementById('lineColor').value='#ffff00';document.getElementById('lineWidth').value='3';document.getElementById('lineWidthValue').textContent='3 px';savePrefs();render();});
document.getElementById('animSpeed').addEventListener('change', savePrefs);
document.getElementById('playMode').addEventListener('change', () => {
  stopAnimation(); stopLivePolling();
  if(document.getElementById('playMode').value === 'live') startLivePolling();
  else updatePlaybackStatusIdle();
});
document.getElementById('playTrace').addEventListener('click', () => {
  if(document.getElementById('playMode').value==='live'){
    if(!livePollTimer){
      startLivePolling();
      return;
    }
    playbackRunning=true;
    liveAnimationPaused=!liveAnimationPaused;
    if(!liveAnimationPaused){ processLiveQueue(); flushPausedActivityQueue(); }
    updatePlaybackStatusIdle();
    return;
  }
  if(playbackRunning){
    historyAnimationPaused=!historyAnimationPaused;
    updatePlaybackStatusIdle();
  }else{
    playHistoryLoop();
  }
});
document.getElementById('prevTrace').addEventListener('click', () => { if(document.getElementById('playMode').value==='history') playHistoryOnce(historyIndex-1); });
document.getElementById('nextTrace').addEventListener('click', () => { if(document.getElementById('playMode').value==='history') playHistoryOnce(historyIndex+1); });
document.getElementById('reload').addEventListener('click',refreshTopologyNow);
document.getElementById('fit').addEventListener('click',fitMapTight);



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
function dayLabel(ms){const d=new Date(ms),now=new Date();const today=new Date(now.getFullYear(),now.getMonth(),now.getDate());const that=new Date(d.getFullYear(),d.getMonth(),d.getDate());const delta=Math.round((today-that)/86400000);if(delta===0)return 'Hoje';if(delta===1)return 'Ontem';return d.toLocaleDateString(uiLocale(),{day:'2-digit',month:'long',year:'numeric'});}
function lastReadMs(){return Number(localStorage.getItem(MESSAGE_READ_KEY)||0)||0;}
function markMessagesRead(){if(!primaryMessages.length)return;const newest=Math.max(...primaryMessages.filter(m=>!m.mine).map(msgTimeMs),0);if(newest>lastReadMs())localStorage.setItem(MESSAGE_READ_KEY,String(newest));updateUnreadBadge();renderMessages();}
function updateUnreadBadge(){const lr=lastReadMs();const unread=primaryMessages.filter(m=>!m.mine&&msgTimeMs(m)>lr).length;const nav=document.getElementById('messagesNav'),count=document.getElementById('messagesUnreadCount');count.textContent=String(unread);nav.classList.toggle('unread',unread>0);nav.title=unread?`${unread} mensagem(ns) não lida(s)`:'Sem mensagens não lidas';}
let mentionMatches=[];
let mentionActiveIndex=0;
let mentionStart=-1;
function mentionNodeList(){
  return (topology?.nodes||[]).filter(n=>n && (n.name||n.shortName||n.nodeId)).map(n=>({nodeNum:n.nodeNum,nodeId:n.nodeId||'',shortName:n.shortName||'',name:n.longName||n.name||n.shortName||n.nodeId||''}));
}
function mentionContext(){
  const input=document.getElementById('messageInput'),pos=input.selectionStart??input.value.length,before=input.value.slice(0,pos);
  const m=before.match(/(^|[\s,;:!?])@([^@\s,;:!?]*)$/);
  if(!m) return null;
  return {query:(m[2]||'').toLowerCase(),start:pos-(m[2]||'').length-1,end:pos};
}
function closeMentionSuggestions(){const box=document.getElementById('mentionSuggestions');box.classList.remove('open');box.innerHTML='';mentionMatches=[];mentionStart=-1;}
function refreshMentionSuggestions(){
  const ctx=mentionContext(); if(!ctx){closeMentionSuggestions();return;}
  mentionStart=ctx.start;
  const q=ctx.query;
  mentionMatches=mentionNodeList().filter(n=>!q||[n.shortName,n.name,n.nodeId].some(v=>String(v||'').toLowerCase().includes(q))).sort((a,b)=>{
    const ae=String(a.shortName||'').toLowerCase()===q?0:1,be=String(b.shortName||'').toLowerCase()===q?0:1;
    return ae-be||String(a.shortName||a.name).localeCompare(String(b.shortName||b.name),uiLocale());
  }).slice(0,12);
  mentionActiveIndex=Math.min(mentionActiveIndex,Math.max(0,mentionMatches.length-1));
  const box=document.getElementById('mentionSuggestions');
  if(!mentionMatches.length){closeMentionSuggestions();return;}
  box.innerHTML=mentionMatches.map((n,i)=>`<div class="mentionItem ${i===mentionActiveIndex?'active':''}" data-mi="${i}"><div class="mentionShort">${esc(n.shortName||'@')}</div><div><div class="mentionLong">${esc(n.name)}</div><div class="mentionId">${esc(n.nodeId)}</div></div></div>`).join('');
  box.classList.add('open');
  box.querySelectorAll('.mentionItem').forEach(el=>el.addEventListener('mousedown',e=>{e.preventDefault();selectMention(Number(el.dataset.mi));}));
}
function selectMention(index){
  const n=mentionMatches[index]; if(!n)return;
  const input=document.getElementById('messageInput'),pos=input.selectionStart??input.value.length,start=mentionStart>=0?mentionStart:pos;
  const full=n.name||n.shortName||n.nodeId;
  input.value=input.value.slice(0,start)+'@'+full+' '+input.value.slice(pos);
  const next=start+full.length+2; input.setSelectionRange(next,next);closeMentionSuggestions();updateMessageCounter();input.focus();
}
function renderChatText(text){
  let html=esc(text||'');
  const names=[...new Set(mentionNodeList().flatMap(n=>[n.name,n.shortName].filter(Boolean)))].sort((a,b)=>b.length-a.length);
  for(const name of names){
    const token=esc('@'+name);
    if(token) html=html.split(token).join(`<span class="chatMention">${token}</span>`);
  }
  return html;
}
function deliveryVisual(m){const st=String(m.deliveryState||'').toLowerCase();if(m.ackFailed||m.routingErrorReceived||st==='failed')return {icon:'!',cls:'failed',tip:'Falha de entrega/roteamento reportada pelo MeshMonitor'};if(st==='confirmed'||m.ackFromNode)return {icon:'✓✓',cls:'confirmed',tip:'ACK confirmado pelo protocolo; não significa leitura humana'};if(st==='delivered')return {icon:'✓',cls:'',tip:'Transmitida para a malha pelo rádio local'};if(st==='queued'||st==='pending'||!st)return {icon:'◷',cls:'',tip:'Aguardando confirmação de transmissão'};return {icon:'✓',cls:'',tip:`Estado: ${st}`};}
function renderMessages(keepBottom=false){const el=document.getElementById('messageList');if(!primaryMessages.length){el.innerHTML='<div class="emptyPanel">Nenhuma mensagem encontrada no canal primário.</div>';return;}const lr=lastReadMs();let html='',lastDay='';for(const m of primaryMessages){const ms=msgTimeMs(m),dk=dateKey(ms);if(dk!==lastDay){html+=`<div class="msgDay"><span>${esc(dayLabel(ms))}</span></div>`;lastDay=dk;}const dv=deliveryVisual(m);const transport=m.viaMqtt?'MQTT':(m.viaStoreForward?'Store&Forward':'RF');const unread=!m.mine&&ms>lr;html+=`<div class="msgRow ${m.mine?'mine':'theirs'}" data-mid="${esc(m.id||'')}"><div class="msgBubble">${!m.mine?`<div class="msgSender">${esc(m.fromName||m.fromNodeId||'Nó')} ${unread?'<span class="msgNewMark">nova</span>':''}</div>`:''}<div class="msgText">${renderChatText(m.text||'')}</div><div class="msgMeta">${new Date(ms).toLocaleString(uiLocale(),{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}${m.mine?`<span class="msgStatus ${dv.cls}" title="${esc(dv.tip)}">${dv.icon}</span>`:`<span class="msgTransport">${transport}</span>`}</div></div></div>`;}el.innerHTML=html;if(keepBottom||document.getElementById('viewMessages').classList.contains('active'))el.scrollTop=el.scrollHeight;}
async function loadPrimaryMessages(force=false,preserveScroll=false){
  const list=document.getElementById('messageList');
  const oldHeight=list.scrollHeight,oldTop=list.scrollTop;
  try{
    const r=await fetch(`/api/messages?limit=${messageFetchLimit}&_=${Date.now()}`,{cache:'no-store'});
    const b=await r.json();
    if(!r.ok||!b.success)throw new Error(b.message||`HTTP ${r.status}`);
    const rows=(b.data||[]).slice().sort((a,b)=>msgTimeMs(a)-msgTimeMs(b));
    const previousNewest=messageNewestSeen;
    const newIncoming=messagesInitialized?rows.filter(m=>!m.mine&&!messageSeenIds.has(messageKey(m))):[];
    primaryMessages=rows;
    messageNewestSeen=Math.max(...rows.map(msgTimeMs),0);
    document.getElementById('messageStatus').textContent=`${rows.length} mensagens · atualizado ${new Date().toLocaleTimeString(uiLocale())}`;
    if(!messagesInitialized){
      messagesInitialized=true;
      messageSeenIds=new Set(rows.map(messageKey));
      if(!localStorage.getItem(MESSAGE_READ_KEY))localStorage.setItem(MESSAGE_READ_KEY,String(messageNewestSeen));
    }else{
      for(const m of rows)messageSeenIds.add(messageKey(m));
    }
    updateUnreadBadge();
    if(newIncoming.length)playMeshSound('message',{category:'messages'});
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
function stripMentionMarkers(text){
  let out=String(text||'');
  const names=[...new Set(mentionNodeList().flatMap(n=>[n.name,n.shortName,n.nodeId].filter(Boolean)))].sort((a,b)=>b.length-a.length);
  for(const name of names) out=out.split('@'+name).join(name);
  return out;
}
async function sendPrimaryMessage(){const input=document.getElementById('messageInput');const text=stripMentionMarkers(input.value.trim());if(!text)return;const bytes=new TextEncoder().encode(text).length;if(bytes>600){alert(tr('Mensagem muito longa. Reduza o texto para até aproximadamente 600 bytes.'));return;}const btn=document.getElementById('messageSend');btn.disabled=true;document.getElementById('messageStatus').textContent='Enviando...';try{const r=await fetch('/api/messages/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});const b=await r.json();if(!r.ok||!b.success)throw new Error(b.message||b.error||`HTTP ${r.status}`);input.value='';updateMessageCounter();document.getElementById('messageStatus').textContent='Mensagem enviada ao MeshMonitor';setTimeout(()=>loadPrimaryMessages(true),450);}catch(e){document.getElementById('messageStatus').textContent=`Falha no envio: ${e}`;alert(tr(`Não foi possível enviar: ${e}`));}finally{btn.disabled=false;input.focus();}}
function updateMessageCounter(){const el=document.getElementById('messageInput'),n=new TextEncoder().encode(el.value).length,c=document.getElementById('messageCounter');c.textContent=`${n} B`;c.classList.toggle('over',n>600);}
document.getElementById('messageReload').addEventListener('click',reloadPrimaryMessages);document.getElementById('messageLoadOlder').addEventListener('click',loadOlderPrimaryMessages);document.getElementById('messageSend').addEventListener('click',sendPrimaryMessage);document.getElementById('messageInput').addEventListener('input',()=>{updateMessageCounter();mentionActiveIndex=0;refreshMentionSuggestions();});document.getElementById('messageInput').addEventListener('click',refreshMentionSuggestions);document.getElementById('messageInput').addEventListener('keydown',e=>{const box=document.getElementById('mentionSuggestions');if(box.classList.contains('open')){if(e.key==='ArrowDown'){e.preventDefault();mentionActiveIndex=(mentionActiveIndex+1)%mentionMatches.length;refreshMentionSuggestions();return;}if(e.key==='ArrowUp'){e.preventDefault();mentionActiveIndex=(mentionActiveIndex-1+mentionMatches.length)%mentionMatches.length;refreshMentionSuggestions();return;}if((e.key==='Enter'||e.key==='Tab')&&mentionMatches.length){e.preventDefault();selectMention(mentionActiveIndex);return;}if(e.key==='Escape'){e.preventDefault();closeMentionSuggestions();return;}}if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendPrimaryMessage();}});document.addEventListener('click',e=>{if(!document.getElementById('messageComposer').contains(e.target))closeMentionSuggestions();});updateMessageCounter();setInterval(()=>loadPrimaryMessages(false),2500);loadPrimaryMessages(false);


document.querySelectorAll('.navbtn').forEach(b=>b.addEventListener('click',()=>setView(b.dataset.view)));
document.getElementById('tracklogHours').addEventListener('change',()=>loadTracklog(true));
document.getElementById('tracklogNode').addEventListener('change',renderTracklog);
document.getElementById('tracklogReload').addEventListener('click',()=>loadTracklog(true));
document.getElementById('tracklogFit').addEventListener('click',()=>{if(!trackMap||!tracklogData)return;const selected=document.getElementById('tracklogNode').value;const pts=(tracklogData.tracks||[]).filter(t=>selected==='all'||String(t.nodeNum)===selected).flatMap(t=>(t.points||[]).map(p=>[p.lat,p.lon]));if(pts.length)trackMap.fitBounds(L.latLngBounds(pts),{padding:[18,18],maxZoom:16});});
for(const id of ['trafficDirection','trafficType']) document.getElementById(id).addEventListener('change',renderTraffic);
document.getElementById('trafficSearch').addEventListener('input',renderTraffic);
document.getElementById('trafficPause').addEventListener('click',toggleTrafficPause);
document.getElementById('trafficReload').addEventListener('click',async()=>{ trafficPackets=[];trafficInitialized=false;selectedPacketId=null;journeySeen=new Set();await loadTrafficInitial(); });
document.getElementById('trafficDump').addEventListener('click',downloadTrafficDump);
document.getElementById('soundEnabled').addEventListener('change',()=>{ ensureAudio(); savePrefs(); });
document.getElementById('soundVolume').addEventListener('input',()=>{ document.getElementById('soundVolumeValue').textContent=`${document.getElementById('soundVolume').value}%`; savePrefs(); });
document.getElementById('soundTheme').addEventListener('change',savePrefs);
document.getElementById('soundDensity').addEventListener('change',savePrefs);
document.getElementById('soundMinInterval').addEventListener('input',()=>{document.getElementById('soundMinIntervalValue').textContent=`${document.getElementById('soundMinInterval').value} ms`;savePrefs();});
document.getElementById('soundMaxVoices').addEventListener('change',savePrefs);
for(const id of ['soundRoutingEnabled','soundMessagesEnabled','soundAlertsEnabled','soundStereoEnabled'])document.getElementById(id).addEventListener('change',savePrefs);
document.getElementById('soundTest').addEventListener('click',testSoundTheme);
for(const id of ['activityAnimationEnabled','activityOriginEnabled','activityRelayEnabled','activityDuration']) document.getElementById(id).addEventListener('change',()=>{savePrefs(); if(!document.getElementById('activityAnimationEnabled').checked){activityLayer.clearLayers();activityMarkers.clear();}});
document.getElementById('autoZoomTraceroute').addEventListener('change',()=>{savePrefs(); if(!document.getElementById('autoZoomTraceroute').checked) disableAutoZoomAndRestore(false);});
document.getElementById('nodeInfoFlowEnabled').addEventListener('change',()=>{savePrefs(); if(!document.getElementById('nodeInfoFlowEnabled').checked){flowGeneration++;flowLayer.clearLayers();}});
document.getElementById('messageFontSize').addEventListener('input',()=>{applyMessageAppearance();savePrefs();});
document.getElementById('messageFontFamily').addEventListener('change',()=>{applyMessageAppearance();savePrefs();});
for(const id of ['messageBold','messageItalic','messageUnderline']) document.getElementById(id).addEventListener('change',()=>{applyMessageAppearance();savePrefs();});
document.getElementById('messageLineHeight').addEventListener('input',()=>{applyMessageAppearance();savePrefs();});
document.getElementById('messageRowGap').addEventListener('input',()=>{applyMessageAppearance();savePrefs();});
document.getElementById('uiTheme').addEventListener('change',()=>{applyTheme();savePrefs();});
document.getElementById('flowToast').addEventListener('click',()=>setView('map'));

let updateRuntimeData=null;
function updateStateLabel(state){
  const labels={idle:'—',pending:'Pendente',running:'Atualizando',success:'Concluída',failed:'Falhou',rolled_back:'Rollback executado',no_change:'Concluída'};
  return tr(labels[state]||state||'—');
}
function renderUpdateStatus(data){
  updateRuntimeData=data||{};
  const box=document.getElementById('updateStatusBox');if(!box)return;
  const settings=data?.settings||{};
  document.getElementById('autoUpdateEnabled').checked=Boolean(settings.enabled);
  document.getElementById('rollbackEnabled').checked=settings.rollbackEnabled!==false;
  const state=String(data?.state||'idle');
  const target=data?.targetVersion?`v${esc(data.targetVersion)}`:'—';
  const previous=data?.previousVersion?`v${esc(data.previousVersion)}`:'—';
  const completed=data?.completedAtMs?new Date(Number(data.completedAtMs)).toLocaleString(uiLocale()):tr('Nunca');
  const msg=data?.message?`<br>${esc(tr(data.message))}`:'';
  box.innerHTML=`<b>${tr('Versão atual:')}</b> v__APP_VERSION__<br><b>${tr('Status:')}</b> <span class="updateState-${esc(state)}">${esc(updateStateLabel(state))}</span> · <b>${tr('Destino')}</b> ${target}<br><b>${tr('Versão anterior:')}</b> ${previous} · <b>${tr('Última atualização:')}</b> ${esc(completed)}${msg}`;
}
async function loadUpdateStatus(){
  try{
    const r=await fetch('/api/update/status',{cache:'no-store'});const b=await r.json();
    if(!r.ok||!b.success)throw new Error(b.message||`HTTP ${r.status}`);
    renderUpdateStatus(b);return b;
  }catch(e){
    const box=document.getElementById('updateStatusBox');if(box)box.textContent=`${tr('Erro')}: ${e}`;return null;
  }
}
async function saveUpdateSettings(){
  const payload={enabled:document.getElementById('autoUpdateEnabled').checked,rollbackEnabled:document.getElementById('rollbackEnabled').checked};
  const r=await fetch('/api/update/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const b=await r.json();if(!r.ok||!b.success)throw new Error(b.message||`HTTP ${r.status}`);renderUpdateStatus(b.status||{});return b;
}
async function triggerUpdateNow(){
  const btn=document.getElementById('updateNow');btn.disabled=true;btn.textContent=tr('Atualizando...');
  try{
    const r=await fetch('/api/update/trigger',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'update'})});const b=await r.json();
    if(!r.ok||!b.success)throw new Error(b.message||`HTTP ${r.status}`);
    await loadUpdateStatus();btn.textContent=tr(b.requested?'Solicitação de atualização enviada.':'Nenhuma atualização disponível.');
  }catch(e){btn.textContent=tr('Erro');alert(`${tr('Erro')}: ${e}`);}
  finally{setTimeout(()=>{btn.disabled=false;btn.textContent=tr('Atualizar agora');},2200);}
}
document.getElementById('autoUpdateEnabled').addEventListener('change',async()=>{try{await saveUpdateSettings();}catch(e){alert(`${tr('Erro')}: ${e}`);await loadUpdateStatus();}});
document.getElementById('rollbackEnabled').addEventListener('change',async()=>{try{await saveUpdateSettings();}catch(e){alert(`${tr('Erro')}: ${e}`);await loadUpdateStatus();}});
document.getElementById('updateNow').addEventListener('click',triggerUpdateNow);

const WHATS_NEW_SEEN_KEY='trafficAnalyzerWhatsNewSeenV124';
async function showWhatsNewIfNeeded(){
  try{
    const r=await fetch('/api/current-release-notes',{cache:'no-store'});const b=await r.json();if(!r.ok||!b.success)return;
    const current=String(b.version||'__APP_VERSION__'),install=b.lastInstall||{},previous=String(install.previousVersion||'');
    if(!previous||previous===current||localStorage.getItem(WHATS_NEW_SEEN_KEY)===current)return;
    document.getElementById('whatsNewTitle').textContent=currentLang==='en'?'Traffic Analyzer updated':'Traffic Analyzer atualizado';
    document.getElementById('whatsNewSummary').textContent=currentLang==='en'?`Updated from v${previous} to v${current}.`:`Atualizado da v${previous} para a v${current}.`;
    const notes=b.notes||[];
    document.getElementById('whatsNewNotes').innerHTML=notes.length?notes.map(n=>`<div class="wnItem">• ${esc(tr(n))}</div>`).join(''):`<div>${esc(tr('Não há notas de versão disponíveis.'))}</div>`;
    const link=document.getElementById('whatsNewReleaseLink');if(b.releaseUrl)link.href=b.releaseUrl;
    document.getElementById('whatsNewBackdrop').classList.add('open');
    localStorage.setItem(WHATS_NEW_SEEN_KEY,current);
  }catch{}
}
function closeWhatsNew(){document.getElementById('whatsNewBackdrop').classList.remove('open');}
document.getElementById('whatsNewClose').addEventListener('click',closeWhatsNew);
document.getElementById('whatsNewOk').addEventListener('click',closeWhatsNew);
document.getElementById('whatsNewBackdrop').addEventListener('click',e=>{if(e.target===e.currentTarget)closeWhatsNew();});

let versionStatusData=null;
function renderVersionStatus(data){
  versionStatusData=data||null;
  const badge=document.getElementById('versionBadge');
  if(!badge) return;
  badge.classList.remove('checking','current','update','error');
  if(!data || data.status==='unavailable'){
    badge.classList.add('error'); badge.textContent=`v${data?.localVersion||'__APP_VERSION__'} · não verificado`; badge.title='Não foi possível verificar a versão mais recente'; return;
  }
  if(data.updateAvailable){
    badge.classList.add('update'); badge.textContent=`v${data.localVersion} → v${data.latestVersion} disponível`; badge.title='Nova versão disponível - clique para ver as novidades';
  }else{
    badge.classList.add('current'); badge.textContent=`v${data.localVersion} · ATUALIZADO`; badge.title='Esta é a versão mais recente publicada';
  }
}
async function checkVersionStatus(force=false){
  const badge=document.getElementById('versionBadge');
  if(badge && !versionStatusData){ badge.classList.add('checking'); badge.textContent='v__APP_VERSION__ · verificando…'; }
  try{
    const r=await fetch(`/api/version-status${force?'?force=1':''}`,{cache:'no-store'});
    const data=await r.json();
    if(!r.ok) throw new Error(data.message||`HTTP ${r.status}`);
    renderVersionStatus(data); return data;
  }catch(e){
    const data={status:'unavailable',localVersion:'__APP_VERSION__',message:String(e?.message||e)};
    renderVersionStatus(data); return data;
  }
}
function cleanReleaseNotesForModal(raw){
  let s=String(raw||'').replace(/\r/g,'');
  s=s.replace(/\n##\s+Screenshots[\s\S]*$/i,'');
  s=s.split('\n').filter(line=>!/^!\[[^\]]*\]\([^)]*\)\s*$/.test(line.trim())).join('\n');
  return s.replace(/^#{1,6}\s+/gm,'').trim();
}
function openVersionModal(){
  const d=versionStatusData||{localVersion:'__APP_VERSION__',status:'unavailable'};
  const summary=document.getElementById('versionModalSummary');
  const notes=document.getElementById('versionNotes');
  const link=document.getElementById('versionReleaseLink');
  if(d.updateAvailable) summary.textContent=`Instalada: v${d.localVersion} · disponível: v${d.latestVersion} · publicada em ${d.publishedAt?new Date(d.publishedAt).toLocaleString(uiLocale()):tr('data não informada')}.`;
  else if(d.status==='unavailable') summary.textContent=`Instalada: v${d.localVersion}. Não foi possível consultar o GitHub agora.`;
  else summary.textContent=`Instalada: v${d.localVersion}. Esta é a versão mais recente publicada.`;
  notes.textContent=cleanReleaseNotesForModal(d.notes||d.message)||'Não há notas de versão disponíveis.';
  if(d.releaseUrl && /^https:\/\/github\.com\/alexpmr\/traffic-analyzer\//.test(d.releaseUrl)) link.href=d.releaseUrl;
  else link.href='https://github.com/alexpmr/traffic-analyzer/releases/latest';
  document.getElementById('versionModalBackdrop').classList.add('open');
}
function closeVersionModal(){ document.getElementById('versionModalBackdrop').classList.remove('open'); }
document.getElementById('versionBadge').addEventListener('click',openVersionModal);
document.getElementById('versionModalClose').addEventListener('click',closeVersionModal);
document.getElementById('versionModalBackdrop').addEventListener('click',e=>{if(e.target===e.currentTarget)closeVersionModal();});
document.getElementById('versionContinue').addEventListener('click',closeVersionModal);
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeVersionModal();closeWhatsNew();}});

const legend = L.control({position:'bottomright'});
legend.onAdd = () => {
  const d = L.DomUtil.create('div','legend');
  d.innerHTML = '<b>Último tráfego</b><br><span class="dot trafficFresh"></span>até 2 h<br><span class="dot trafficWarm"></span>2 a 24 h<br><span class="dot trafficOld"></span>mais de 24 h<br><span class="dot trafficUnknown"></span>sem registro';
  return d;
};
legend.addTo(map);

initVisualPrefs();
applyLanguage(currentLang,false);
initI18nObserver();
checkVersionStatus(false);
loadUpdateStatus();
showWhatsNewIfNeeded();
setInterval(()=>checkVersionStatus(false),30*60*1000);
setInterval(()=>loadUpdateStatus(),15000);
load(true).then(()=>{ if(document.getElementById('playMode').value==='live') startLivePolling(); });
loadTrafficInitial();
setInterval(() => load(false), 60000);
</script>
</body>
</html>'''.replace('__TITLE__', TITLE.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')).replace('__DISPLAY_TITLE__', DISPLAY_TITLE.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')).replace('__APP_VERSION__', APP_VERSION.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))


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

        CREATE TABLE IF NOT EXISTS positions (
          position_id INTEGER PRIMARY KEY AUTOINCREMENT,
          position_key TEXT NOT NULL UNIQUE,
          source_id TEXT NOT NULL,
          node_num INTEGER NOT NULL,
          node_id TEXT,
          node_name TEXT,
          timestamp INTEGER NOT NULL,
          latitude REAL NOT NULL,
          longitude REAL NOT NULL,
          altitude REAL,
          snr REAL,
          rssi REAL,
          archived_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_positions_node_time ON positions(source_id,node_num,timestamp);
        CREATE INDEX IF NOT EXISTS idx_positions_time ON positions(timestamp);
        """)
    _tracklog_backfill()


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


def _position_payload(metadata):
    if metadata is None:
        return None
    obj = metadata
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    candidates = [obj]
    for key in ("decoded_payload", "decoded", "position", "payload"):
        val = obj.get(key)
        if isinstance(val, dict):
            candidates.insert(0, val)
    for d in candidates:
        lat = d.get("latitude")
        lon = d.get("longitude")
        if lat is None:
            lat = d.get("latitudeI")
        if lon is None:
            lon = d.get("longitudeI")
        try:
            lat = float(lat); lon = float(lon)
        except Exception:
            continue
        if abs(lat) > 90:
            lat /= 1e7
        if abs(lon) > 180:
            lon /= 1e7
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (abs(lat) < 1e-9 and abs(lon) < 1e-9):
            continue
        alt = d.get("altitude", d.get("altitudeHae"))
        try:
            alt = float(alt) if alt is not None else None
        except Exception:
            alt = None
        return lat, lon, alt
    return None


def _tracklog_position_tuple(item, ts, now_ms):
    try:
        portnum = int(item.get("portnum")) if item.get("portnum") is not None else None
    except Exception:
        portnum = None
    if item.get("portnum_name") != "POSITION_APP" and portnum != 3:
        return None
    try:
        node_num = int(item.get("from_node"))
    except Exception:
        return None
    pos = _position_payload(item.get("metadata"))
    if not pos:
        return None
    lat, lon, alt = pos
    key = _archive_key(item)
    name = item.get("from_node_longName") or item.get("from_node_id")
    return (key, MM_SOURCE, node_num, item.get("from_node_id"), name, ts, lat, lon, alt, item.get("snr"), item.get("rssi"), now_ms)


def _tracklog_insert_values(conn, values):
    if not values:
        return 0
    before = conn.total_changes
    conn.executemany("""
      INSERT OR IGNORE INTO positions (
        position_key,source_id,node_num,node_id,node_name,timestamp,latitude,longitude,altitude,snr,rssi,archived_at
      ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, values)
    return conn.total_changes - before


def _tracklog_backfill():
    try:
        now_ms = int(time.time() * 1000)
        with _archive_connect() as conn:
            rows = conn.execute("""
              SELECT archive_key,source_id,mm_row_id AS id,packet_id,timestamp,created_at,direction,
                     from_node,from_node_id,from_node_long_name AS from_node_longName,
                     to_node,to_node_id,to_node_long_name AS to_node_longName,channel,portnum,portnum_name,
                     snr,rssi,relay_node,metadata
              FROM packets
              WHERE source_id=? AND (portnum_name='POSITION_APP' OR portnum=3)
              ORDER BY timestamp ASC
            """, (MM_SOURCE,)).fetchall()
            vals=[]
            for row in rows:
                item=dict(row)
                item["id"]=item.get("id")
                v=_tracklog_position_tuple(item,int(item.get("timestamp") or now_ms),now_ms)
                if v:
                    # preserve the original packet archive key exactly
                    v=(str(item.get("archive_key")),)+v[1:]
                    vals.append(v)
                if len(vals)>=1000:
                    _tracklog_insert_values(conn,vals); vals=[]
            _tracklog_insert_values(conn,vals)
    except Exception as exc:
        print(f"AVISO: não foi possível reconstruir tracklog histórico: {exc}", flush=True)


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
    position_values = []
    for raw in rows:
        item = _sanitize_packet(raw)
        ts = item.get("timestamp") or item.get("created_at") or now_ms
        try:
            ts = int(ts)
        except Exception:
            ts = now_ms
        if ts < 10_000_000_000:
            ts *= 1000
        archive_key = _archive_key(item)
        values.append((
            archive_key, MM_SOURCE, item.get("id"), item.get("packet_id"), ts,
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
        posv = _tracklog_position_tuple(item, ts, now_ms)
        if posv:
            position_values.append((archive_key,)+posv[1:])
    with _archive_connect() as conn:
        before = conn.total_changes
        conn.executemany(sql, values)
        inserted_packets = conn.total_changes - before
        _tracklog_insert_values(conn, position_values)
        return inserted_packets


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
        conn.execute("DELETE FROM positions WHERE timestamp < ?", (cutoff,))
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


def _haversine_m(lat1, lon1, lat2, lon2):
    import math
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.atan2(math.sqrt(a), math.sqrt(max(0.0,1-a)))


def _tracklog_query(hours: int = 24):
    hours = max(1, min(int(hours or 24), 24*30))
    cutoff = int(time.time()*1000) - hours*3600*1000
    with _archive_connect() as conn:
        rows = conn.execute("""
          SELECT node_num,node_id,node_name,timestamp,latitude,longitude,altitude,snr,rssi
          FROM positions WHERE source_id=? AND timestamp>=?
          ORDER BY node_num,timestamp ASC
        """, (MM_SOURCE, cutoff)).fetchall()
    by_node = {}
    for row in rows:
        n = int(row["node_num"])
        by_node.setdefault(n, []).append(row)
    tracks=[]
    try:
        top=json.loads(TOPOLOGY_FILE.read_text(encoding="utf-8"))
    except Exception:
        top={}
    node_meta={int(n.get("nodeNum")):n for n in (top.get("nodes") or []) if n.get("nodeNum") is not None}
    total_points=0
    for node_num, pts in by_node.items():
        cleaned=[]; distance=0.0; last=None
        for row in pts:
            lat=float(row["latitude"]); lon=float(row["longitude"]); ts=int(row["timestamp"])
            if last:
                d=_haversine_m(last["lat"],last["lon"],lat,lon)
                dt=max(1,(ts-last["timestampMs"])/1000.0)
                speed_kmh=(d/dt)*3.6
                # elimina jitter submétrico e saltos manifestamente incompatíveis com deslocamento terrestre
                if d < 3.0:
                    continue
                if speed_kmh > 300.0 and d > 5000.0:
                    continue
                distance += d
            point={"timestampMs":ts,"lat":lat,"lon":lon,"altitude":row["altitude"],"snr":row["snr"],"rssi":row["rssi"]}
            cleaned.append(point); last=point
        if len(cleaned)<2 or distance<100.0:
            continue
        meta=node_meta.get(node_num) or {}
        name=meta.get("name") or meta.get("longName") or (pts[-1]["node_name"] if pts else None) or meta.get("nodeId") or f"!{node_num & 0xffffffff:08x}"
        short=meta.get("shortName") or ""
        node_id=meta.get("nodeId") or (pts[-1]["node_id"] if pts else None) or f"!{node_num & 0xffffffff:08x}"
        # proteção de resposta: amostra no máximo ~2500 pontos por nó
        if len(cleaned)>2500:
            step=max(1,len(cleaned)//2500)
            sampled=cleaned[::step]
            if sampled[-1] is not cleaned[-1]: sampled.append(cleaned[-1])
            cleaned=sampled
        total_points += len(cleaned)
        tracks.append({"nodeNum":node_num,"nodeId":node_id,"name":name,"shortName":short,"pointCount":len(cleaned),"distanceMeters":round(distance,1),"firstTimestampMs":cleaned[0]["timestampMs"],"lastTimestampMs":cleaned[-1]["timestampMs"],"points":cleaned})
    tracks.sort(key=lambda t:(-t["distanceMeters"],str(t["name"])))
    return {"success":True,"hours":hours,"generatedAtMs":int(time.time()*1000),"trackCount":len(tracks),"pointCount":total_points,"tracks":tracks}


def _read_json_file(path: Path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default)
    except Exception:
        return dict(default)


def _write_json_file(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _update_settings():
    raw = _read_json_file(UPDATE_SETTINGS_FILE, {"enabled": False, "rollbackEnabled": True})
    return {
        "enabled": bool(raw.get("enabled", False)),
        "rollbackEnabled": bool(raw.get("rollbackEnabled", True)),
    }


def _save_update_settings(payload: dict):
    data = {
        "enabled": bool(payload.get("enabled", False)),
        "rollbackEnabled": bool(payload.get("rollbackEnabled", True)),
        "updatedAtMs": int(time.time() * 1000),
    }
    _write_json_file(UPDATE_SETTINGS_FILE, data)
    return data


def _local_release_notes(version: str = APP_VERSION):
    path = Path(__file__).with_name("CHANGELOG.md")
    notes = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        active = False
        prefix = f"## {version}"
        prefix_v = f"## v{version}"
        for line in lines:
            stripped = line.strip()
            if not active and (stripped.startswith(prefix) or stripped.startswith(prefix_v)):
                active = True
                continue
            if active and stripped.startswith("## "):
                break
            if active and stripped.startswith("- "):
                notes.append(stripped[2:].strip())
    except Exception:
        pass
    return notes


def _current_release_info():
    return {
        "success": True,
        "version": APP_VERSION,
        "notes": _local_release_notes(APP_VERSION),
        "releaseUrl": f"https://github.com/alexpmr/traffic-analyzer/releases/tag/v{APP_VERSION}",
        "lastInstall": _read_json_file(LAST_INSTALL_FILE, {}),
    }


def _update_runtime_status():
    settings = _update_settings()
    status = _read_json_file(UPDATE_STATUS_FILE, {"state": "idle"})
    status["settings"] = settings
    status["localVersion"] = APP_VERSION
    status["lastInstall"] = _read_json_file(LAST_INSTALL_FILE, {})
    return status


def _request_update(version_data=None, reason: str = "manual"):
    data = version_data or _version_status(force=True)
    if not data.get("success") or data.get("status") == "unavailable":
        raise RuntimeError(data.get("message") or "Não foi possível consultar a Latest Release")
    if not data.get("stable", True):
        raise RuntimeError("A Latest Release consultada não é estável")
    if not data.get("updateAvailable"):
        return {"success": True, "requested": False, "message": "Nenhuma atualização disponível.", "status": _update_runtime_status()}
    settings = _update_settings()
    now_ms = int(time.time() * 1000)
    request = {
        "requestedAtMs": now_ms,
        "requestedBy": reason,
        "targetVersion": data.get("latestVersion"),
        "rollbackEnabled": bool(settings.get("rollbackEnabled", True)),
    }
    _write_json_file(UPDATE_REQUEST_FILE, request)
    _write_json_file(UPDATE_STATUS_FILE, {
        "state": "pending",
        "targetVersion": data.get("latestVersion"),
        "previousVersion": APP_VERSION,
        "requestedAtMs": now_ms,
        "requestedBy": reason,
        "message": "Solicitação de atualização enviada.",
    })
    return {"success": True, "requested": True, "message": "Solicitação de atualização enviada.", "targetVersion": data.get("latestVersion"), "status": _update_runtime_status()}


def _maybe_request_auto_update(version_data: dict):
    settings = _update_settings()
    if not settings.get("enabled") or not version_data.get("updateAvailable") or not version_data.get("stable", True):
        return
    target = str(version_data.get("latestVersion") or "")
    status = _read_json_file(UPDATE_STATUS_FILE, {})
    state = str(status.get("state") or "")
    if str(status.get("targetVersion") or "") == target:
        if state in {"pending", "running"}:
            return
        if state in {"failed", "rolled_back"}:
            completed = float(status.get("completedAtMs") or 0) / 1000.0
            if completed and time.time() - completed < AUTO_UPDATE_RETRY_BACKOFF_SECONDS:
                return
    try:
        _request_update(version_data=version_data, reason="automatic")
    except Exception as exc:
        _write_json_file(UPDATE_STATUS_FILE, {
            "state": "failed",
            "targetVersion": target,
            "previousVersion": APP_VERSION,
            "completedAtMs": int(time.time() * 1000),
            "requestedBy": "automatic",
            "message": str(exc),
        })


def _version_tuple(value: str):
    raw = str(value or "").strip().lower()
    if raw.startswith("v"):
        raw = raw[1:]
    out = []
    for part in raw.split(".")[:4]:
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    while len(out) < 4:
        out.append(0)
    return tuple(out)


def _version_status(force: bool = False):
    now = time.time()
    with _version_status_lock:
        cached = _version_status_cache.get("data")
        checked_at = float(_version_status_cache.get("checked_at") or 0)
        if cached and not force and now - checked_at < VERSION_CHECK_TTL_SECONDS:
            return dict(cached)

        req = urllib.request.Request(
            GITHUB_RELEASES_LATEST_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"Traffic-Analyzer/{APP_VERSION}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                release = json.loads(resp.read().decode("utf-8"))
            tag = str(release.get("tag_name") or "").strip()
            latest = tag[1:] if tag.lower().startswith("v") else tag
            if not latest:
                raise RuntimeError("Release Latest sem tag de versão")
            data = {
                "success": True,
                "status": "ok",
                "localVersion": APP_VERSION,
                "latestVersion": latest,
                "updateAvailable": _version_tuple(latest) > _version_tuple(APP_VERSION),
                "releaseUrl": release.get("html_url"),
                "publishedAt": release.get("published_at"),
                "notes": str(release.get("body") or "").strip(),
                "stable": not bool(release.get("draft")) and not bool(release.get("prerelease")),
                "checkedAtMs": int(now * 1000),
            }
            _version_status_cache["checked_at"] = now
            _version_status_cache["data"] = dict(data)
            return data
        except Exception as exc:
            if cached:
                stale = dict(cached)
                stale["status"] = "stale"
                stale["message"] = f"Falha na consulta atual; exibindo último resultado conhecido: {exc}"
                return stale
            return {
                "success": False,
                "status": "unavailable",
                "localVersion": APP_VERSION,
                "latestVersion": None,
                "updateAvailable": False,
                "releaseUrl": "https://github.com/alexpmr/traffic-analyzer/releases/latest",
                "publishedAt": None,
                "notes": "",
                "message": str(exc),
                "checkedAtMs": int(now * 1000),
            }


def _refresh_topology_now():
    if not _topology_refresh_lock.acquire(blocking=False):
        return {"success": False, "busy": True, "message": "Atualização de topologia já está em andamento."}
    try:
        script = Path(__file__).with_name("traffic_analyzer.py")
        proc = subprocess.run([sys.executable, str(script), "--topology-only"], capture_output=True, text=True, timeout=90, env=os.environ.copy())
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "falha sem detalhes").strip()
            raise RuntimeError(detail[-1800:])
        updated_ms = int(TOPOLOGY_FILE.stat().st_mtime * 1000) if TOPOLOGY_FILE.exists() else int(time.time()*1000)
        return {"success": True, "updatedAtMs": updated_ms, "message": "Topologia atualizada."}
    finally:
        _topology_refresh_lock.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "TrafficAnalyzer/1.24.1"

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
        if path == "/api/version-status":
            try:
                query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                force = (query.get("force") or ["0"])[0] in {"1", "true", "yes"}
                body = _version_status(force=force)
                _maybe_request_auto_update(body)
                self._send(200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({"success": False, "status": "unavailable", "localVersion": APP_VERSION, "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/update/status":
            try:
                self._send(200, "application/json; charset=utf-8", json.dumps({"success": True, **_update_runtime_status()}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({"success": False, "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/current-release-notes":
            self._send(200, "application/json; charset=utf-8", json.dumps(_current_release_info(), ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/tracklog":
            try:
                query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
                hours=int((query.get("hours") or ["24"])[0])
                body=_tracklog_query(hours)
                self._send(200,"application/json; charset=utf-8",json.dumps(body,ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(500,"application/json; charset=utf-8",json.dumps({"success":False,"error":"tracklog_error","message":str(e)},ensure_ascii=False).encode("utf-8"))
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
        if path == "/api/topology/refresh":
            try:
                body = _refresh_topology_now()
                self._send(200 if body.get("success") else 409, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except subprocess.TimeoutExpired:
                self._send(504, "application/json; charset=utf-8", json.dumps({"success": False, "error": "refresh_timeout", "message": "A atualização excedeu 90 segundos."}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({"success": False, "error": "refresh_failed", "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/update/settings":
            try:
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length <= 0 or length > 4096:
                    raise ValueError("Corpo da requisição inválido")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Corpo da requisição inválido")
                settings = _save_update_settings(payload)
                if settings.get("enabled"):
                    _maybe_request_auto_update(_version_status(force=True))
                self._send(200, "application/json; charset=utf-8", json.dumps({"success": True, "settings": settings, "status": _update_runtime_status()}, ensure_ascii=False).encode("utf-8"))
            except ValueError as e:
                self._send(400, "application/json; charset=utf-8", json.dumps({"success": False, "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({"success": False, "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
        if path == "/api/update/trigger":
            try:
                if "application/json" not in str(self.headers.get("Content-Type") or "").lower():
                    raise ValueError("Content-Type application/json obrigatório")
                length = int(self.headers.get("Content-Length", "0") or 0)
                if length <= 0 or length > 1024:
                    raise ValueError("Corpo da requisição inválido")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict) or payload.get("action") != "update":
                    raise ValueError("Ação de atualização inválida")
                body = _request_update(reason="manual")
                self._send(202 if body.get("requested") else 200, "application/json; charset=utf-8", json.dumps(body, ensure_ascii=False).encode("utf-8"))
            except ValueError as e:
                self._send(400, "application/json; charset=utf-8", json.dumps({"success": False, "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            except Exception as e:
                self._send(500, "application/json; charset=utf-8", json.dumps({"success": False, "message": str(e)}, ensure_ascii=False).encode("utf-8"))
            return
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
