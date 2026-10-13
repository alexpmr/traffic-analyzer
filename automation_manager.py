#!/usr/bin/env python3
"""Configuração segura e renderização das automações PING/CLIMA.

A configuração reside em /var/lib, não no diretório substituído por releases.
Não abre outra conexão Meshtastic: os dois bots usam o listener existente.
"""
from __future__ import annotations

import copy
import ipaddress
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit

_LOCK = threading.RLock()
_VARIABLE = re.compile(r"\{\{([a-z0-9_]+)\}\}")
_DEFAULT_PING_TEMPLATE = "{{mensagem_padrao}}"
_DEFAULT_CLIMA_TEMPLATE = "{{clima}}"
PING_VARIABLES = ("mensagem_padrao", "destino", "origem", "hora", "sinal", "qualidade", "saltos", "via", "nos_24h", "rota")
CLIMA_VARIABLES = ("clima",)
AUTOMATION_IDS = ("ping", "clima")


def defaults(*, ping_label="VHF3", ping_cooldown=30, ping_route_timeout=20,
             clima_cooldown=300, clima_api_url="http://127.0.0.1:8765/clima",
             clima_reply_gap=8):
    return {
        "ping": {
            "enabled": True,
            "label": str(ping_label),
            "cooldownSeconds": int(ping_cooldown),
            "routeTimeoutSeconds": int(ping_route_timeout),
            "template": _DEFAULT_PING_TEMPLATE,
        },
        "clima": {
            "enabled": True,
            "cooldownSeconds": int(clima_cooldown),
            "replyGapSeconds": float(clima_reply_gap),
            "apiUrl": str(clima_api_url),
            "template": _DEFAULT_CLIMA_TEMPLATE,
        },
    }


def _integer(value, name, low, high):
    if isinstance(value, bool):
        raise ValueError(f"{name}: use um número inteiro")
    try:
        num = int(value)
        if str(value).strip() != str(num):
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError(f"{name}: use um número inteiro")
    if num < low or num > high:
        raise ValueError(f"{name}: permitido de {low} a {high}")
    return num


def _float(value, name, low, high):
    if isinstance(value, bool):
        raise ValueError(f"{name}: número inválido")
    try:
        num = float(value)
    except (ValueError, TypeError):
        raise ValueError(f"{name}: número inválido")
    if not (low <= num <= high):
        raise ValueError(f"{name}: permitido de {low} a {high}")
    return num


def _template(value, allowed, required):
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError("Modelo de resposta deve ter até 2.000 caracteres")
    if not value.strip():
        raise ValueError("O modelo de resposta não pode estar vazio")
    found = set(_VARIABLE.findall(value))
    if required not in found:
        raise ValueError(f"Modelo deve incluir {{{{{required}}}}}")
    unknown = found - set(allowed)
    if unknown:
        raise ValueError("Variáveis desconhecidas: " + ", ".join(sorted(unknown)))
    # Reject unmatched double braces: avoid accidentally transmitting placeholders.
    if "{{" in _VARIABLE.sub("", value) or "}}" in _VARIABLE.sub("", value):
        raise ValueError("Marcadores {{ }} inválidos")
    return value


def _api_url(value):
    url = str(value).strip()
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or len(url) > 256:
        raise ValueError("API CLIMA deve usar HTTP local sem credenciais")
    host = parsed.hostname.lower()
    if host != "localhost":
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            raise ValueError("API CLIMA: use localhost ou 127.0.0.1")
        if not addr.is_loopback:
            raise ValueError("API CLIMA deve estar em loopback")
    if parsed.port is not None and not (1 <= parsed.port <= 65535):
        raise ValueError("Porta inválida")
    return url


