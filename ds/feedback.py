"""HTTP block page and TLS ClientHello SNI catcher."""

from __future__ import annotations

import html
import socket
import threading
import time

from ds import ui

HTTP_PORT = 28080
TLS_PORT = 28443
READ_TIMEOUT = 2.0
READ_CAP = 16384
BANNER_DEBOUNCE_S = 30
_BIND_NOTICE = "Block-page server unavailable"

_stop = threading.Event()
_ctl = threading.Lock()
_banner_lock = threading.Lock()
_banner_at: dict[str, float] = {}
_socks: list[socket.socket] = []
_threads: list[threading.Thread] = []
_is_locked = lambda: False


def parse_sni(data):
    try:
        return _parse_sni(data)
    except (IndexError, OSError, UnicodeDecodeError, ValueError):
        return None


def start(config, is_locked):
    stop()
    if not _block_page_on(config):
        return
    global _is_locked
    _is_locked = is_locked if callable(is_locked) else (lambda v=bool(is_locked): v)
    _stop.clear()
    notified = False
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        for port, kind in ((HTTP_PORT, "http"), (TLS_PORT, "tls")):
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
            target = _http_loop if kind == "http" else _tls_loop
            t = threading.Thread(target=target, args=(sock,), daemon=True)
            t.start()
            with _ctl:
                _socks.append(sock)
                _threads.append(t)


def stop():
    _stop.set()
    with _ctl:
        socks, threads = _socks[:], _threads[:]
        _socks.clear()
        _threads.clear()
        _banner_at.clear()
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


def _parse_sni(data):
    if not isinstance(data, (bytes, bytearray)) or len(data) < 5:
        return None
    if data[0] != 0x16:
        return None
    rec_len = _u16(data, 3)
    if rec_len < 4 or 5 + rec_len > len(data):
        return None
    payload = data[5:5 + rec_len]
    if payload[0] != 0x01:
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


def _tls_done(buf):
    if len(buf) < 5:
        return False
    return len(buf) >= 5 + _u16(buf, 3)


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


def _page(host, locked):
    safe = html.escape(host, quote=True)
    lock_note = "<p>The distraction space is locked.</p>" if locked else ""
    return (
        "<!doctype html><html><head><meta charset=utf-8><title>Blocked</title>"
        "<style>body{font-family:sans-serif;max-width:36rem;margin:4rem auto;"
        "padding:0 1.5rem;background:#111;color:#eee}"
        "@media(prefers-color-scheme:light){body{background:#f4f4f2;color:#111}}</style>"
        f"</head><body><h1>Can't open {safe} on this workspace</h1>"
        "<p>Super+D opens the distraction space.</p>"
        f"{lock_note}</body></html>"
    )


def _http_conn(conn):
    try:
        buf = _read_bounded(conn, _headers_done)
        if not _headers_done(buf):
            return
        host = _host_from_http(buf) or "this site"
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
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass


def _maybe_banner(host):
    now = time.monotonic()
    key = host.lower()
    with _banner_lock:
        last = _banner_at.get(key, 0.0)
        if now - last < BANNER_DEBOUNCE_S:
            return
        _banner_at[key] = now
    _notify("Blocked on this workspace", f"{host} opens in the distraction space — Super+D.")


def _tls_conn(conn):
    try:
        buf = _read_bounded(conn, _tls_done)
        host = parse_sni(buf)
        if host:
            _maybe_banner(host)
    except OSError:
        pass
    finally:
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            conn.close()
        except OSError:
            pass


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
