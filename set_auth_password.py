#!/usr/bin/env python3
"""Configura a autenticação administrativa do Traffic Analyzer."""

from __future__ import annotations

import base64
import getpass
import hashlib
import os
import re
import subprocess
import tempfile
from pathlib import Path

ENV_PATH = Path(os.environ.get("TRAFFIC_ANALYZER_MAP_ENV", "/etc/traffic-analyzer-map.env"))
ITERATIONS = 600_000
USER_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


def password_hash(password: str) -> str:
    salt = os.urandom(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    return "pbkdf2_sha256$" + str(ITERATIONS) + "$" + base64.urlsafe_b64encode(salt).decode("ascii").rstrip("=") + "$" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def read_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def update_env(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    done: set[str] = set()
    out: list[str] = []
    for raw in lines:
        if "=" in raw and not raw.lstrip().startswith("#"):
            key = raw.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                done.add(key)
                continue
        out.append(raw)
    for key, value in updates.items():
        if key not in done:
            out.append(f"{key}={value}")
    data = "\n".join(out).rstrip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


def main() -> int:
    if os.geteuid() != 0:
        raise SystemExit("Execute como root: sudo traffic-analyzer-set-password")

    current = read_values(ENV_PATH)
    default_user = current.get("TA_AUTH_USER", "admin") or "admin"
    typed = input(f"Usuário administrador [{default_user}]: ").strip()
    username = typed or default_user
    if not USER_RE.fullmatch(username):
        raise SystemExit("Usuário inválido. Use apenas letras, números, ponto, _, @ ou -.")

    password = getpass.getpass("Nova senha (mínimo 10 caracteres): ")
    if len(password) < 10:
        raise SystemExit("A senha precisa ter pelo menos 10 caracteres.")
    confirm = getpass.getpass("Repita a nova senha: ")
    if password != confirm:
        raise SystemExit("As senhas não conferem.")

    update_env(
        ENV_PATH,
        {
            "TA_AUTH_ENABLED": "true",
            "TA_AUTH_USER": username,
            "TA_AUTH_PASSWORD_HASH": password_hash(password),
            "TA_AUTH_SESSION_HOURS": current.get("TA_AUTH_SESSION_HOURS", "12") or "12",
            "TA_AUTH_SECURE_COOKIE": current.get("TA_AUTH_SECURE_COOKIE", "auto") or "auto",
        },
    )
    os.chmod(ENV_PATH, 0o600)

    print(f"Autenticação ativada para o usuário {username!r}.")
    try:
        subprocess.run(
            ["systemctl", "restart", "traffic-analyzer-map.service"],
            check=True,
            timeout=30,
        )
        print("Serviço traffic-analyzer-map reiniciado.")
    except Exception as exc:
        print(f"AVISO: não foi possível reiniciar o serviço automaticamente: {exc}")
        print("Execute: sudo systemctl restart traffic-analyzer-map.service")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
