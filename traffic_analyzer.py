#!/usr/bin/env python3
"""
Traffic Analyzer v1.24.0

- Analisa traceroutes do MeshMonitor e descobre nós intermediários.
- Solicita NodeInfo de nós desconhecidos/incompletos com cooldown.
- Gera topologia agregada para o mapa do Traffic Analyzer.
- O tráfego de pacotes geral é lido diretamente pela interface web via API v1 do MeshMonitor.

Compatibilidade alvo: MeshMonitor v4.16.1+
Sem dependências externas: Python 3 standard library.
"""

import argparse
import json
import logging
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

LOG = logging.getLogger("traffic-analyzer")


def env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on", "sim"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)).strip())
    except Exception:
        return default


MM_BASE_URL = os.getenv("MM_BASE_URL", "http://127.0.0.1:3001").rstrip("/")
MM_API_TOKEN = os.getenv("MM_API_TOKEN", "").strip()
MM_SOURCE = os.getenv("MM_SOURCE", "default").strip() or "default"

TRACEROUTE_LIMIT = max(1, min(env_int("TRACEROUTE_LIMIT", 5000), 50000))
LOOKBACK_HOURS = max(1, env_int("LOOKBACK_HOURS", 24))
TOPOLOGY_LOOKBACK_HOURS = max(0, env_int("TOPOLOGY_LOOKBACK_HOURS", 0))
NODE_COOLDOWN_HOURS = max(1, env_int("NODE_COOLDOWN_HOURS", 24))
MAX_REQUESTS_PER_RUN = max(0, env_int("MAX_REQUESTS_PER_RUN", 1))
MAX_ATTEMPTS = max(1, env_int("MAX_ATTEMPTS", 3))
ATTEMPT_RESET_HOURS = max(24, env_int("ATTEMPT_RESET_HOURS", 168))
STATE_RETENTION_DAYS = max(7, env_int("STATE_RETENTION_DAYS", 30))
DRY_RUN = env_bool("DRY_RUN", True)

STATE_FILE = Path(os.getenv(
    "STATE_FILE",
    "/var/lib/traffic-analyzer/state.json",
))
TOPOLOGY_FILE = Path(os.getenv(
    "TOPOLOGY_FILE",
    "/var/lib/traffic-analyzer/topology.json",
))

INVALID_NODE_NUMS = {0, 1, 2, 3, 255, 65535, 0xFFFFFFFF}
UNKNOWN_SNR_DB = -32.0


def node_id(node_num: int) -> str:
    return f"!{node_num & 0xFFFFFFFF:08x}"


def api_request(method: str, path: str, body=None):
    if not MM_API_TOKEN:
        raise RuntimeError("MM_API_TOKEN não configurado")

    url = f"{MM_BASE_URL}{path}"
    data = None
    headers = {
        "Authorization": f"Bearer {MM_API_TOKEN}",
        "Accept": "application/json",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw) if raw else {}
            if isinstance(parsed, dict) and parsed.get("success") is False:
                raise RuntimeError(f"API retornou erro: {parsed}")
            return parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} em {url}: {raw[:1000]}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Falha ao acessar {url}: {e}") from e


def load_state():
    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            state = json.load(f)
            if not isinstance(state, dict):
                return {"nodes": {}}
            state.setdefault("nodes", {})
            return state
    except FileNotFoundError:
        return {"nodes": {}}
    except Exception as e:
        LOG.warning("Estado inválido (%s); iniciando novo estado", e)
        return {"nodes": {}}


def atomic_json_write(path: Path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=False)
        f.write("\n")
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def save_state(state):
    atomic_json_write(STATE_FILE, state, mode=0o600)


def to_ms(value):
    try:
        v = float(value)
    except Exception:
        return 0
    if v < 10_000_000_000:
        v *= 1000
    return int(v)


