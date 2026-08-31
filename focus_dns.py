#!/usr/bin/env python3
"""UDP DNS sinkhole for focus-mode suffix blocks.

This process is the resolver for blocked suffixes only. systemd-resolved (or
/etc/resolv.conf takeover) sends those names here. Upstream queries go to the
nameservers captured before apply, never back through the system stub, so the
sinkhole cannot intercept itself.
"""

from __future__ import annotations

import argparse
import os
import select
import signal
import socket
import sys
from pathlib import Path

SINKHOLE_A = bytes([0, 0, 0, 0])
SINKHOLE_AAAA = bytes(16)


def suffix_matches(hostname: str, suffix: str) -> bool:
    name = hostname.rstrip(".").lower()
    tail = suffix.rstrip(".").lower()
    return name == tail or name.endswith("." + tail)


def load_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_suffixes(path: Path) -> list[str]:
    return [item.lower() for item in load_lines(path)]


def parse_qname(data: bytes) -> tuple[str, int] | None:
    if len(data) < 12:
        return None
    pos = 12
    labels: list[str] = []
    while pos < len(data):
        length = data[pos]
        if length == 0:
            pos += 1
            break
        if length & 0xC0:
            return None
        pos += 1
        if pos + length > len(data):
            return None
        labels.append(data[pos : pos + length].decode("ascii", "replace"))
        pos += length
    if pos + 4 > len(data):
        return None
    return ".".join(labels).rstrip(".").lower(), pos + 4


def blocked_qname(qname: str, suffixes: list[str]) -> bool:
    return any(suffix_matches(qname, suffix) for suffix in suffixes)


def sinkhole_response(query: bytes, qtype: int) -> bytes:
    header = bytearray(query[:12])
    header[2] = 0x81
    header[3] = 0x80
    header[6:8] = b"\x00\x01"
    header[8:10] = b"\x00\x00"
    header[10:12] = b"\x00\x00"
    question = query[12:]
    rdata = SINKHOLE_AAAA if qtype == 28 else SINKHOLE_A
    answer = b"\xc0\x0c" + qtype.to_bytes(2, "big") + b"\x00\x01" + (30).to_bytes(4, "big")
    answer += len(rdata).to_bytes(2, "big") + rdata
    return bytes(header) + question + answer


def query_type(data: bytes, question_end: int) -> int:
    if question_end < 4:
        return 1
    return int.from_bytes(data[question_end - 4 : question_end - 2], "big")


def _usable_upstream(server: str) -> bool:
    return not server.startswith("127.") and server not in {":1", "::1"}


def load_upstreams(path: Path | None) -> list[str]:
    if path is not None and path.exists():
        servers = [item for item in load_lines(path) if _usable_upstream(item)]
        if servers:
            return servers
    for candidate in (Path("/run/systemd/resolve/resolv.conf"), Path("/etc/resolv.conf")):
        if not candidate.exists():
            continue
        servers = []
        for line in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0] != "nameserver":
                continue
            server = parts[1]
            if not _usable_upstream(server):
                continue
            servers.append(server)
        if servers:
            return servers
    return []


def forward(query: bytes, servers: list[str]) -> bytes | None:
    for server in servers:
        family = socket.AF_INET6 if ":" in server else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            sock.settimeout(1.5)
            sock.sendto(query, (server, 53))
            data, _addr = sock.recvfrom(4096)
            return data
        except OSError:
            continue
        finally:
            sock.close()
    return None


def serve(bind: str, port: int, suffix_path: Path, upstream_path: Path | None = None) -> None:
    suffixes = {"items": load_suffixes(suffix_path)}
    servers = {"items": load_upstreams(upstream_path)}

    def reload_files(_signum, _frame) -> None:
        suffixes["items"] = load_suffixes(suffix_path)
        servers["items"] = load_upstreams(upstream_path)

    try:
        signal.signal(signal.SIGHUP, reload_files)
    except ValueError:
        pass
    sockets = []
    for family, address in ((socket.AF_INET, bind), (socket.AF_INET6, "::1")):
        sock = socket.socket(family, socket.SOCK_DGRAM)
        if family == socket.AF_INET6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        try:
            sock.bind((address, port))
        except OSError:
            sock.close()
            continue
        sockets.append(sock)
    if not sockets:
        raise SystemExit("could not bind the suffix DNS sinkhole")
    while True:
        readable, _w, _x = select.select(sockets, [], [], 1)
        for sock in readable:
            try:
                data, addr = sock.recvfrom(4096)
            except OSError:
                continue
            parsed = parse_qname(data)
            if parsed is None:
                continue
            qname, end = parsed
            qtype = query_type(data, end)
            if blocked_qname(qname, suffixes["items"]):
                sock.sendto(sinkhole_response(data, qtype), addr)
                continue
            reply = forward(data, servers["items"])
            if reply:
                sock.sendto(reply, addr)


def daemonize() -> None:
    if os.fork() > 0:
        raise SystemExit(0)
    os.setsid()
    if os.fork() > 0:
        raise SystemExit(0)
    sys.stdin.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suffixes", required=True)
    parser.add_argument("--upstreams")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=53553)
    parser.add_argument("--pid")
    parser.add_argument("--daemon", action="store_true")
    args = parser.parse_args()
    if args.daemon:
        daemonize()
    if args.pid:
        Path(args.pid).write_text(str(os.getpid()) + "\n", encoding="utf-8")
    serve(args.bind, args.port, Path(args.suffixes), Path(args.upstreams) if args.upstreams else None)


if __name__ == "__main__":
    main()
