#!/usr/bin/env python3
"""Funções puras dos comandos de malha integrados ao Traffic Analyzer."""

from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.request


VALID_COMMANDS = {"ping", "clima", "#clima"}


def normalize_command(text) -> str | None:
    value = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if value == "#clima":
        return "clima"
    return value if value in {"ping", "clima"} else None


def node_identity(node: dict | None, fallback_id: str | None = None) -> str:
    node = node or {}
    long_name = str(node.get("longName") or "").strip()
    short_name = str(node.get("shortName") or "").strip()
    generic_name = str(node.get("name") or "").strip()
    node_id = str(node.get("nodeId") or fallback_id or "").strip()

    label = ""
    if long_name and short_name and short_name.lower() != long_name.lower():
        label = f"{long_name} [{short_name}]"
    elif long_name:
        label = long_name
    elif short_name:
        label = short_name
    elif generic_name:
        label = generic_name
    elif node_id:
        label = node_id
    else:
        label = "nó desconhecido"

    if node_id and node_id.lower() not in label.lower():
        return f"{label} ({node_id})"
    return label


def hops_from_message(message: dict) -> int | None:
    try:
        start = int(message.get("hopStart"))
        limit = int(message.get("hopLimit"))
    except (TypeError, ValueError):
        return None
    hops = start - limit
    return hops if 0 <= hops <= 15 else None


def format_hops(hops: int | None, destination_label: str) -> str:
    if hops is None:
        return f"Saltos até {destination_label}: desconhecido"
    return f"Saltos até {destination_label}: {hops}"


def local_time_text(timestamp_ms=None) -> str:
    if timestamp_ms:
        try:
            value = float(timestamp_ms)
            if value > 0:
                if value < 100000000000:
                    value *= 1000
                return _dt.datetime.fromtimestamp(value / 1000).strftime("%H:%M:%S")
        except Exception:
            pass
    return _dt.datetime.now().strftime("%H:%M:%S")


def format_ping_message(*, destination_label: str, origin: str, message: dict,
                        heard_nodes_24h: int | None, route_text: str) -> str:
    lines = [f"PING {destination_label}", f"Origem: {origin}"]
    lines.append(f"Hora: {local_time_text(message.get('receivedAt') or message.get('createdAt') or message.get('timestamp'))}")

    rssi = message.get("rxRssi")
    snr = message.get("rxSnr")
    try:
        if rssi is not None:
            lines.append(f"Sinal recebido: {float(rssi):.0f} dBm")
    except (TypeError, ValueError):
        pass
    try:
        if snr is not None:
            lines.append(f"Qualidade do sinal: {float(snr):.1f} dB")
    except (TypeError, ValueError):
        pass

    lines.append(format_hops(hops_from_message(message), destination_label))
    lines.append("Via: MQTT" if bool(message.get("viaMqtt")) else "Via: LoRa")
    if heard_nodes_24h is not None:
        lines.append(f"Nós ouvidos em 24 h: {int(heard_nodes_24h)}")
    lines.append(f"Teste de rota: {route_text or 'sem resposta'}")
    return "\n".join(lines)


def _expand_clima_segment(segment: str) -> str:
    """Expande rótulos compactos recebidos da API CLIMA para texto legível."""
    text = re.sub(r"\s+", " ", str(segment or "").strip())
    if not text:
        return ""

    replacements = [
        (r"^T\s+([-+]?\d+(?:[.,]\d+)?)\s*°?C$", r"Temperatura: \1 °C"),
        (r"^UR\s+([-+]?\d+(?:[.,]\d+)?)%$", r"Umidade relativa: \1%"),
        (r"^Orvalho\s+([-+]?\d+(?:[.,]\d+)?)\s*°?C$", r"Ponto de orvalho: \1 °C"),
        (r"^P\s+([-+]?\d+(?:[.,]\d+)?)\s*hPa$", r"Pressão: \1 hPa"),
        (r"^UV\s+(.+)$", r"Índice ultravioleta: \1"),
        (r"^(\d+(?:[.,]\d+)?)\s*lx$", r"Iluminação: \1 lux"),
        (r"^Solar\s+([-+]?\d+(?:[.,]\d+)?)\s*W/m2$", r"Radiação solar: \1 W/m²"),
        (r"^min/med/raj\s+(.+)$", r"Vento mínimo / médio / rajada: \1"),
        (r"^(\d+(?:[.,]\d+)?)\s*graus\s+(.+)$", r"Direção do vento: \1° \2"),
        (r"^1min\s+(.+)$", r"Precipitação em 1 minuto: \1"),
        (r"^taxa10m\s+(.+)$", r"Taxa de chuva em 10 minutos: \1"),
        (r"^1h\s+(.+)$", r"Acumulado de chuva em 1 hora: \1"),
        (r"^24h\s+(.+)$", r"Acumulado de chuva em 24 horas: \1"),
        (r"^raios\s+1h\s+(.+)$", r"Raios detectados na última hora: \1"),
        (r"^ultimo\s+(.+)$", r"Último raio detectado: \1"),
        (r"^bat\s+(.+)$", r"Bateria: \1"),
        (r"^dados\s+(\d+)s$", r"Dados atualizados há \1 segundos"),
    ]
    for pattern, repl in replacements:
        if re.match(pattern, text, flags=re.IGNORECASE):
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
            break

    text = re.sub(r"(?i)\bsem chuva\b", "Sem chuva no momento", text)
    text = re.sub(r"(?i)\bult\.?\b", "último", text)
    text = re.sub(r"(?i)\bbat\.?\b", "bateria", text)
    text = re.sub(r"(?i)\braj\.?\b", "rajada", text)
    text = re.sub(r"(?i)\bmed\.?\b", "médio", text)
    text = re.sub(r"(?i)\bmin\.?\b", "mínimo", text)
    text = re.sub(r"(?i)(\d)(mm/h)\b", r"\1 mm/h", text)
    text = re.sub(r"(?i)(\d)(mm)\b", r"\1 mm", text)
    text = re.sub(r"(?i)(\d)(m/s)\b", r"\1 m/s", text)
    text = re.sub(r"(?i)(\d)(hPa)\b", r"\1 hPa", text)
    text = re.sub(r"(?i)(\d)(V)\b", r"\1 V", text)
    return text