def parse_json_array(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip()
        if not value or value == "null":
            return []
        try:
            parsed = json.loads(value)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def parse_route(value, filter_invalid=True):
    raw = parse_json_array(value)
    result = []
    for item in raw:
        try:
            if isinstance(item, str):
                s = item.strip()
                if s.startswith("!"):
                    n = int(s[1:], 16)
                elif s.lower().startswith("0x"):
                    n = int(s, 16)
                else:
                    n = int(s, 10)
            else:
                n = int(item)
        except Exception:
            continue

        n &= 0xFFFFFFFF
        if filter_invalid and n in INVALID_NODE_NUMS:
            continue
        result.append(n)
    return result


def parse_snr_raw(value):
    result = []
    for item in parse_json_array(value):
        try:
            result.append(float(item))
        except Exception:
            result.append(None)
    return result


def parse_route_positions(value):
    if not value:
        return {}
    if isinstance(value, dict):
        raw = value
    elif isinstance(value, str):
        try:
            raw = json.loads(value)
        except Exception:
            return {}
    else:
        return {}

    if not isinstance(raw, dict):
        return {}

    result = {}
    for key, entry in raw.items():
        try:
            n = int(key) & 0xFFFFFFFF
        except Exception:
            continue
        if n in INVALID_NODE_NUMS or not isinstance(entry, dict):
            continue
        lat = entry.get("lat")
        lon = entry.get("lng")
        if valid_position(lat, lon):
            result[n] = {
                "lat": float(lat),
                "lon": float(lon),
                "alt": entry.get("alt"),
            }
    return result


def valid_position(lat, lon):
    try:
        lat = float(lat)
        lon = float(lon)
    except Exception:
        return False
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return False
    # Evita Null Island / coordenada GPS não inicializada. Um único eixo 0 é válido.
    if abs(lat) < 0.01 and abs(lon) < 0.01:
        return False
    return True


def classify_node(node, n):
    if node is None:
        return "route-only"

    nid = node_id(n)
    long_name = str(node.get("longName") or "").strip()
    short_name = str(node.get("shortName") or "").strip()

    if not long_name:
        return "stub"
    if long_name.lower() == f"node {nid}".lower():
        return "stub"
    if long_name.lower().startswith("node !") and long_name[-8:].lower() == nid[-8:].lower():
        return "stub"
    if not short_name or short_name.lower() == nid[-4:].lower():
        return "stub"
    return "identified"


def is_placeholder_or_incomplete(node, n):
    return classify_node(node, n) != "identified"


def fetch_nodes():
    path = f"/api/v1/sources/{urllib.parse.quote(MM_SOURCE, safe='')}/nodes"
    body = api_request("GET", path)
    data = body.get("data", []) if isinstance(body, dict) else []
    result = {}
    for node in data:
        try:
            n = int(node.get("nodeNum")) & 0xFFFFFFFF
            result[n] = node
        except Exception:
            continue
    return result


def fetch_traceroutes():
    source = urllib.parse.quote(MM_SOURCE, safe="")
    path = f"/api/v1/sources/{source}/traceroutes?limit={TRACEROUTE_LIMIT}"
    body = api_request("GET", path)
    return body.get("data", []) if isinstance(body, dict) else []


def request_nodeinfo(n, channel=None):
    source = urllib.parse.quote(MM_SOURCE, safe="")
    path = f"/api/v1/sources/{source}/actions/request-nodeinfo"
    payload = {"nodeNum": n}
    if isinstance(channel, int) and 0 <= channel <= 7:
        payload["channel"] = channel
    return api_request("POST", path, payload)


def discover_candidates(traceroutes, now_ms):
    cutoff = now_ms - LOOKBACK_HOURS * 3600 * 1000
    candidates = {}

    for tr in traceroutes:
        ts = to_ms(tr.get("timestamp") or tr.get("createdAt"))
        if ts and ts < cutoff:
            continue

        hops = parse_route(tr.get("route")) + parse_route(tr.get("routeBack"))
        try:
            channel = int(tr.get("channel")) if tr.get("channel") is not None else None
        except Exception:
            channel = None
        if channel is not None and not (0 <= channel <= 7):
            channel = None

        for n in hops:
            current = candidates.get(n)
            if current is None or ts >= current["last_seen_ms"]:
                candidates[n] = {
                    "node_num": n,
                    "node_id": node_id(n),
                    "last_seen_ms": ts or now_ms,
                    "channel": channel,
                    "trace_id": tr.get("id"),
                    "from": tr.get("fromNodeId"),
                    "to": tr.get("toNodeId"),
                }

    return list(candidates.values())


def prune_state(state, now_ms):
    retention = STATE_RETENTION_DAYS * 86400 * 1000
    old = []
    for key, item in state.get("nodes", {}).items():
        last_seen = int(item.get("last_seen_ms") or 0)
        last_req = int(item.get("last_request_ms") or 0)
        reference = max(last_seen, last_req)
        if reference and now_ms - reference > retention:
            old.append(key)
    for key in old:
        state["nodes"].pop(key, None)


def has_forward_route_data(value):
    return value is not None and value not in ("", "null")


def has_return_path(route_back_raw, snr_back_raw):
    if parse_json_array(route_back_raw):
        return True
    if snr_back_raw is None:
        return False
    if isinstance(snr_back_raw, str):
        return snr_back_raw not in ("", "null", "[]")
    if isinstance(snr_back_raw, list):
        return bool(snr_back_raw)
    return False


def build_leg_links(start_num, raw_intermediate, end_num, snr_raw, leg):
    """Replica a semântica de adjacency do MeshMonitor: SNR pertence ao receptor."""
    raw_hops = []
    for item in parse_route(raw_intermediate, filter_invalid=False):
        raw_hops.append(item)

    snr_values = parse_snr_raw(snr_raw)
    entries = [(start_num, None)]
    for idx, n in enumerate(raw_hops):
        raw_snr = snr_values[idx] if idx < len(snr_values) else None
        entries.append((n, raw_snr))
    end_snr = snr_values[len(raw_hops)] if len(raw_hops) < len(snr_values) else None
    entries.append((end_num, end_snr))

    # Não "costura" a rota através de hops reservados/desconhecidos.
    # Se houver 0xffffffff (ou outro placeholder), os segmentos dos dois lados
    # ficam interrompidos em vez de criar uma adjacência fictícia.
    links = []
    for idx in range(len(entries) - 1):
        a = entries[idx][0]
        b, raw_snr = entries[idx + 1]
        if a in INVALID_NODE_NUMS or b in INVALID_NODE_NUMS:
            continue
        snr_db = None
        snr_unknown = False
        if raw_snr is not None:
            try:
                snr_db = float(raw_snr) / 4.0
                if math.isclose(snr_db, UNKNOWN_SNR_DB, abs_tol=1e-9):
                    snr_unknown = True
                    snr_db = None
            except Exception:
                snr_db = None
        links.append({
            "from": a,
            "to": b,
            "leg": leg,
            "snr_db": snr_db,
            "snr_unknown": snr_unknown,
        })
    return links


def node_display_name(node, n):
    if node:
        long_name = str(node.get("longName") or "").strip()
        if long_name:
            return long_name
        short_name = str(node.get("shortName") or "").strip()
        if short_name:
            return short_name
    return node_id(n)


def _position_for_trace_node(n, snapshot_positions, nodes):
    """Posição histórica do traceroute; fallback para posição atual do NodeDB."""
    pos = snapshot_positions.get(n)
    if pos and valid_position(pos.get("lat"), pos.get("lon")):
        return {
            "nodeNum": n,
            "nodeId": node_id(n),
            "name": node_display_name(nodes.get(n), n),
            "lat": float(pos["lat"]),
            "lon": float(pos["lon"]),
        }
    row = nodes.get(n)
    if row and valid_position(row.get("latitude"), row.get("longitude")):
        return {
            "nodeNum": n,
            "nodeId": node_id(n),
            "name": node_display_name(row, n),
            "lat": float(row["latitude"]),
            "lon": float(row["longitude"]),
        }
    return None


def _trace_leg_path(start_num, raw_intermediate, end_num, snapshot_positions, nodes):
    """Retorna caminho completo somente se todos os hops forem válidos e posicionados."""
    mids = parse_route(raw_intermediate, filter_invalid=False)
    nums = [start_num, *mids, end_num]
    if len(nums) < 2 or any(n in INVALID_NODE_NUMS for n in nums):
        return None
    pts = []
    for n in nums:
        p = _position_for_trace_node(n, snapshot_positions, nodes)
        if p is None:
            return None
        pts.append(p)
    return pts


def _build_trace_record(tr, nodes, ts):
    try:
        from_num = int(tr.get("fromNodeNum")) & 0xFFFFFFFF
        to_num = int(tr.get("toNodeNum")) & 0xFFFFFFFF
    except Exception:
        return None
    if from_num in INVALID_NODE_NUMS or to_num in INVALID_NODE_NUMS:
        return None
    positions = parse_route_positions(tr.get("routePositions"))
    forward = None
    back = None
    if has_forward_route_data(tr.get("route")):
        forward = _trace_leg_path(from_num, tr.get("route"), to_num, positions, nodes)
    if has_return_path(tr.get("routeBack"), tr.get("snrBack")):
        back = _trace_leg_path(to_num, tr.get("routeBack"), from_num, positions, nodes)
    return {
        "id": tr.get("id"),
        "packetId": tr.get("packetId"),
        "timestampMs": ts,
        "fromNodeNum": from_num,
        "toNodeNum": to_num,
        "fromNodeId": tr.get("fromNodeId") or node_id(from_num),
        "toNodeId": tr.get("toNodeId") or node_id(to_num),
        "fromName": node_display_name(nodes.get(from_num), from_num),
        "toName": node_display_name(nodes.get(to_num), to_num),
        "channel": tr.get("channel"),
        "forwardPath": forward,
        "returnPath": back,
        "animatable": bool((forward and len(forward) >= 2) or (back and len(back) >= 2)),
    }


def build_topology(nodes, traceroutes, now_ms):
    cutoff = None if TOPOLOGY_LOOKBACK_HOURS == 0 else now_ms - TOPOLOGY_LOOKBACK_HOURS * 3600 * 1000
    route_rows = []
    topo_traces = []
    snapshots_by_node = {}
    edge_acc = {}
    route_node_nums = set()

    for tr in traceroutes:
        ts = to_ms(tr.get("timestamp") or tr.get("createdAt")) or now_ms
        if cutoff is not None and ts < cutoff:
            continue
        route_rows.append(tr)
        trace_record = _build_trace_record(tr, nodes, ts)
        if trace_record is not None:
            topo_traces.append(trace_record)
        positions = parse_route_positions(tr.get("routePositions"))
        for n, pos in positions.items():
            prev = snapshots_by_node.get(n)
            if prev is None or ts >= prev["ts"]:
                snapshots_by_node[n] = {"ts": ts, **pos}

        try:
            from_num = int(tr.get("fromNodeNum")) & 0xFFFFFFFF
            to_num = int(tr.get("toNodeNum")) & 0xFFFFFFFF
        except Exception:
            continue
        if from_num in INVALID_NODE_NUMS or to_num in INVALID_NODE_NUMS:
            continue
        route_node_nums.update((from_num, to_num))

        links = []
        if has_forward_route_data(tr.get("route")):
            links.extend(build_leg_links(
                from_num,
                tr.get("route"),
                to_num,
                tr.get("snrTowards"),
                "forward",
            ))
        if has_return_path(tr.get("routeBack"), tr.get("snrBack")):
            links.extend(build_leg_links(
                to_num,
                tr.get("routeBack"),
                from_num,
                tr.get("snrBack"),
                "return",
            ))

        for link in links:
            a = link["from"]
            b = link["to"]
            route_node_nums.update((a, b))
            lo, hi = sorted((a, b))
            key = f"{lo}:{hi}"
            acc = edge_acc.get(key)
            if acc is None:
                acc = {
                    "a": lo,
                    "b": hi,
                    "observations": 0,
                    "forwardObservations": 0,
                    "returnObservations": 0,
                    "firstSeenMs": ts,
                    "lastSeenMs": ts,
                    "snrSamples": [],
                    "latestTraceId": tr.get("id"),
                    "latestPacketId": tr.get("packetId"),
                    "latestChannel": tr.get("channel"),
                    "latestLeg": link["leg"],
                    "events": [],
                }
                edge_acc[key] = acc
            acc["observations"] += 1
            if link["leg"] == "forward":
                acc["forwardObservations"] += 1
            else:
                acc["returnObservations"] += 1
            acc["firstSeenMs"] = min(acc["firstSeenMs"], ts)
            if ts >= acc["lastSeenMs"]:
                acc["lastSeenMs"] = ts
                acc["latestTraceId"] = tr.get("id")
                acc["latestPacketId"] = tr.get("packetId")
                acc["latestChannel"] = tr.get("channel")
                acc["latestLeg"] = link["leg"]
            if link["snr_db"] is not None:
                acc["snrSamples"].append(float(link["snr_db"]))
            acc["events"].append({
                "timestampMs": ts,
                "leg": link["leg"],
                "snr": link["snr_db"],
                "traceId": tr.get("id"),
            })

    all_node_nums = set(nodes.keys()) | route_node_nums | set(snapshots_by_node.keys())
    topo_nodes = []
    coord_by_num = {}
    state_counts = defaultdict(int)

    for n in sorted(all_node_nums):
        if n in INVALID_NODE_NUMS:
            continue
        row = nodes.get(n)
        state = classify_node(row, n)
        state_counts[state] += 1

        lat = lon = alt = None
        position_source = None
        if row and valid_position(row.get("latitude"), row.get("longitude")):
            lat = float(row.get("latitude"))
            lon = float(row.get("longitude"))
            alt = row.get("altitude")
            position_source = "node"
        elif n in snapshots_by_node:
            snap = snapshots_by_node[n]
            lat, lon, alt = snap["lat"], snap["lon"], snap.get("alt")
            position_source = "traceroute-snapshot"

        if lat is not None and lon is not None:
            coord_by_num[n] = (lat, lon)

        topo_nodes.append({
            "nodeNum": n,
            "nodeId": node_id(n),
            "name": node_display_name(row, n),
            "longName": row.get("longName") if row else None,
            "shortName": row.get("shortName") if row else None,
            "state": state,
            "latitude": lat,
            "longitude": lon,
            "altitude": alt,
            "positionSource": position_source,
            "lastHeard": row.get("lastHeard") if row else None,
            "hopsAway": row.get("hopsAway") if row else None,
            "snr": row.get("snr") if row else None,
            "rssi": row.get("rssi") if row else None,
            "hwModel": row.get("hwModel") if row else None,
            "role": row.get("role") if row else None,
            "publicKey": bool(row.get("publicKey")) if row else False,
            "routeParticipant": n in route_node_nums,
        })

    topo_edges = []
    mappable_edges = 0
    for key, acc in edge_acc.items():
        a = acc["a"]
        b = acc["b"]
        row_a = nodes.get(a)
        row_b = nodes.get(b)
        samples = acc.pop("snrSamples")
        avg_snr = round(sum(samples) / len(samples), 2) if samples else None
        min_snr = round(min(samples), 2) if samples else None
        max_snr = round(max(samples), 2) if samples else None

        geometry = None
        if a in coord_by_num and b in coord_by_num:
            lat1, lon1 = coord_by_num[a]
            lat2, lon2 = coord_by_num[b]
            geometry = [[lat1, lon1], [lat2, lon2]]
            mappable_edges += 1

        topo_edges.append({
            "id": key,
            "a": a,
            "b": b,
            "aId": node_id(a),
            "bId": node_id(b),
            "aName": node_display_name(row_a, a),
            "bName": node_display_name(row_b, b),
            "observations": acc["observations"],
            "forwardObservations": acc["forwardObservations"],
            "returnObservations": acc["returnObservations"],
            "firstSeenMs": acc["firstSeenMs"],
            "lastSeenMs": acc["lastSeenMs"],
            "avgSnr": avg_snr,
            "minSnr": min_snr,
            "maxSnr": max_snr,
            "latestTraceId": acc["latestTraceId"],
            "latestPacketId": acc["latestPacketId"],
            "latestChannel": acc["latestChannel"],
            "latestLeg": acc["latestLeg"],
            "geometry": geometry,
            "events": acc["events"],
        })

    topo_edges.sort(key=lambda e: (e["lastSeenMs"], e["observations"]), reverse=True)
    topo_nodes.sort(key=lambda n: (n["state"] != "identified", n["name"].lower()))
    topo_traces.sort(key=lambda t: t["timestampMs"])

    mappable_nodes = sum(1 for n in topo_nodes if n["latitude"] is not None and n["longitude"] is not None)
    return {
        "version": "1.19.0",
        "generatedAtMs": now_ms,
        "sourceId": MM_SOURCE,
        "lookbackHours": TOPOLOGY_LOOKBACK_HOURS,
        "summary": {
            "nodesInApi": len(nodes),
            "traceroutesRead": len(traceroutes),
            "traceroutesInWindow": len(route_rows),
            "routeParticipants": len(route_node_nums),
            "identified": state_counts.get("identified", 0),
            "stub": state_counts.get("stub", 0),
            "routeOnly": state_counts.get("route-only", 0),
            "mappableNodes": mappable_nodes,
            "observedEdges": len(topo_edges),
            "mappableEdges": mappable_edges,
        },
        "nodes": topo_nodes,
        "edges": topo_edges,
        "traces": topo_traces,
        "disclaimer": (
            "As linhas representam adjacências observadas nos traceroutes carregados e filtrados na interface. "
            "Não são enlaces permanentes nem prova de conectividade bidirecional atual."
        ),
    }


def write_topology(nodes, traceroutes, now_ms):
    topology = build_topology(nodes, traceroutes, now_ms)
    atomic_json_write(TOPOLOGY_FILE, topology, mode=0o644)
    s = topology["summary"]
    LOG.info(
        "Topologia: %d enlaces observados (%d mapeáveis), %d nodes mapeáveis; arquivo=%s",
        s["observedEdges"], s["mappableEdges"], s["mappableNodes"], TOPOLOGY_FILE,
    )
    return topology


def run_discovery(nodes, traceroutes, now_ms, state):
    candidates = discover_candidates(traceroutes, now_ms)
    candidates.sort(key=lambda x: x["last_seen_ms"], reverse=True)

    unresolved = []
    identified_count = 0
    route_only_count = 0
    stub_count = 0

    for c in candidates:
        n = c["node_num"]
        status = classify_node(nodes.get(n), n)
        if status == "identified":
            identified_count += 1
        elif status == "route-only":
            route_only_count += 1
        else:
            stub_count += 1

        st = state["nodes"].setdefault(str(n), {})
        st["node_id"] = c["node_id"]
        st["last_seen_ms"] = max(int(st.get("last_seen_ms") or 0), c["last_seen_ms"])
        st["last_trace_id"] = c.get("trace_id")
        st["last_channel"] = c.get("channel")
        st["discovery_state"] = status

        if status == "identified":
            if not st.get("resolved"):
                LOG.info("RESOLVIDO: %s já possui NodeInfo completo no MM", c["node_id"])
            st["resolved"] = True
            st["resolved_ms"] = now_ms
            continue

        st["resolved"] = False
        unresolved.append(c)

    LOG.info(
        "Scan: %d nodes no MM, %d traceroutes lidos, %d IDs intermediários nas últimas %dh | "
        "identificados=%d route-only=%d stubs=%d",
        len(nodes), len(traceroutes), len(candidates), LOOKBACK_HOURS,
        identified_count, route_only_count, stub_count,
    )

    if not unresolved:
        LOG.info("Nenhum hop intermediário novo/incompleto precisa de NodeInfo.")
        return 0

    cooldown_ms = NODE_COOLDOWN_HOURS * 3600 * 1000
    reset_ms = ATTEMPT_RESET_HOURS * 3600 * 1000
    eligible = []
    cooldown_count = 0
    maxed_count = 0

    for c in unresolved:
        n = c["node_num"]
        st = state["nodes"].setdefault(str(n), {})
        last_req = int(st.get("last_request_ms") or 0)
        attempts = int(st.get("attempts") or 0)
        attempt_window_start = int(st.get("attempt_window_start_ms") or 0)

        if attempt_window_start == 0 or now_ms - attempt_window_start >= reset_ms:
            attempts = 0
            st["attempts"] = 0
            st["attempt_window_start_ms"] = now_ms

        if last_req and now_ms - last_req < cooldown_ms:
            cooldown_count += 1
            st["request_state"] = "cooldown"
            continue
        if attempts >= MAX_ATTEMPTS:
            maxed_count += 1
            st["request_state"] = "attempt-limit"
            continue
        st["request_state"] = "eligible"
        eligible.append(c)

    LOG.info(
        "NodeInfo pendente: %d | elegíveis=%d | cooldown=%d | limite-de-tentativas=%d",
        len(unresolved), len(eligible), cooldown_count, maxed_count,
    )

    if MAX_REQUESTS_PER_RUN == 0:
        LOG.info("MAX_REQUESTS_PER_RUN=0: nenhuma solicitação será enviada.")
        return 0

    sent = 0
    for c in eligible:
        if sent >= MAX_REQUESTS_PER_RUN:
            break

        n = c["node_num"]
        st = state["nodes"].setdefault(str(n), {})
        attempts = int(st.get("attempts") or 0)
        origin = f"{c.get('from') or '?'} → {c.get('to') or '?'}"
        status = classify_node(nodes.get(n), n).upper()

        LOG.info(
            "CANDIDATO: %s estado=%s via traceroute id=%s (%s), canal=%s",
            c["node_id"], status, c.get("trace_id"), origin,
            c.get("channel") if c.get("channel") is not None else "automático",
        )

        if DRY_RUN:
            LOG.info("DRY-RUN: pediria NodeInfo de %s", c["node_id"])
            sent += 1
            continue

        try:
            response = request_nodeinfo(n, c.get("channel"))
            st["last_request_ms"] = now_ms
            st["attempts"] = attempts + 1
            st["last_request_ok"] = True
            st["last_error"] = None
            st["request_state"] = "cooldown"
            sent += 1
            LOG.info(
                "NODEINFO SOLICITADO: %s (tentativa %d/%d) resposta=%s",
                c["node_id"], attempts + 1, MAX_ATTEMPTS,
                json.dumps(response.get("data", {}), ensure_ascii=False),
            )
        except Exception as e:
            st["last_request_ms"] = now_ms
            st["attempts"] = attempts + 1
            st["last_request_ok"] = False
            st["last_error"] = str(e)[:1000]
            st["request_state"] = "cooldown"
            sent += 1
            LOG.error("Falha ao pedir NodeInfo de %s: %s", c["node_id"], e)

    if DRY_RUN:
        LOG.info("DRY-RUN ativo: nenhuma transmissão foi feita.")
    else:
        LOG.info("Ciclo concluído: %d solicitação(ões) de NodeInfo enviada(s).", sent)
    return sent


def parse_args():
    p = argparse.ArgumentParser(description="Traffic Analyzer v1.19.0")
    p.add_argument(
        "--topology-only",
        action="store_true",
        help="gera topology.json sem executar solicitações NodeInfo",
    )
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if not MM_API_TOKEN:
        LOG.error("MM_API_TOKEN não configurado em /etc/traffic-analyzer.env")
        return 2

    now_ms = int(time.time() * 1000)

    try:
        nodes = fetch_nodes()
        traceroutes = fetch_traceroutes()
    except Exception as e:
        LOG.error("%s", e)
        return 3

    try:
        write_topology(nodes, traceroutes, now_ms)
    except Exception as e:
        LOG.exception("Falha ao gerar topologia: %s", e)
        return 4

    if args.topology_only:
        LOG.info("Modo --topology-only: topologia atualizada sem ler ou alterar cooldowns/estado de NodeInfo.")
        return 0

    state = load_state()
    prune_state(state, now_ms)
    run_discovery(nodes, traceroutes, now_ms, state)
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
