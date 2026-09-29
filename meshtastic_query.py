#!/usr/bin/env python3
"""Envia consultas Meshtastic pelo Virtual Node usando o cliente Python oficial.

O helper envia a solicitação e retorna imediatamente o packet.id em JSON.
A resposta é acompanhada pelo Traffic Analyzer através do Packet Monitor do
MeshMonitor, correlacionando decoded.request_id com o packet.id original.
"""

import argparse
import json
import sys
import time


def _build_nodeinfo_user(interface, mesh_pb2):
    info = interface.getMyNodeInfo() or {}
    src = info.get("user") or {}
    user = mesh_pb2.User()
    node_num = None
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


def send_request(args):
    from meshtastic.tcp_interface import TCPInterface
    from meshtastic.protobuf import mesh_pb2, portnums_pb2, telemetry_pb2

    started_ms = int(time.time() * 1000)
    interface = TCPInterface(
        hostname=args.host,
        portNumber=args.port,
        timeout=max(5, args.connect_timeout),
    )
    try:
        payload, port_num = _build_payload(
            args.action, interface, mesh_pb2, telemetry_pb2, portnums_pb2
        )
        packet = interface.sendData(
            payload,
            destinationId=args.dest,
            portNum=port_num,
            wantAck=False,
            wantResponse=True,
            channelIndex=args.channel,
        )
        packet_id = int(getattr(packet, "id", 0) or 0)
        if not packet_id:
            raise RuntimeError("O cliente Meshtastic não retornou packet.id")
        # Pequena janela para garantir que o frame foi entregue ao servidor TCP
        # antes do fechamento gracioso da conexão.
        time.sleep(0.15)
        return {
            "success": True,
            "backend": "virtual-node",
            "action": args.action,
            "destination": args.dest,
            "channel": args.channel,
            "packetId": packet_id,
            "sentAtMs": started_ms,
            "host": args.host,
            "port": args.port,
        }
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
    args = parser.parse_args()

    if args.channel < 0 or args.channel > 7:
        raise SystemExit("channel deve estar entre 0 e 7")

    try:
        result = send_request(args)
    except Exception as exc:
        result = {
            "success": False,
            "backend": "virtual-node",
            "error": str(exc),
            "action": args.action,
            "destination": args.dest,
            "host": args.host,
            "port": args.port,
        }
        print(json.dumps(result, ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
