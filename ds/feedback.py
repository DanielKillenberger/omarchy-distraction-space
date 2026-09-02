"""HTTP block page and TLS ClientHello SNI catcher."""

from __future__ import annotations

import errno
import html
import os
import random
import select
import socket
import struct
import threading
import time
from pathlib import Path

from ds import hypr, ui

HTTP_PORT = 28080
TLS_PORT = 28443
READ_TIMEOUT = 2.0
READ_CAP = 16384
BANNER_DEBOUNCE_S = 30
# Above the default net.ipv4.ip_local_port_range ceiling (60999), so an ordinary
# outbound connection never draws an exempt source port by chance.
SPLICE_PORT_MIN = 61000
SPLICE_PORT_MAX = 61999
MAX_SPLICES = 256
CONNECT_TIMEOUT = 5.0
IDLE_TIMEOUT = 120.0
SO_ORIGINAL_DST = 80
IP6T_SO_ORIGINAL_DST = 80
_BIND_NOTICE = "Block-page server unavailable"

_stop = threading.Event()
_ctl = threading.Lock()
_banner_lock = threading.Lock()
_banner_at: dict[str, float] = {}
_log_at: dict[str, float] = {}
_socks: list[socket.socket] = []
_threads: list[threading.Thread] = []
_is_locked = lambda: False
_PPID_WALK = 8
_LOG_LIMIT_S = 60
_splices = 0
_splice_lock = threading.Lock()
# Source ports held by live splices. SO_REUSEADDR stays on the splice sockets so
# a port in TIME_WAIT toward one destination can serve another, which means bind
# alone cannot tell two live splices apart; this registry does.
_ports_in_use: set[int] = set()
_pass_through = True
_block_page = True
_bind_ok = False


def _proc_root():
    return Path(os.environ.get("DS_PROC_ROOT") or "/proc")


def parse_sni(data):
    try:
        return _parse_sni(data)
    except (IndexError, OSError, UnicodeDecodeError, ValueError):
        return None


