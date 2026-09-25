#!/usr/bin/env python3
"""Atualizador seguro do Traffic Analyzer baseado na Latest Release estável."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO = "alexpmr/traffic-analyzer"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
APP_DIR = Path("/opt/traffic-analyzer")
STATE_DIR = Path("/var/lib/traffic-analyzer")
REQUEST_FILE = STATE_DIR / "update-request.json"
STATUS_FILE = STATE_DIR / "update-status.json"
BACKUP_ROOT = STATE_DIR / "update-backups"
LOCK_FILE = Path("/run/traffic-analyzer-auto-update.lock")
SYSTEMD_DIR = Path("/etc/systemd/system")
LOCAL_SBIN = Path("/usr/local/sbin")
UNITS = [
    "traffic-analyzer.service",
    "traffic-analyzer.timer",
    "traffic-analyzer-map.service",
    "traffic-analyzer-auto-update.service",
    "traffic-analyzer-auto-update.path",
]
SBIN_FILES = ["traffic-analyzer-update"]
HEALTH_TIMEOUT = 75


def now_ms() -> int:
    return int(time.time() * 1000)


def read_json(path: Path, default=None):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else (default or {})
    except Exception:
        return default or {}


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    try:
        shutil.chown(path, user="traffic-analyzer", group="traffic-analyzer")
        path.chmod(0o640)
    except Exception:
        pass


def version_tuple(value: str):
    raw = str(value or "").strip().lower().lstrip("v")
    out = []
    for part in raw.split(".")[:4]:
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits or 0))
    while len(out) < 4:
        out.append(0)
    return tuple(out)


def current_version() -> str:
    try:
        return (APP_DIR / "VERSION").read_text(encoding="utf-8").strip() or "0.0.0"
    except Exception:
        return "0.0.0"


def request_json(url: str):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"Traffic-Analyzer-Updater/{current_version()}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def latest_release():
    release = request_json(LATEST_API)
    if release.get("draft") or release.get("prerelease"):
        raise RuntimeError("A Latest Release retornada pelo GitHub não é estável")
    tag = str(release.get("tag_name") or "").strip()
    version = tag[1:] if tag.lower().startswith("v") else tag
    if not version:
        raise RuntimeError("Latest Release sem tag de versão")
    wanted = f"traffic-analyzer-v{version}.zip"
    asset = next((a for a in release.get("assets", []) if a.get("name") == wanted), None)
    if not asset:
        asset = next((a for a in release.get("assets", []) if a.get("name") == "traffic-analyzer-latest.zip"), None)
    if not asset or not asset.get("browser_download_url"):
        raise RuntimeError(f"Asset ZIP não encontrado na Release v{version}")
    return {
        "version": version,
        "releaseUrl": release.get("html_url") or f"https://github.com/{REPO}/releases/tag/v{version}",
        "assetUrl": asset["browser_download_url"],
        "digest": str(asset.get("digest") or ""),
    }


def download(url: str, destination: Path) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Traffic-Analyzer-Updater"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as resp, destination.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            out.write(chunk)
    return h.hexdigest()


def backup_installation(previous: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_ROOT / f"{stamp}-v{previous}"
    backup.mkdir(parents=True, exist_ok=False)
    if APP_DIR.exists():
        shutil.copytree(APP_DIR, backup / "app", symlinks=True)
    units_dir = backup / "systemd"
    units_dir.mkdir()
    for name in UNITS:
        src = SYSTEMD_DIR / name
        if src.exists():
            shutil.copy2(src, units_dir / name)
    sbin_dir = backup / "sbin"
    sbin_dir.mkdir()
    for name in SBIN_FILES:
        src = LOCAL_SBIN / name
        if src.exists():
            shutil.copy2(src, sbin_dir / name)
    return backup


def restore_backup(backup: Path) -> None:
    app = backup / "app"
    if app.exists():
        shutil.rmtree(APP_DIR, ignore_errors=True)
        shutil.copytree(app, APP_DIR, symlinks=True)
    units_dir = backup / "systemd"
    for name in UNITS:
        saved = units_dir / name
        target = SYSTEMD_DIR / name
        if saved.exists():
            shutil.copy2(saved, target)
        elif target.exists():
            target.unlink()
    sbin_dir = backup / "sbin"
    for name in SBIN_FILES:
        saved = sbin_dir / name
        target = LOCAL_SBIN / name
        if saved.exists():
            shutil.copy2(saved, target)
    subprocess.run(["systemctl", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "enable", "--now", "traffic-analyzer.timer"], check=False)
    subprocess.run(["systemctl", "enable", "--now", "traffic-analyzer-auto-update.path"], check=False)
    subprocess.run(["systemctl", "restart", "traffic-analyzer-map.service"], check=False)


def map_port() -> int:
    path = Path("/etc/traffic-analyzer-map.env")
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("MAP_PORT="):
                return int(line.split("=", 1)[1].strip())
    except Exception:
        pass
    return 8788


def wait_healthy(expected_version: str) -> None:
    deadline = time.time() + HEALTH_TIMEOUT
    url = f"http://127.0.0.1:{map_port()}/health"
    last_error = ""
    while time.time() < deadline:
        try:
            if current_version() != expected_version:
                raise RuntimeError(f"VERSION instalada é {current_version()}, esperada {expected_version}")
            with urllib.request.urlopen(url, timeout=4) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                if resp.status == 200 and payload.get("ok"):
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(3)
    raise RuntimeError(f"Nova versão não ficou saudável em {HEALTH_TIMEOUT}s: {last_error}")


def trim_backups(keep: int = 3) -> None:
    try:
        dirs = sorted((p for p in BACKUP_ROOT.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in dirs[keep:]:
            shutil.rmtree(old, ignore_errors=True)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manual", action="store_true", help="Atualização manual para a Latest Release estável")
    args = parser.parse_args()

    if os.geteuid() != 0:
        print("ERRO: execute o atualizador como root.", file=sys.stderr)
        return 1

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    lock = LOCK_FILE.open("w")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("Outra atualização do Traffic Analyzer já está em andamento.")
        return 0

    request = {}
    processing = None
    if not args.manual:
        if not REQUEST_FILE.exists():
            return 0
        processing = REQUEST_FILE.with_name(f"update-request.processing.{os.getpid()}.json")
        os.replace(REQUEST_FILE, processing)
        request = read_json(processing, {})
    else:
        request = {"requestedBy": "manual", "rollbackEnabled": True}

    previous = current_version()
    target = ""
    release_url = ""
    backup = None
    rollback_enabled = bool(request.get("rollbackEnabled", True))
    reason = str(request.get("requestedBy") or ("manual" if args.manual else "automatic"))

    try:
        release = latest_release()
        target = release["version"]
        release_url = release["releaseUrl"]
        if version_tuple(target) <= version_tuple(previous):
            write_json(STATUS_FILE, {
                "state": "no_change",
                "previousVersion": previous,
                "targetVersion": target,
                "currentVersion": previous,
                "requestedBy": reason,
                "completedAtMs": now_ms(),
                "releaseUrl": release_url,
                "message": "Nenhuma atualização disponível.",
            })
            print(f"Traffic Analyzer já está atualizado: v{previous}")
            return 0

        requested_target = str(request.get("targetVersion") or "").strip()
        if requested_target and version_tuple(requested_target) > version_tuple(target):
            raise RuntimeError(f"Versão solicitada v{requested_target} é superior à Latest Release estável v{target}")

        write_json(STATUS_FILE, {
            "state": "running",
            "previousVersion": previous,
            "targetVersion": target,
            "requestedBy": reason,
            "startedAtMs": now_ms(),
            "releaseUrl": release_url,
            "message": f"Atualizando v{previous} para v{target}.",
        })

        with tempfile.TemporaryDirectory(prefix="traffic-analyzer-update-") as td:
            tmp = Path(td)
            archive = tmp / f"traffic-analyzer-v{target}.zip"
            actual_digest = download(release["assetUrl"], archive)
            expected_digest = release["digest"]
            if expected_digest.startswith("sha256:"):
                expected = expected_digest.split(":", 1)[1].strip().lower()
                if actual_digest.lower() != expected:
                    raise RuntimeError("Digest SHA-256 do pacote não confere com o publicado pelo GitHub")

            extract = tmp / "extract"
            extract.mkdir()
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(extract)
            candidates = list(extract.rglob("install.sh"))
            if not candidates:
                raise RuntimeError("install.sh não encontrado no pacote")
            source = candidates[0].parent
            package_version = (source / "VERSION").read_text(encoding="utf-8").strip()
            if package_version != target:
                raise RuntimeError(f"VERSION do pacote é {package_version}; esperada {target}")

            subprocess.run([sys.executable, "-m", "py_compile",
                            str(source / "traffic_analyzer.py"),
                            str(source / "traffic_analyzer_web.py"),
                            str(source / "auto_update.py")], check=True)

            backup = backup_installation(previous)
            subprocess.run(["bash", str(source / "install.sh")], cwd=str(source), check=True)
            wait_healthy(target)

        write_json(STATUS_FILE, {
            "state": "success",
            "previousVersion": previous,
            "targetVersion": target,
            "currentVersion": current_version(),
            "requestedBy": reason,
            "completedAtMs": now_ms(),
            "releaseUrl": release_url,
            "backupPath": str(backup) if backup else None,
            "message": f"Atualização concluída: v{previous} → v{target}.",
        })
        trim_backups()
        print(f"Traffic Analyzer atualizado com sucesso: v{previous} → v{target}")
        return 0

    except Exception as exc:
        rolled_back = False
        rollback_error = ""
        if rollback_enabled and backup is not None:
            try:
                restore_backup(backup)
                rolled_back = True
            except Exception as rb_exc:
                rollback_error = str(rb_exc)
        state = "rolled_back" if rolled_back else "failed"
        message = str(exc)
        if rollback_error:
            message += f" | Falha no rollback: {rollback_error}"
        write_json(STATUS_FILE, {
            "state": state,
            "previousVersion": previous,
            "targetVersion": target or str(request.get("targetVersion") or ""),
            "currentVersion": current_version(),
            "requestedBy": reason,
            "completedAtMs": now_ms(),
            "releaseUrl": release_url,
            "backupPath": str(backup) if backup else None,
            "message": message,
        })
        print(f"ERRO: {message}", file=sys.stderr)
        return 1
    finally:
        if processing is not None:
            try:
                processing.unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
