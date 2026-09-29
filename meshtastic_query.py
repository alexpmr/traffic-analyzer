#!/usr/bin/env python3
"""Executa uma consulta Meshtastic pelo Virtual Node e grava o estado em JSON.

O helper usa o cliente Python oficial Meshtastic. A correlação da resposta é
feita pelo próprio MeshInterface: o callback registrado para o packet.id só é
chamado quando chega uma resposta cujo decoded.request_id referencia aquele
packet.id (ou um NAK de roteamento correspondente).
"""

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path


def _write_status(path, payload):
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data["updatedAtMs"] = int(time.time() * 1000)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
    os.replace(tmp, target)


def _build_nodeinfo_user(interface, mesh_pb2):
    info = interface.getMyNodeInfo() or {}
    src = info.get("user") or {}
    user = mesh_pb2.User()
    try:
        node_num = int(getattr(interface.myInfo, "my_node_num", 0) or 0)
    except Exception:
        node_num = 0
    user.id = str(src.get("id") or (f"!{node_num:08x}" if node_num else "!00000000"))
    user.long_name = str(src.get("longName") or src.get("long_name") or "Traffic Analyzer")
    user.short_name = str(src.get("shortName") or src.get("short_name") or "TA")[:4]
    if "isLicensed" in src:
        user.is_licensed = bool(src.get("isLicensed"))
    elif "is_licensed" in src:
        user.is_licensed = bool(src.get("is_licensed"))
    return user


def _build_payload(action, interface, mesh_pb2, telemetry_pb2, portnums_pb2):
    if action == "position":
        return mesh_pb2.Position(), portnums_pb2.PortNum.POSITION_APP

    if action == "nodeinfo":
        return _build_nodeinfo_user(interface, mesh_pb2), portnums_pb2.PortNum.NODEINFO_APP

    if action == "neighbors":
        return mesh_pb2.NeighborInfo(), portnums_pb2.PortNum.NEIGHBORINFO_APP

    if action.startswith("telemetry_"):
        telemetry_type = action.split("_", 1)[1]
        t = telemetry_pb2.Telemetry()
        if telemetry_type == "environment":
            t.environment_metrics.CopyFrom(telemetry_pb2.EnvironmentMetrics())
        elif telemetry_type == "airQuality":
            t.air_quality_metrics.CopyFrom(telemetry_pb2.AirQualityMetrics())
        elif telemetry_type == "power":
            t.power_metrics.CopyFrom(telemetry_pb2.PowerMetrics())
        elif telemetry_type == "device":
            t.device_metrics.CopyFrom(telemetry_pb2.DeviceMetrics())
        else:
            raise ValueError(f"Tipo de telemetria inválido: {telemetry_type}")
        return t, portnums_pb2.PortNum.TELEMETRY_APP

    raise ValueError(f"Ação não suportada pelo Virtual Node: {action}")


def _port_name(value, portnums_pb2):
    if isinstance(value, str):
        return value
    try:
        return portnums_pb2.PortNum.Name(int(value))
    except Exception:
        return str(value or "")


def _safe_response(packet, portnums_pb2):
    packet = packet or {}
    decoded = packet.get("decoded") or {}
    port_name = _port_name(decoded.get("portnum"), portnums_pb2)
    routing = decoded.get("routing") or {}
    error_reason = routing.get("errorReason")
    if error_reason is None:
        error_reason = routing.get("error_reason")
    request_id = decoded.get("requestId")
    if request_id is None:
        request_id = decoded.get("request_id")

    return {
        "responsePort": port_name,
        "requestId": request_id,
        "routingErrorReason": error_reason,
        "fromNode": packet.get("from"),
        "toNode": packet.get("to"),
        "channel": packet.get("channel"),
        "rxSnr": packet.get("rxSnr", packet.get("rx_snr")),
        "rxRssi": packet.get("rxRssi", packet.get("rx_rssi")),
        "hopLimit": packet.get("hopLimit", packet.get("hop_limit")),
        "hopStart": packet.get("hopStart", packet.get("hop_start")),
        "receivedAtMs": int(time.time() * 1000),
    }