def validate_bot(bot, submitted, existing):
    if bot not in AUTOMATION_IDS:
        raise ValueError("Automação desconhecida")
    if not isinstance(submitted, dict):
        raise ValueError("Configuração inválida")
    allowed = set(existing[bot])
    if set(submitted) - allowed:
        raise ValueError("Campos não permitidos: " + ", ".join(sorted(set(submitted) - allowed)))
    value = copy.deepcopy(existing[bot])
    value.update(submitted)
    if type(value["enabled"]) is not bool:
        raise ValueError("Ativação deve ser verdadeira ou falsa")
    value["cooldownSeconds"] = _integer(value["cooldownSeconds"], "Cooldown", 0, 86400)
    if bot == "ping":
        label = str(value["label"]).strip()
        if not (1 <= len(label) <= 45):
            raise ValueError("Identificação deve ter de 1 a 45 caracteres")
        value["label"] = label
        value["routeTimeoutSeconds"] = _integer(value["routeTimeoutSeconds"], "Timeout de rota", 5, 90)
        value["template"] = _template(value["template"], PING_VARIABLES, "mensagem_padrao" if "{{mensagem_padrao}}" in value["template"] else "origem")
    else:
        value["replyGapSeconds"] = _float(value["replyGapSeconds"], "Intervalo entre mensagens", 0, 60)
        value["apiUrl"] = _api_url(value["apiUrl"])
        value["template"] = _template(value["template"], CLIMA_VARIABLES, "clima")
    return value


def load(path: Path, fallback):
    settings = copy.deepcopy(fallback)
    with _LOCK:
        if not Path(path).exists():
            return settings
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            for bot in AUTOMATION_IDS:
                if isinstance(raw.get(bot), dict):
                    # Saved settings receive validation, and missing fields retain defaults.
                    settings[bot] = validate_bot(bot, raw[bot], settings)
            return settings
        except (ValueError, OSError, TypeError, KeyError) as exc:
            # Do not silently enable bots with defaults after corrupt config.
            raise RuntimeError(f"Configuração de automações inválida: {exc}") from exc


def save(path: Path, fallback, bot, patch, username="admin"):
    with _LOCK:
        config = load(path, fallback)
        config[bot] = validate_bot(bot, patch, config)
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + f".{os.getpid()}.tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp, 0o600)
            os.replace(tmp, target)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        # No secrets or message texts in audit history.
        audit = target.with_name("automation-audit.jsonl")
        with open(audit, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": int(time.time() * 1000), "actor": str(username)[:60],
                                "bot": bot, "changedKeys": sorted(patch.keys())}, ensure_ascii=False) + "\n")
        os.chmod(audit, 0o600)
        return config


def _fields(default_text):
    lines = str(default_text).splitlines()
    by_prefix = {
        "origem": "Origem:", "hora": "Hora:", "sinal": "Sinal recebido:",
        "qualidade": "Qualidade do sinal:", "via": "Via:",
        "nos_24h": "Nós ouvidos em 24 h:", "rota": "Teste de rota:",
    }
    mapping = {k: "não disponível" for k in PING_VARIABLES}
    mapping["mensagem_padrao"] = str(default_text)
    mapping["destino"] = lines[0].removeprefix("PING ").strip() if lines else "VHF3"
    for key, prefix in by_prefix.items():
        row = next((x for x in lines if x.startswith(prefix)), None)
        if row:
            mapping[key] = row[len(prefix):].strip()
    hop = next((x for x in lines if x.startswith("Saltos até ")), None)
    if hop:
        mapping["saltos"] = hop.split(":", 1)[-1].strip()
    return mapping


def render_ping(template, default_text):
    return _render(template, _fields(default_text))


def _render(template, mapping):
    return _VARIABLE.sub(lambda match: mapping.get(match.group(1), ""), template).strip()


def render_clima(template, responses):
    if not isinstance(responses, list) or not responses:
        raise ValueError("API CLIMA não retornou mensagens")
    return _render(template, {"clima": "\n".join(str(x).strip() for x in responses if str(x).strip())})


def preview(bot, config, default_ping_text=None, clima_responses=None):
    from mesh_commands import split_utf8
    if bot == "ping":
        raw = render_ping(config["template"], default_ping_text or "")
    elif bot == "clima":
        raw = render_clima(config["template"], clima_responses or [])
    else:
        raise ValueError("Automação desconhecida")
    parts = split_utf8(raw, 200)
    if not parts or len(parts) > 12:
        raise ValueError("Resposta excede o limite de 12 blocos Meshtastic")
    return {"text": raw, "parts": parts, "bytes": len(raw.encode("utf-8")), "transmits": False}
