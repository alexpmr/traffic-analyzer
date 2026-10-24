#!/usr/bin/env python3
"""Funções puras dos comandos de malha integrados ao Traffic Analyzer."""

from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.error
import urllib.parse
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


_TRACE_PLACEHOLDERS = {0, 1, 2, 3, 255, 65535, 0xFFFFFFFF}
_TRACE_UNKNOWN_SNR_DB = -32.0


def _trace_list(raw) -> list:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) if raw.strip() else []
        except ValueError:
            return []
    return raw if isinstance(raw, list) else []


def _trace_leg(start: int, intermediate, end: int, snr_raw, label) -> list[str]:
    """Um enlace por linha (start → intermediários → end), com o SNR (valor do rádio ÷ 4) de quem recebeu."""
    hops = []
    for value in _trace_list(intermediate):
        try:
            hops.append(int(value) & 0xFFFFFFFF)
        except (TypeError, ValueError):
            hops.append(None)
    snrs = _trace_list(snr_raw)
    name = lambda num: "?" if num is None or num in _TRACE_PLACEHOLDERS else label(num)
    links = []
    previous = label(start)
    for idx, num in enumerate(hops + [end]):
        current = label(end) if idx == len(hops) else name(num)
        line = f"{previous} → {current}"
        try:
            snr = float(snrs[idx]) / 4.0
            if abs(snr - _TRACE_UNKNOWN_SNR_DB) < 1e-9:
                raise ValueError
            line += f": {snr:.1f} dB"
        except (IndexError, TypeError, ValueError):
            pass
        links.append(line)
        previous = current
    return links


def format_traceroute_lines(trace: dict | None, label, timeout_seconds: int | None = None) -> list[str]:
    """Linhas de ida e volta de um traceroute do MeshMonitor para a resposta do PING.

    ``label`` converte nodeNum em nome curto. A volta só é mostrada quando o
    registro a traz; nunca é inferida invertendo a ida.
    """
    if not trace:
        wait = f" em {int(timeout_seconds)} s" if timeout_seconds else ""
        return [f"Traceroute: sem resposta{wait}"]
    try:
        start = int(trace.get("fromNodeNum")) & 0xFFFFFFFF
        end = int(trace.get("toNodeNum")) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return ["Traceroute: resposta inválida"]
    lines = ["Rota de ida:", *_trace_leg(start, trace.get("route"), end, trace.get("snrTowards"), label)]
    if _trace_list(trace.get("routeBack")) or _trace_list(trace.get("snrBack")):
        lines += ["Rota de volta:", *_trace_leg(end, trace.get("routeBack"), start, trace.get("snrBack"), label)]
    else:
        lines.append("Rota de volta: não disponível")
    return lines


def format_ping_message(*, destination_label: str, origin: str, message: dict,
                        heard_nodes_24h: int | None, route_text: str = "",
                        route_lines: list[str] | None = None) -> str:
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
    if route_lines:
        # Traceroute de ida e volta ao final, em bloco próprio (a linha em branco inicia nova mensagem).
        lines.append("")
        lines.extend(route_lines)
    else:
        lines.append(f"Teste de rota: {route_text or 'sem resposta'}")
    return "\n".join(lines)


_WIND_MS = re.compile(r"(?<![\d.,/])(\d+(?:[.,]\d+)?(?:/\d+(?:[.,]\d+)?)*)\s*m/s\b", re.IGNORECASE)


def _wind_kmh(text: str) -> str:
    """Converte velocidades em m/s (inclusive "0.7/1.0/1.8m/s") para km/h."""
    def convert(match):
        values = [float(x.replace(",", ".")) * 3.6 for x in match.group(1).split("/")]
        return "/".join(f"{v:.1f}" for v in values) + " km/h"
    return _WIND_MS.sub(convert, text)


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
    text = _wind_kmh(text)
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


CLIMA_BLOCK_TITLES = (
    "Temperatura e umidade",
    "Luz e vento",
    "Chuva",
    "Raios",
    "Previsão do tempo",
)