def normalize_clima_message(text: str) -> str:
    """Converte mensagens compactas da API CLIMA em blocos multilinha legíveis."""
    raw = str(text or "").replace("\r", "").strip()
    if not raw:
        return ""
    segments = [x.strip() for x in re.split(r"\s*\|\s*", raw) if x.strip()]
    if not segments:
        return raw

    heading = segments[0]
    heading_map = {
        "LUZ/VENTO": "Luz e vento",
        "CHUVA": "Chuva",
        "RAIOS/TEMPEST": "Raios e estação meteorológica",
        "RAIOS/TEMPESTADE": "Raios e tempestade",
        "ALERTA": "Alerta meteorológico",
    }
    lines = [heading_map.get(heading.upper(), heading)]
    lines.extend(_expand_clima_segment(x) for x in segments[1:])
    lines = [x for x in lines if x]

    # Alertas devem ser autoexplicativos, mesmo quando a fonte usa rótulos curtos.
    normalized = "\n".join(lines)
    normalized = re.sub(r"(?im)^CHUVA FORTE$", "Alerta de chuva forte", normalized)
    normalized = re.sub(r"(?im)^RAIOS$", "Alerta de raios", normalized)
    normalized = re.sub(r"(?im)^VENTO FORTE$", "Alerta de vento forte", normalized)
    normalized = re.sub(r"(?im)^GRANIZO$", "Alerta de granizo", normalized)
    normalized = re.sub(r"(?im)^TEMPESTADE$", "Alerta de tempestade", normalized)
    normalized = re.sub(r":\s*--$", ": sem registro", normalized, flags=re.MULTILINE)
    return normalized


def fetch_clima_responses(url: str, timeout: float = 6.0) -> list[str]:
    req = urllib.request.Request(str(url), headers={"User-Agent": "TrafficAnalyzer-MeshCommands/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    body = json.loads(raw) if raw else {}
    responses = body.get("responses") if isinstance(body, dict) else None
    if not isinstance(responses, list):
        raise RuntimeError("Resposta inválida da API de clima")
    out = [normalize_clima_message(str(x)) for x in responses if str(x).strip()]
    out = [x for x in out if x]
    if not out:
        raise RuntimeError("API de clima não retornou mensagens")
    return out[:4]


def split_utf8(text: str, max_bytes: int = 200) -> list[str]:
    """Divide em linhas preservando limite de bytes do Meshtastic."""
    text = str(text or "").strip()
    if len(text.encode("utf-8")) <= max_bytes:
        return [text] if text else []
    chunks, current = [], ""
    for line in text.splitlines():
        candidate = line if not current else current + "\n" + line
        if len(candidate.encode("utf-8")) <= max_bytes:
            current = candidate
            continue
        if current:
            chunks.append(current)
        raw = line
        while len(raw.encode("utf-8")) > max_bytes:
            piece = ""
            for ch in raw:
                if len((piece + ch).encode("utf-8")) > max_bytes:
                    break
                piece += ch
            if not piece:
                break
            chunks.append(piece)
            raw = raw[len(piece):]
        current = raw
    if current:
        chunks.append(current)
    return chunks