def run_query(args):
    from meshtastic.tcp_interface import TCPInterface
    from meshtastic.protobuf import mesh_pb2, portnums_pb2, telemetry_pb2

    started_ms = int(time.time() * 1000)
    base = {
        "queryId": args.query_id,
        "backend": "virtual-node",
        "action": args.action,
        "destination": args.dest,
        "channel": args.channel,
        "host": args.host,
        "port": args.port,
        "startedAtMs": started_ms,
    }
    _write_status(args.status_file, {**base, "success": True, "state": "connecting"})

    interface = TCPInterface(
        hostname=args.host,
        portNumber=args.port,
        timeout=max(5, args.connect_timeout),
    )
    event = threading.Event()
    response_holder = {}

    try:
        payload, port_num = _build_payload(
            args.action, interface, mesh_pb2, telemetry_pb2, portnums_pb2
        )

        def on_response(packet):
            safe = _safe_response(packet, portnums_pb2)
            port_name = safe.get("responsePort")
            reason = safe.get("routingErrorReason")
            if port_name == "ROUTING_APP":
                # NONE é ACK de roteamento, não a resposta de aplicação. Com
                # wantAck=False ele normalmente nem chega ao callback, mas não
                # encerramos a consulta caso apareça.
                if reason in (None, 0, "NONE", "0"):
                    return
                final = {
                    **base,
                    **safe,
                    "success": False,
                    "state": "routing_error",
                    "error": str(reason),
                }
            else:
                final = {
                    **base,
                    **safe,
                    "success": True,
                    "state": "received",
                }
            response_holder["result"] = final
            _write_status(args.status_file, final)
            event.set()

        packet = interface.sendData(
            payload,
            destinationId=args.dest,
            portNum=port_num,
            wantAck=False,
            wantResponse=True,
            onResponse=on_response,
            onResponseAckPermitted=False,
            channelIndex=args.channel,
        )
        packet_id = int(getattr(packet, "id", 0) or 0)
        if not packet_id:
            raise RuntimeError("O cliente Meshtastic não retornou packet.id")

        base["packetId"] = packet_id
        if not event.is_set():
            _write_status(
                args.status_file,
                {
                    **base,
                    "success": True,
                    "state": "waiting",
                    "sentAtMs": int(time.time() * 1000),
                },
            )

        if not event.wait(args.wait_timeout):
            result = {
                **base,
                "success": False,
                "state": "timeout",
                "error": f"Sem resposta correlacionada em {args.wait_timeout} s",
                "completedAtMs": int(time.time() * 1000),
            }
            _write_status(args.status_file, result)
            return result

        result = dict(response_holder.get("result") or {})
        result.setdefault("packetId", packet_id)
        result.setdefault("completedAtMs", int(time.time() * 1000))
        _write_status(args.status_file, result)
        return result
    finally:
        try:
            interface.close()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Traffic Analyzer Meshtastic Virtual Node query helper")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4404)
    parser.add_argument("--dest", required=True)
    parser.add_argument("--channel", type=int, default=0)
    parser.add_argument(
        "--action",
        required=True,
        choices=[
            "nodeinfo",
            "position",
            "neighbors",
            "telemetry_device",
            "telemetry_environment",
            "telemetry_airQuality",
            "telemetry_power",
        ],
    )
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument("--wait-timeout", type=int, default=30)
    parser.add_argument("--query-id", required=True)
    parser.add_argument("--status-file", required=True)
    args = parser.parse_args()

    if args.channel < 0 or args.channel > 7:
        raise SystemExit("channel deve estar entre 0 e 7")

    base = {
        "queryId": args.query_id,
        "backend": "virtual-node",
        "action": args.action,
        "destination": args.dest,
        "channel": args.channel,
        "host": args.host,
        "port": args.port,
    }
    try:
        result = run_query(args)
    except Exception as exc:
        result = {
            **base,
            "success": False,
            "state": "error",
            "error": str(exc),
            "completedAtMs": int(time.time() * 1000),
        }
        _write_status(args.status_file, result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return 1

    print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result.get("state") == "received" else 2


if __name__ == "__main__":
    sys.exit(main())