def _env_port(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _splice_range():
    lo = _env_port("DS_SPLICE_PORT_MIN", SPLICE_PORT_MIN)
    hi = _env_port("DS_SPLICE_PORT_MAX", SPLICE_PORT_MAX)
    return (lo, hi) if hi >= lo else (SPLICE_PORT_MIN, SPLICE_PORT_MAX)


def _pass_through_cfg(config):
    """site_block.pass_through, default True when the key or the config is absent."""
    if not isinstance(config, dict):
        return True
    sb = config.get("site_block")
    if not isinstance(sb, dict):
        return True
    return bool(sb.get("pass_through", True))


def pass_through_state():
    """on | off | unavailable — configured off wins; on only when the servers all bound."""
    if not _pass_through:
        return "off"
    return "on" if _bind_ok else "unavailable"


def start(config, is_locked):
    """Bind the routers when either the block page or pass-through wants them."""
    stop()
    global _is_locked, _pass_through, _bind_ok, _block_page
    _pass_through = _pass_through_cfg(config)
    _block_page = _block_page_on(config)
    _bind_ok = False
    if not _block_page and not _pass_through:
        return
    _is_locked = is_locked if callable(is_locked) else (lambda v=bool(is_locked): v)
    _stop.clear()
    notified = False
    bound = 0
    http_port = _env_port("DS_FEEDBACK_HTTP_PORT", HTTP_PORT)
    tls_port = _env_port("DS_FEEDBACK_TLS_PORT", TLS_PORT)
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        for port, kind in ((http_port, "http"), (tls_port, "tls")):
            sock = socket.socket(family, socket.SOCK_STREAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if family == socket.AF_INET6:
                    sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                sock.bind((host, port))
                sock.listen(128)
                sock.settimeout(0.5)
            except OSError:
                sock.close()
                if not notified:
                    _notify(_BIND_NOTICE, "A feedback port is in use; blocked sites still fail fast.")
                    notified = True
                continue
            bound += 1
            target = _http_loop if kind == "http" else _tls_loop
            t = threading.Thread(target=target, args=(sock,), daemon=True)
            t.start()
            with _ctl:
                _socks.append(sock)
                _threads.append(t)
    _bind_ok = bound > 0 and not notified


def stop():
    """Close the listeners. Live splices keep their slot and source port until they end."""
    global _bind_ok
    _stop.set()
    _bind_ok = False
    with _ctl:
        socks, threads = _socks[:], _threads[:]
        _socks.clear()
        _threads.clear()
        _banner_at.clear()
        _log_at.clear()
    for sock in socks:
        try:
            sock.close()
        except OSError:
            pass
    for t in threads:
        t.join(timeout=2)


def _block_page_on(config):
    if not isinstance(config, dict):
        return True
    nudges = config.get("nudges")
    if not isinstance(nudges, dict):
        return True
    return bool(nudges.get("block_page", True))


def _notify(title, body):
    try:
        ui.notify(title, body)
    except Exception:
        pass


def _u16(buf, off):
    return (buf[off] << 8) | buf[off + 1]


def _u24(buf, off):
    return (buf[off] << 16) | (buf[off + 1] << 8) | buf[off + 2]


def _handshake_payload(data):
    """The concatenated payloads of the complete handshake records at the start of data.

    A ClientHello may span several TLS records (RFC 8446 section 5.1), so the
    routers reassemble before reading the SNI; a hello judged by its first
    record alone would read as unreadable and pass through.
    """
    out = bytearray()
    off = 0
    while off + 5 <= len(data):
        if data[off] != 0x16:
            break
        rec_len = _u16(data, off + 3)
        if off + 5 + rec_len > len(data):
            break
        out.extend(data[off + 5:off + 5 + rec_len])
        off += 5 + rec_len
    return bytes(out)


def _parse_sni(data):
    if not isinstance(data, (bytes, bytearray)) or len(data) < 5:
        return None
    if data[0] != 0x16:
        return None
    payload = _handshake_payload(data)
    if len(payload) < 4 or payload[0] != 0x01:
        return None
    hs_len = _u24(payload, 1)
    if 4 + hs_len > len(payload):
        return None
    body = payload[4:4 + hs_len]
    if len(body) < 35:
        return None
    off = 34
    sid_len = body[off]
    off += 1 + sid_len
    if off + 2 > len(body):
        return None
    off += 2 + _u16(body, off)
    if off + 1 > len(body):
        return None
    off += 1 + body[off]
    if off == len(body):
        return None
    if off + 2 > len(body):
        return None
    ext_len = _u16(body, off)
    off += 2
    if off + ext_len > len(body):
        return None
    end = off + ext_len
    while off + 4 <= end:
        etype = _u16(body, off)
        elen = _u16(body, off + 2)
        off += 4
        if off + elen > end:
            return None
        edata = body[off:off + elen]
        off += elen
        if etype == 0:
            return _sni_host(edata)
    return None


def _sni_host(edata):
    if len(edata) < 2:
        return None
    list_len = _u16(edata, 0)
    if 2 + list_len > len(edata):
        return None
    pos = 2
    end = 2 + list_len
    while pos + 3 <= end:
        name_type = edata[pos]
        name_len = _u16(edata, pos + 1)
        pos += 3
        if pos + name_len > end:
            return None
        name = edata[pos:pos + name_len]
        pos += name_len
        if name_type == 0 and name:
            host = name.decode("ascii")
            if "\x00" in host:
                return None
            return host
    return None


def _read_bounded(conn, done):
    conn.settimeout(READ_TIMEOUT)
    buf = bytearray()
    deadline = time.monotonic() + READ_TIMEOUT
    while len(buf) < READ_CAP:
        left = deadline - time.monotonic()
        if left <= 0:
            break
        conn.settimeout(left)
        try:
            chunk = conn.recv(min(4096, READ_CAP - len(buf)))
        except (TimeoutError, socket.timeout, OSError):
            break
        if not chunk:
            break
        buf.extend(chunk)
        if done(buf):
            break
    return bytes(buf)


def _headers_done(buf):
    return b"\r\n\r\n" in buf or b"\n\n" in buf


def _http_request_line(buf):
    nl = buf.find(b"\n")
    if nl < 0:
        return False
    line = buf[:nl].rstrip(b"\r")
    parts = line.split(b" ")
    if len(parts) != 3:
        return False
    method, target, version = parts
    if not method.isalpha() or not target:
        return False
    if len(version) != 8 or not version.startswith(b"HTTP/1."):
        return False
    return version[7:8].isdigit()


def _tls_done(buf):
    """True once the whole ClientHello is buffered, or the bytes cannot be one."""
    if len(buf) < 5:
        return False
    if buf[0] != 0x16:
        return True
    payload = _handshake_payload(buf)
    if len(payload) < 4:
        return False
    if payload[0] != 0x01:
        return True
    return len(payload) >= 4 + _u24(payload, 1)


def _host_from_http(buf):
    try:
        text = buf.decode("iso-8859-1")
    except UnicodeDecodeError:
        return ""
    if "\r\n\r\n" in text:
        head = text.split("\r\n\r\n", 1)[0]
    elif "\n\n" in text:
        head = text.split("\n\n", 1)[0]
    else:
        return ""
    for line in head.splitlines()[1:]:
        if line.lower().startswith("host:"):
            return line.split(":", 1)[1].strip()
    return ""


def _norm_host(host):
    """Lowercase, strip a port or [v6] brackets, a trailing dot, and a leading www."""
    if not isinstance(host, str) or not host:
        return ""
    h = host.strip().lower()
    if h.startswith("["):
        end = h.find("]")
        if end > 1:
            h = h[1:end]
    elif h.count(":") == 1:
        name, port = h.rsplit(":", 1)
        if port.isdigit():
            h = name
    h = h.rstrip(".")
    if h.startswith("www."):
        h = h[4:]
    return h


def _entry_for_host(host):
    """The active entry owning host, matched as an equal or parent domain, or None.

    One matcher serves routing, banner identity, and origin attribution, so a
    subdomain of a listed host debounces and attributes like the host itself.
    """
    want = _norm_host(host)
    if not want:
        return None
    for entry in hypr._current_entries():
        if not isinstance(entry, dict):
            continue
        for h in entry.get("hosts") or []:
            if not isinstance(h, str):
                continue
            base = _norm_host(h)
            if base and (want == base or want.endswith("." + base)):
                return entry
    return None


def _listed(host):
    """True when host equals, or is a subdomain of, a host in the active expansion."""
    return _entry_for_host(host) is not None


def _original_dst(conn):
    """(host, port) recovered from the redirect, or None when not redirected."""
    try:
        if conn.family == socket.AF_INET6:
            raw = conn.getsockopt(socket.IPPROTO_IPV6, IP6T_SO_ORIGINAL_DST, 28)
            _fam, port, _flow, addr, _scope = struct.unpack("!HHI16sI", raw)
            if port == 0:
                return None
            host = socket.inet_ntop(socket.AF_INET6, addr)
        else:
            raw = conn.getsockopt(socket.SOL_IP, SO_ORIGINAL_DST, 16)
            _fam, port, addr = struct.unpack("!HH4s", raw[:8])
            if port == 0:
                return None
            host = socket.inet_ntop(socket.AF_INET, addr)
        return (host, port)
    except (OSError, struct.error, ValueError):
        return None


def _is_self(conn, dst):
    try:
        local = conn.getsockname()
    except OSError:
        return True
    return dst[0] == local[0] and dst[1] == local[1]


def _acquire_port(lo, hi, skip):
    """Reserve a port in [lo, hi] held by no live splice and not in skip, or None."""
    span = hi - lo + 1
    start = random.randrange(span)
    with _splice_lock:
        for i in range(span):
            port = lo + ((start + i) % span)
            if port in skip or port in _ports_in_use:
                continue
            _ports_in_use.add(port)
            return port
    return None


def _free_port(port):
    with _splice_lock:
        _ports_in_use.discard(port)


def _open_splice(dst, family):
    """(socket, port, None) or (None, None, reason) where reason is 'connect' or 'range'.

    A port the kernel refuses for this destination (bind EADDRINUSE, or connect
    EADDRNOTAVAIL/EADDRINUSE when the same four-tuple is still in TIME_WAIT) is
    skipped and another is tried; every other connect error is the destination's.
    """
    lo, hi = _splice_range()
    wildcard = "::" if family == socket.AF_INET6 else "0.0.0.0"
    skip: set[int] = set()
    while True:
        port = _acquire_port(lo, hi, skip)
        if port is None:
            return None, None, "range"
        sock = socket.socket(family, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((wildcard, port))
            sock.settimeout(CONNECT_TIMEOUT)
            sock.connect(dst)
        except OSError as e:
            try:
                sock.close()
            except OSError:
                pass
            _free_port(port)
            if e.errno in (errno.EADDRINUSE, errno.EADDRNOTAVAIL, errno.EACCES):
                skip.add(port)
                continue
            return None, None, "connect"
        return sock, port, None


def _claim_splice():
    global _splices
    with _splice_lock:
        if _splices >= MAX_SPLICES:
            return False
        _splices += 1
        return True


def _release_splice():
    global _splices
    with _splice_lock:
        _splices = max(0, _splices - 1)


def _close_sock(sock):
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


def _pump(client, upstream, pending):
    try:
        if pending:
            upstream.sendall(pending)
        client.settimeout(IDLE_TIMEOUT)
        upstream.settimeout(IDLE_TIMEOUT)
        socks = [client, upstream]
        while socks:
            try:
                ready, _, _ = select.select(socks, [], [], IDLE_TIMEOUT)
            except (OSError, ValueError):
                return
            if not ready:
                return
            for sock in ready:
                try:
                    data = sock.recv(65536)
                except OSError:
                    return
                peer = upstream if sock is client else client
                if not data:
                    try:
                        peer.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    try:
                        socks.remove(sock)
                    except ValueError:
                        pass
                    continue
                try:
                    peer.sendall(data)
                except OSError:
                    return
    except OSError:
        return


def _route(conn, buf, host):
    """True when this connection is not the block path: it was spliced, or deliberately closed."""
    if not _pass_through:
        return False
    if _listed(host):
        return False
    dst = _original_dst(conn)
    if dst is None or _is_self(conn, dst):
        return True
    if not _claim_splice():
        _log_limited("splice-cap", f"pass-through cap {MAX_SPLICES} reached; connection closed")
        return True
    try:
        up, port, why = _open_splice(dst, conn.family)
        if up is None:
            if why == "range":
                _log_limited("splice-cap", "pass-through source ports exhausted; connection closed")
            else:
                _log_limited(f"dst:{dst[0]}:{dst[1]}",
                             f"pass-through to {dst[0]}:{dst[1]} failed")
            return True
        try:
            _pump(conn, up, buf)
        finally:
            _close_sock(up)
            _free_port(port)
    finally:
        _release_splice()
    return True


def _page(host, locked):
    safe = html.escape(host, quote=True)
    lock_note = "<p>The distraction space is locked.</p>" if locked else ""
    return (
        "<!doctype html><html><head><meta charset=utf-8><title>Blocked</title>"
        "<style>body{font-family:sans-serif;max-width:36rem;margin:4rem auto;"
        "padding:0 1.5rem;background:#111;color:#eee}"
        "@media(prefers-color-scheme:light){body{background:#f4f4f2;color:#111}}</style>"
        f"</head><body><h1>Can't open {safe} on this workspace</h1>"
        "<p>Super+Ctrl+Shift+D opens the distraction space.</p>"
        f"{lock_note}</body></html>"
    )


def _http_conn(conn):
    try:
        buf = _read_bounded(conn, _headers_done)
        ok = _headers_done(buf) and _http_request_line(buf)
        host = _host_from_http(buf) if ok else ""
        if _route(conn, buf, host):
            return
        if not ok or not _block_page:
            return
        host = host or "this site"
        try:
            locked = bool(_is_locked())
        except Exception:
            locked = False
        body = _page(host, locked).encode("utf-8")
        head = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html; charset=utf-8\r\n"
            "Connection: close\r\n"
            f"Content-Length: {len(body)}\r\n"
            "\r\n"
        )
        conn.sendall(head.encode("ascii") + body)
    except OSError:
        pass
    finally:
        _close_sock(conn)


def _log_limited(key, msg):
    now = time.monotonic()
    with _banner_lock:
        last = _log_at.get(key)
        if last is not None and now - last < _LOG_LIMIT_S:
            return
        _log_at[key] = now
    hypr._log(msg)


def _banner_identity(host):
    entry = _entry_for_host(host)
    if isinstance(entry, dict):
        name = entry.get("name")
        if isinstance(name, str) and name:
            return name, name
    return (host or "").lower(), host


def _inode_in_table(path, peer_port, uid):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    lines = text.splitlines()
    if not lines:
        return None
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 10:
            continue
        local = parts[1]
        try:
            hexport = local.rsplit(":", 1)[1]
            port = int(hexport, 16)
        except (IndexError, ValueError):
            continue
        if port != peer_port:
            continue
        try:
            row_uid = int(parts[7])
            inode = int(parts[9])
        except ValueError:
            continue
        if row_uid != uid:
            continue
        return inode
    return None


def _inode_for_port(peer_port):
    try:
        peer_port = int(peer_port)
    except (TypeError, ValueError):
        return None
    uid = os.getuid()
    root = _proc_root()
    for name in ("tcp", "tcp6"):
        inode = _inode_in_table(root / "net" / name, peer_port, uid)
        if inode is not None:
            return inode
    return None


def _pid_for_inode(inode):
    root = _proc_root()
    uid = os.getuid()
    want = f"socket:[{inode}]"
    try:
        names = os.listdir(root)
    except OSError:
        return None
    for name in names:
        if not name.isdigit():
            continue
        proc_dir = root / name
        try:
            if os.stat(proc_dir).st_uid != uid:
                continue
        except OSError:
            continue
        fd_dir = proc_dir / "fd"
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd_dir / fd)
            except OSError:
                continue
            if target == want:
                return int(name)
    return None


def _ppid_of(pid):
    path = _proc_root() / str(pid) / "status"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        if line.startswith("PPid:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return None
    return None


def _pid_clients(pid, clients):
    out = []
    for c in clients:
        if not isinstance(c, dict):
            continue
        try:
            if int(c.get("pid")) == int(pid):
                out.append(c)
        except (TypeError, ValueError):
            continue
    return out


def _walk_to_hypr_owner(start_pid, clients):
    owners = set()
    for c in clients:
        if not isinstance(c, dict):
            continue
        try:
            owners.add(int(c.get("pid")))
        except (TypeError, ValueError):
            continue
    try:
        pid = int(start_pid)
    except (TypeError, ValueError):
        return None
    for _ in range(_PPID_WALK + 1):
        if pid <= 1:
            return None
        if pid in owners:
            return pid
        parent = _ppid_of(pid)
        if parent is None or parent <= 1:
            return None
        pid = parent
    return None


def _origin_on_space(peer_port, host):
    if peer_port is None:
        return False
    try:
        return _origin_on_space_inner(peer_port, host)
    except Exception as e:
        _log_limited("proc", f"origin attribution: {e}")
        return False


def _origin_on_space_inner(peer_port, host):
    clients = hypr.clients_cached()
    if clients is None:
        _log_limited("clients", "hyprctl clients unavailable; banner shown")
        return False
    inode = _inode_for_port(peer_port)
    if inode is None:
        return False
    pid = _pid_for_inode(inode)
    if pid is None:
        return False
    owner = _walk_to_hypr_owner(pid, clients)
    if owner is None:
        return False
    owner_clients = _pid_clients(owner, clients)
    if not owner_clients:
        return False
    on_space = all(
        isinstance(c.get("workspace"), dict) and c["workspace"].get("name") == hypr.SPACE
        for c in owner_clients
    )
    if on_space:
        return True
    entry = _entry_for_host(host)
    if entry is None:
        return False
    if not any(hypr._class_matches(entry, c.get("class") or "") for c in owner_clients):
        return False
    return hypr.entry_clients_on_space(entry, clients)


def _maybe_banner(host, peer_port=None):
    now = time.monotonic()
    key, name = _banner_identity(host)
    with _banner_lock:
        last = _banner_at.get(key)
        if last is not None and now - last < BANNER_DEBOUNCE_S:
            return
    if _origin_on_space(peer_port, host):
        return
    now = time.monotonic()
    with _banner_lock:
        last = _banner_at.get(key)
        if last is not None and now - last < BANNER_DEBOUNCE_S:
            return
        _banner_at[key] = now
    _notify("Blocked on this workspace", f"{name} opens in the distraction space — Super+Ctrl+Shift+D.")


def _tls_conn(conn):
    try:
        try:
            peer_port = conn.getpeername()[1]
        except OSError:
            peer_port = None
        buf = _read_bounded(conn, _tls_done)
        host = parse_sni(buf)
        if _route(conn, buf, host or ""):
            return
        if host and _block_page:
            _maybe_banner(host, peer_port)
    except OSError:
        pass
    finally:
        _close_sock(conn)


def _accept_loop(sock, handler):
    while not _stop.is_set():
        try:
            conn, _addr = sock.accept()
        except TimeoutError:
            continue
        except OSError:
            if _stop.is_set():
                break
            continue
        threading.Thread(target=handler, args=(conn,), daemon=True).start()


def _http_loop(sock):
    _accept_loop(sock, _http_conn)


def _tls_loop(sock):
    _accept_loop(sock, _tls_conn)
