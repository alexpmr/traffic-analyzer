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


def link_quality_label(snr) -> str | None:
    try:
        value = float(snr)
    except (TypeError, ValueError):
        return None
    if value >= 7:
        return "Excelente"
    if value >= 3:
        return "Boa"
    if value >= 0:
        return "Regular"
    return "Fraca"


def format_ping_message(*, destination_label: str, origin: str, message: dict,
                        heard_nodes_24h: int | None, route_text: str,
                        response_seconds: float | None = None) -> str:
    lines = [f"PING {destination_label}", f"Origem: {origin}"]
    lines.append(f"Horário do recebimento: {local_time_text(message.get('receivedAt') or message.get('createdAt') or message.get('timestamp'))}")
    if response_seconds is not None:
        try:
            value = max(0.0, float(response_seconds))
            lines.append(f"Tempo de resposta: {value:.1f} segundos")
        except (TypeError, ValueError):
            pass

    rssi = message.get("rxRssi")
    snr = message.get("rxSnr")
    try:
        if rssi is not None:
            lines.append(f"Sinal recebido: {float(rssi):.0f} dBm")
    except (TypeError, ValueError):
        pass
    try:
        if snr is not None:
            lines.append(f"Relação sinal-ruído: {float(snr):.1f} dB")
            quality = link_quality_label(snr)
            if quality:
                lines.append(f"Qualidade estimada do enlace: {quality}")
    except (TypeError, ValueError):
        pass

    lines.append(format_hops(hops_from_message(message), destination_label))
    lines.append("Transporte: MQTT" if bool(message.get("viaMqtt")) else "Transporte: LoRa")
    if heard_nodes_24h is not None:
        lines.append(f"Nós ouvidos nas últimas 24 horas: {int(heard_nodes_24h)}")
    lines.append(f"Teste de rota: {route_text or 'sem resposta'}")
    return "\n".join(lines)


def normalize_clima_text(text: str) -> str:
    """Expande abreviações comuns e preserva uma informação por linha."""
    value = str(text or "").strip()
    replacements = (
        (r"(?im)^Temp(?:\.|eratura)?\s*:", "Temperatura:"),
        (r"(?im)^Sens(?:\.|ação térmica)?\s*:", "Sensação térmica:"),
        (r"(?im)^Umid(?:\.|ade)?\s*:", "Umidade relativa:"),
        (r"(?im)^Press(?:\.|ão)?\s*:", "Pressão atmosférica:"),
        (r"(?im)^Vento\s*:", "Velocidade do vento:"),
        (r"(?im)^Raj(?:\.|ada)?\s*:", "Rajada de vento:"),
        (r"(?im)^Dir(?:\.|eção)?\s*:", "Direção do vento:"),
        (r"(?im)^Chuva\s*:", "Precipitação:"),
        (r"(?im)^UV\s*:", "Índice ultravioleta:"),
        (r"(?im)^Raios?\s*:", "Atividade de raios:"),
    )
    for pattern, replacement in replacements:
        value = re.sub(pattern, replacement, value)
    # APIs antigas às vezes devolvem campos separados por " | " ou " • ".
    value = re.sub(r"\s+(?:\||•)\s+", "\n", value)
    return value


def portable_line_breaks(text: str) -> str:
    """Usa separador Unicode de linha para clientes que colapsam LF simples."""
    return re.sub(r"\r?\n", "\u2028", str(text or ""))


def fetch_clima_responses(url: str, timeout: float = 6.0) -> list[str]:
    req = urllib.request.Request(str(url), headers={"User-Agent": "TrafficAnalyzer-MeshCommands/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    body = json.loads(raw) if raw else {}
    responses = body.get("responses") if isinstance(body, dict) else None
    if not isinstance(responses, list):
        raise RuntimeError("Resposta inválida da API de clima")
    out = [normalize_clima_text(str(x)) for x in responses if str(x).strip()]
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