# Seções compactas da API Tempest -> índice do bloco enviado pela malha.
_CLIMA_SECTION_BLOCK = {"CLIMA": 0, "LUZ/VENTO": 1, "CHUVA": 2, "RAIOS/TEMPEST": 3, "RAIOS/TEMPESTADE": 3}
# Linhas de diagnóstico da estação que não fazem parte do bloco de raios.
_CLIMA_DROPPED = ("Bateria:", "Dados atualizados")

HA_CONDITIONS = {
    "clear-night": "Céu limpo", "cloudy": "Nublado", "exceptional": "Condição excepcional",
    "fog": "Neblina", "hail": "Granizo", "lightning": "Raios", "lightning-rainy": "Chuva com raios",
    "partlycloudy": "Parcialmente nublado", "pouring": "Chuva forte", "rainy": "Chuva",
    "snowy": "Neve", "snowy-rainy": "Chuva e neve", "sunny": "Ensolarado",
    "windy": "Ventoso", "windy-variant": "Ventoso e nublado",
}
_WEEKDAYS = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
_HA_ENTITY = re.compile(r"^[a-z_]+\.[a-z0-9_]+$")


def build_clima_blocks(responses, lightning=None, forecast=None) -> list[str]:
    """Organiza as respostas compactas da API CLIMA nos blocos enviados pela malha.

    ``lightning`` é a situação de "Raios próximos" e ``forecast`` as linhas da
    previsão; ambos vêm do Home Assistant e são omitidos quando ``None``.
    Mensagens que não pertencem a uma seção conhecida (alertas) viram blocos extras.
    """
    blocks = [[] for _ in CLIMA_BLOCK_TITLES]
    extras = []
    for raw in responses or []:
        raw = str(raw or "").replace("\r", "").strip()
        segments = [x.strip() for x in re.split(r"\s*\|\s*", raw) if x.strip()]
        if not segments:
            continue
        head = segments[0].upper()
        index = 0 if head.startswith("CLIMA") else _CLIMA_SECTION_BLOCK.get(head)
        if index is None:
            text = normalize_clima_message(raw)
            if text:
                extras.append(text)
            continue
        for segment in segments[1:]:
            line = _expand_clima_segment(segment)
            line = re.sub(r":\s*--$", ": sem registro", line)
            if line and not line.startswith(_CLIMA_DROPPED):
                blocks[index].append(line)
    if lightning is not None:
        blocks[3].insert(0, "Raios próximos: " + str(lightning))
    if forecast:
        blocks[4].extend(str(x) for x in forecast if str(x).strip())
    out = ["\n".join([CLIMA_BLOCK_TITLES[i]] + lines) for i, lines in enumerate(blocks) if lines] + extras
    # A malha pode entregar os blocos fora de ordem; a numeração no título deixa a sequência clara.
    numbered = []
    for index, block in enumerate(out, 1):
        title, _, body = block.partition("\n")
        numbered.append(f"{title} ({index}/{len(out)})" + ("\n" + body if body else ""))
    return numbered


