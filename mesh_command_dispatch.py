#!/usr/bin/env python3
"""Despachante não bloqueante dos bots RF do Traffic Analyzer.

O callback de recepção Meshtastic executa apenas parsing e enqueue; operações
de rede/traceroute/clima/envio rodam em workers independentes por comando.
Não abre conexão Meshtastic adicional.
"""
from __future__ import annotations

import copy
import queue
import threading
import time

COMMANDS = ("ping", "clima")


class MeshCommandDispatcher:
    def __init__(self, *, process, seen, record, send, key, stop_event=None,
                 log=None, max_pending=12):
        self._process = process
        self._seen = seen
        self._record = record
        self._send = send
        self._key = key
        self._stop = threading.Event()
        self._server_stop = stop_event
        self._log = log or (lambda text: None)
        self._lock = threading.RLock()
        self._queues = {cmd: queue.Queue(maxsize=max_pending) for cmd in COMMANDS}
        self._recent = {}
        self._threads = []
        self._status = {
            "connected": False, "connectedAtMs": None, "lastError": None,
            "bots": {cmd: {"rxCount": 0, "txCount": 0, "errorCount": 0,
                            "lastRxMs": None, "lastTxMs": None,
                            "lastError": None, "processing": False}
                     for cmd in COMMANDS},
        }

    def start(self):
        for cmd in COMMANDS:
            thread = threading.Thread(target=self._run, args=(cmd,),
                                      name="mesh-bot-" + cmd, daemon=True)
            self._threads.append(thread)
            thread.start()
        return self

    def set_connected(self, connected, error=None):
        with self._lock:
            self._status["connected"] = bool(connected)
            if connected:
                self._status["connectedAtMs"] = int(time.time() * 1000)
                self._status["lastError"] = None
            elif error:
                self._status["lastError"] = str(error)[:320]

    def snapshot(self):
        with self._lock:
            result = copy.deepcopy(self._status)
            for cmd in COMMANDS:
                result["bots"][cmd]["pending"] = self._queues[cmd].qsize()
            return result

    def submit(self, row, command):
        """Nunca chamar traceroute, API de clima ou envio dentro do callback."""
        if command not in COMMANDS:
            return False
        key = str(self._key(row))
        sender = str(row.get("fromNodeNum") or row.get("fromNodeId") or "")
        semantic = sender + ":" + command
        now = time.monotonic()
        with self._lock:
            if self._stop.is_set() or (self._server_stop and self._server_stop.is_set()):
                return False
            self._recent = {k: expires for k, expires in self._recent.items() if expires > now}
            if ("packet:" + key) in self._recent or ("sender:" + semantic) in self._recent:
                return False
            try:
                self._queues[command].put_nowait((row, key))
            except queue.Full:
                self._status["bots"][command]["errorCount"] += 1
                self._status["bots"][command]["lastError"] = "Fila de comandos lotada"
                self._log("Comando " + command + " descartado: fila lotada")
                return False
            self._recent["packet:" + key] = now + 120.0
            # Rebroadcasts/duplicatas do mesmo comando na malha não devem
            # disparar nova consulta durante a propagação do pacote.
            self._recent["sender:" + semantic] = now + 8.0
            state = self._status["bots"][command]
            state["rxCount"] += 1
            state["lastRxMs"] = int(time.time() * 1000)
        return True

    def _record_error(self, row, command, exc):
        message = str(exc)[:400]
        with self._lock:
            state = self._status["bots"][command]
            state["errorCount"] += 1
            state["lastError"] = message
        try:
            self._record(row, command, "error", detail=message)
        except Exception as error:
            self._log("Falha ao registrar erro do bot " + command + ": " + str(error))
        self._log("Comando " + command.upper() + " falhou: " + message)

    def _run(self, command):
        q = self._queues[command]
        while not self._stop.is_set() and not (self._server_stop and self._server_stop.is_set()):
            try:
                row, key = q.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._lock:
                self._status["bots"][command]["processing"] = True
            try:
                if self._seen(key):
                    continue
                self._log("Comando recebido: " + command.upper() + " de " +
                          str(row.get("fromNodeId") or row.get("fromNodeNum") or "?") +
                          " via Meshtastic RF/live")
                def send_rf(text):
                    if self._stop.is_set() or (self._server_stop and self._server_stop.is_set()):
                        raise RuntimeError("Listener Meshtastic desconectado")
                    result = self._send(text, command)
                    with self._lock:
                        state = self._status["bots"][command]
                        state["txCount"] += 1
                        state["lastTxMs"] = int(time.time() * 1000)
                    return result
                self._process(row, command, send_func=send_rf)
                self._log("Comando processado: " + command.upper())
            except Exception as exc:
                self._record_error(row, command, exc)
            finally:
                with self._lock:
                    self._status["bots"][command]["processing"] = False
                q.task_done()

    def stop(self):
        self._stop.set()
        self.set_connected(False)
        for thread in self._threads:
            if thread is not threading.current_thread():
                thread.join(timeout=0.2)