def _ha_request(base: str, token: str, path: str, timeout: float, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(str(base).rstrip("/") + path, data=data, method="GET" if data is None else "POST",
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                          "User-Agent": "TrafficAnalyzer-MeshCommands/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read(500_001)
    if len(raw) > 500_000:
        raise RuntimeError("Resposta do Home Assistant excede o limite")
    return json.loads(raw) if raw else {}


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return f"{number:.0f}"


def format_forecast(state: dict, daily: list, today: _dt.date | None = None, conditions: dict | None = None) -> list[str]:
    """Linhas curtas: condição atual e previsão diária de hoje e amanhã."""
    today = today or _dt.date.today()
    conditions = HA_CONDITIONS if conditions is None else conditions
    attrs = state.get("attributes") or {}
    unit = attrs.get("temperature_unit") or "°C"
    lines = []
    condition = conditions.get(str(state.get("state") or ""), "")
    temp = _num(attrs.get("temperature"))
    if condition or temp:
        lines.append("Agora: " + ", ".join(x for x in (condition, f"{temp} {unit}" if temp else "") if x))
    for item in (daily or []):
        if len(lines) >= 3 or not isinstance(item, dict):
            break
        try:
            day = _dt.date.fromisoformat(str(item.get("datetime") or "")[:10])
        except ValueError:
            continue
        if day < today:
            continue
        label = "Hoje" if day == today else "Amanhã" if day == today + _dt.timedelta(days=1) \
            else f"{_WEEKDAYS[day.weekday()]} {day:%d/%m}"
        parts = [conditions.get(str(item.get("condition") or ""), "")]
        high, low = _num(item.get("temperature")), _num(item.get("templow"))
        if high and low:
            parts.append(f"{low} a {high} {unit}")
        elif high:
            parts.append(f"máx. {high} {unit}")
        rain = _num(item.get("precipitation_probability"))
        if rain is not None:
            parts.append(f"chuva {rain}%")
        lines.append(label + ": " + ", ".join(x for x in parts if x))
    return lines


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
# Códigos WMO usados pelo Open-Meteo.
WMO_CONDITIONS = {
    "0": "Céu limpo", "1": "Predomínio de sol", "2": "Parcialmente nublado", "3": "Nublado",
    "45": "Neblina", "48": "Neblina", "51": "Garoa fraca", "53": "Garoa", "55": "Garoa forte",
    "56": "Garoa congelante", "57": "Garoa congelante", "61": "Chuva fraca", "63": "Chuva", "65": "Chuva forte",
    "66": "Chuva congelante", "67": "Chuva congelante", "71": "Neve", "73": "Neve", "75": "Neve", "77": "Neve",
    "80": "Pancadas fracas", "81": "Pancadas de chuva", "82": "Pancadas fortes", "85": "Neve", "86": "Neve",
    "95": "Trovoadas", "96": "Trovoadas com granizo", "99": "Trovoadas com granizo",
}


def fetch_open_meteo_forecast(latitude: float, longitude: float, timeout: float = 6.0,
                              errors: list | None = None, today: _dt.date | None = None) -> list[str] | None:
    """Previsão sem chave de API (Open-Meteo): condição atual, hoje e amanhã."""
    errors = [] if errors is None else errors
    try:
        lat, lon = float(latitude), float(longitude)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("coordenadas fora do intervalo")
        query = urllib.parse.urlencode({
            "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "timezone": "auto", "forecast_days": 3,
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        })
        req = urllib.request.Request(OPEN_METEO_URL + "?" + query, headers={"User-Agent": "TrafficAnalyzer-MeshCommands/1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read(200_001))
        current, daily = body.get("current") or {}, body.get("daily") or {}
        state = {"state": str(current.get("weather_code", "")),
                 "attributes": {"temperature": current.get("temperature_2m"), "temperature_unit": "°C"}}
        column = lambda key: list(daily.get(key) or [])
        times = column("time")
        pad = lambda values: values + [None] * (len(times) - len(values))
        days = [{"datetime": t, "condition": "" if c is None else str(c), "temperature": hi, "templow": lo,
                 "precipitation_probability": rain}
                for t, c, hi, lo, rain in zip(times, pad(column("weather_code")), pad(column("temperature_2m_max")),
                                              pad(column("temperature_2m_min")), pad(column("precipitation_probability_max")))]
        lines = format_forecast(state, days, today=today, conditions=WMO_CONDITIONS)
        if not lines:
            raise ValueError("resposta sem previsão")
        return lines
    except Exception as exc:
        reason = f"HTTP {exc.code}" if isinstance(exc, urllib.error.HTTPError) else \
            f"inacessível: {exc.reason}" if isinstance(exc, urllib.error.URLError) else str(exc)[:200]
        errors.append("Open-Meteo: " + reason)
        return None


def _ha_error(exc) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        return {401: "token recusado (HTTP 401)", 404: "entidade não encontrada (HTTP 404)"}.get(exc.code, f"HTTP {exc.code}")
    if isinstance(exc, urllib.error.URLError):
        return f"Home Assistant inacessível: {exc.reason}"
    return str(exc)[:200]


def fetch_home_assistant_weather(base: str, token: str, lightning_entity: str, forecast_entity: str,
                                 timeout: float = 6.0, errors: list | None = None):
    """Retorna (descargas próximas, linhas da previsão) a partir do Home Assistant.

    Falhas são independentes: uma entidade indisponível não impede a outra.
    O motivo de cada falha é acrescentado a ``errors``, quando informado.
    """
    errors = [] if errors is None else errors
    lightning = forecast = None
    for name, entity in (("raios", lightning_entity), ("previsão", forecast_entity)):
        if entity and not _HA_ENTITY.match(entity):
            errors.append(f"Entidade de {name} inválida: {entity}")
    if lightning_entity and _HA_ENTITY.match(lightning_entity):
        try:
            state = str(_ha_request(base, token, "/api/states/" + lightning_entity, timeout).get("state") or "")
            # A entidade indica se há raios próximos (on = risco, off = seguro).
            lightning = {"on": "SIM, situação de risco", "off": "não, situação segura"}.get(state, "indisponível")
            if lightning == "indisponível":
                errors.append(f"{lightning_entity}: estado '{state}'")
        except Exception as exc:
            lightning = "indisponível"
            errors.append(f"{lightning_entity}: {_ha_error(exc)}")
    if forecast_entity and _HA_ENTITY.match(forecast_entity):
        try:
            state = _ha_request(base, token, "/api/states/" + forecast_entity, timeout)
            daily = (state.get("attributes") or {}).get("forecast")
            if not isinstance(daily, list):
                # Home Assistant 2024.3+ só expõe a previsão pelo serviço weather.get_forecasts.
                try:
                    body = _ha_request(base, token, "/api/services/weather/get_forecasts?return_response", timeout,
                                       {"entity_id": forecast_entity, "type": "daily"})
                    daily = (((body or {}).get("service_response") or {}).get(forecast_entity) or {}).get("forecast")
                except Exception as exc:
                    daily = None
                    errors.append(f"weather.get_forecasts: {_ha_error(exc)}")
            forecast = format_forecast(state, daily if isinstance(daily, list) else []) or ["Previsão indisponível"]
        except Exception as exc:
            forecast = ["Previsão indisponível"]
            errors.append(f"{forecast_entity}: {_ha_error(exc)}")
    return lightning, forecast


def fetch_clima_responses(url: str, timeout: float = 6.0, home_assistant: dict | None = None,
                          forecast_location: tuple | None = None) -> list[str]:
    req = urllib.request.Request(str(url), headers={"User-Agent": "TrafficAnalyzer-MeshCommands/1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    body = json.loads(raw) if raw else {}
    responses = body.get("responses") if isinstance(body, dict) else None
    if not isinstance(responses, list):
        raise RuntimeError("Resposta inválida da API de clima")
    lightning = forecast = None
    ha = home_assistant or {}
    if ha.get("url") and ha.get("token"):
        lightning, forecast = fetch_home_assistant_weather(
            ha["url"], ha["token"], ha.get("lightningEntity", ""), ha.get("forecastEntity", ""), timeout)
    # Sem previsão do Home Assistant, usa o Open-Meteo (não exige conta nem token).
    if forecast_location and (not forecast or forecast == ["Previsão indisponível"]):
        forecast = fetch_open_meteo_forecast(*forecast_location, timeout=timeout) or forecast
    out = build_clima_blocks([str(x) for x in responses if str(x).strip()], lightning, forecast)
    if not out:
        raise RuntimeError("API de clima não retornou mensagens")
    return out[:8]


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
