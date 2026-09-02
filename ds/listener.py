"""Event listener: socket2, network, feedback, lock tick, reload, state."""

import fcntl
import os
import re
import select
import signal
import socket
import threading
import time
from pathlib import Path

from ds import catalog, config, feedback, hypr, lock, net, state, ui

TICK, PERIOD, _APPLY = 1.0, 30.0, {"on": "ok", "off": "flush", "unavailable": "unavailable"}
CLIENT_CAP = 256


def _reload_wait():
    return 2 * net.BATCH_DEADLINE + 5


def cmd_listen(args): return run()

def cmd_reload(args):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connected = False
    try:
        sock.settimeout(_reload_wait())
        sock.connect(str(state.runtime_path("distraction-space.sock")))
        connected = True
        sock.sendall(b"reload\n")
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(256)
            if not chunk:
                break
            buf += chunk
        if buf.split(b"\n", 1)[0] == b"ok":
            return 0
        ui.notify("Reload failed", "The listener rejected the request.")
        return 1
    except OSError:
        if connected:
            ui.notify("Reload failed", "The listener closed the connection.")
        else:
            ui.notify("No listener running", "Start it with: distractions listen")
        return 1
    finally:
        sock.close()

def run():
    path = state.runtime_path("distraction-space.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    lf = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lf.close()
        return 0
    try:
        return _listen()
    finally:
        lf.close()

def _empty():
    return {"list": [], "keep_reachable": [], "nudges": {"app_banner": False, "block_page": False, "entry_confirm": False}}

def _close(*objs):
    for obj in objs:
        if obj is None:
            continue
        try:
            obj.close()
        except OSError:
            pass

def _listen():
    ctx = _Ctx()
    r_fd, w_fd = os.pipe()
    for fd in (r_fd, w_fd):
        os.set_blocking(fd, False)
    ctx.wake_w = w_fd
    stop = False

    def handle(_sig, _frame):
        nonlocal stop
        stop = True
        try:
            os.write(w_fd, b"x")
        except OSError:
            pass

    prev = (signal.signal(signal.SIGTERM, handle), signal.signal(signal.SIGINT, handle))
    rs = sock2 = None
    try:
        ctx.boot("start")
        rs = _bind_reload()
        sock2 = _connect_socket2()
        ctx.last_period = time.monotonic()
        ctx.write_state(True)
        ctx.tick()
        last = time.monotonic()
        buf = b""
        while not stop:
            now = time.monotonic()
            wait = max(0.0, last + TICK - now)
            for c in ctx.clients:
                wait = min(wait, max(0.0, c.deadline - now))
            fds = [rs, r_fd] + ([sock2] if sock2 is not None else []) + [c.sock for c in ctx.clients]
            try:
                ready, _, _ = select.select(fds, [], [], wait)
            except (InterruptedError, ValueError):
                continue
            if r_fd in ready:
                try:
                    while os.read(r_fd, 64):
                        pass
                except OSError:
                    pass
                ctx.take_result()
            if sock2 is not None and sock2 in ready:
                chunk, buf, sock2 = _recv_sock2(sock2, buf)
                for raw in chunk:
                    ctx.event(raw)
            if rs in ready:
                _accept_reload(rs, ctx)
            _service_clients(ctx, ready)
            now = time.monotonic()
            if now - last >= TICK or not ready:
                last = now
                ctx.tick()
                if sock2 is None:
                    sock2 = _connect_socket2()
        return 0
    finally:
        signal.signal(signal.SIGTERM, prev[0])
        signal.signal(signal.SIGINT, prev[1])
        feedback.stop()
        net.shutdown()
        for c in ctx.clients:
            _close(c.sock)
        ctx.clients = []
        _close(rs, sock2)
        for fd in (r_fd, w_fd):
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            state.runtime_path("distraction-space.sock").unlink()
        except OSError:
            pass

class _Client:
    __slots__ = ("sock", "buf", "deadline", "gen")
    def __init__(self, sock):
        self.sock, self.buf, self.gen = sock, b"", None
        self.deadline = time.monotonic() + _reload_wait()

class _Ctx:
    def __init__(self):
        self.exp, self.cfg = _empty(), None
        self.gen = self.latest = 0
        self.busy = self.rerun = self.noted = self.resolve_noted = False
        self.reason, self.prev, self.last_state = "start", None, None
        self.last_period = time.monotonic()
        self.pending, self.lock, self.wake_w = None, threading.Lock(), None
        self.clients = []
    def _note_invalid(self):
        if not self.noted:
            ui.notify("Invalid config", "Using the last saved expansion.")
            self.noted = True
    def _note_resolve(self):
        if not self.resolve_noted:
            ui.notify("Network update failed", "Keeping the current site block.")
            self.resolve_noted = True
    def boot(self, reason):
        cfg = _read_cfg()
        if cfg is None:
            raw = state.read_expansion()
            self.exp, self.cfg = (_as_exp(raw) if raw is not None else _empty()), None
            self._note_invalid()
        else:
            self.cfg, self.exp = cfg, _from_cfg(cfg)
            state.write_expansion(self.exp)
        self.enforce(reason)
    def enforce(self, reason):
        hypr.apply_rules(self.exp)
        _scan(self.exp.get("list") or [])
        feedback.start(self.cfg or {"nudges": self.exp.get("nudges") or {}}, lock.is_locked)
        if reason == "reload":
            self.space("reload")
        else:
            here = hypr.on_space()
            if here is not None and self.prev is None:
                self.prev = here
        if self.prev is True:
            self.flush(reason)
            self.write_state(True)
            return True
        self.request(reason)
        self.write_state(True)
        return self.latest
    def request(self, reason):
        self.gen += 1
        self.latest, self.reason = self.gen, reason
        self._adopt_waiters(self.latest)
        if self.busy:
            self.rerun = True
            return
        self._launch(self.gen, reason)
    def _launch(self, gen, reason):
        self.busy = True
        now = time.monotonic()
        window = net.BATCH_DEADLINE + 5
        for c in self.clients:
            if c.gen == gen:
                c.deadline = now + window
        hosts, keep, wake = _hosts(self.exp), self.exp.get("keep_reachable") or [], self.wake_w
        def work():
            failed = False
            try:
                addrs, batch = net.resolve_batch(hosts, gen, reason, keep_reachable=keep)
            except Exception:
                failed = True
                addrs, batch = [], {"generation": gen, "reason": reason, "hosts": 0,
                                    "resolved": 0, "failed": 0, "marker": "failed",
                                    "started": time.monotonic()}
            with self.lock:
                self.pending = (addrs, batch, failed)
            if wake is not None:
                try:
                    os.write(wake, b"n")
                except OSError:
                    pass

        threading.Thread(target=work, daemon=True).start()
    def take_result(self):
        with self.lock:
            item, self.pending = self.pending, None
        if item is None:
            return
        addrs, batch, failed = item
        self.busy = False
        gen = batch.get("generation")
        if failed:
            net.finish_batch(batch, "failed")
            self._note_resolve()
            self._reply_waiters(gen, False)
            self.write_state()
            return self._follow()
        if gen != self.latest:
            net.finish_batch(batch, "stale")
            self._reply_waiters(gen, False)
            return self._follow()
        here = hypr.on_space()
        if here is not False:
            net.finish_batch(batch, "dropped")
            self.rerun = False
            self._reply_waiters(gen, False)
            self.write_state()
            return
        result = net.apply(addrs)
        net.finish_batch(batch, _APPLY.get(result, result))
        self._reply_waiters(gen, True)
        self.write_state()
        self._follow()
    def _follow(self):
        if self.rerun and hypr.on_space() is False:
            self.rerun = False
            self._launch(self.latest, self.reason)
        else:
            self.rerun = False
    def _adopt_waiters(self, gen):
        now = time.monotonic()
        deadline = now + net.BATCH_DEADLINE + 5
        for c in self.clients:
            if isinstance(c.gen, int):
                c.gen = gen
                c.deadline = deadline
    def _reply_waiters(self, gen, ok):
        msg = b"ok\n" if ok else b"error\n"
        for c in self.clients:
            if c.gen == gen:
                _send_reply(c.sock, msg)
                c.gen = "done"
    def _drop_waiters(self):
        for c in self.clients:
            if isinstance(c.gen, int):
                _send_reply(c.sock, b"error\n")
                c.gen = "done"
    def flush(self, _reason=None):
        self.gen += 1
        self.latest, self.rerun = self.gen, False
        net.apply([])
        self._drop_waiters()
        self.write_state(True)
    def event(self, line):
        hypr.handle_event(line)
        name = _workspace_name(line)
        if name is not None:
            self.space("workspace", name)
    def tick(self):
        raw = state.read_json(state.state_path("lock.json"), None)
        if lock.expire_if_due():
            purpose = raw.get("purpose") if isinstance(raw, dict) else ""
            ui.notify("Lock ended", purpose or "")
            lock.run_hook("unlock", _env("unlock", purpose or ""))
            self.write_state(True)
        self.space("tick")
        if self.prev is not True and time.monotonic() - self.last_period >= PERIOD:
            self.last_period = time.monotonic()
            self.request("periodic")
    def space(self, reason, name=None):
        here = (name == hypr.SPACE) if name is not None else hypr.on_space()
        if here is None:
            return
        prev = self.prev
        if prev is None:
            self.prev = here
            self.write_state()
            return
        if here is True and prev is not True:
            lock.run_hook("enter", _env("enter"))
            self.flush()
        elif here is False and prev is True:
            lock.run_hook("leave", _env("leave"))
            self.request("workspace")
        elif here is False and reason == "workspace":
            self.request("workspace")
        self.prev = here
        self.write_state()
    def reload(self):
        cfg = _read_cfg()
        if cfg is None:
            self._note_invalid()
            return False
        self.cfg, self.exp = cfg, _from_cfg(cfg)
        state.write_expansion(self.exp)
        return self.enforce("reload")
    def refresh(self):
        if self.prev is True:
            self.flush("refresh")
            return True
        self.request("refresh")
        return self.latest
    def write_state(self, force=False):
        lk = state.read_lock()
        obj = {
            "locked": bool(lk.get("locked")), "until": lk.get("until"),
            "purpose": lk.get("purpose") or "", "on_space": self.prev,
            "site_block": net.site_block, "listener_pid": os.getpid(),
            "updated": state.now_iso(),
        }
        key = (obj["locked"], obj["until"], obj["purpose"], obj["on_space"], obj["site_block"])
        if not force and key == self.last_state:
            return
        self.last_state = key
        state.write_state(obj)
def _read_cfg():
    if not config.config_path().exists():
        return None
    try:
        return config.load()
    except Exception:
        return None

def _from_cfg(cfg):
    return {"list": catalog.expand(cfg), "keep_reachable": list(cfg.get("keep_reachable") or []),
            "nudges": dict(cfg.get("nudges") or {})}

def _as_exp(obj):
    if isinstance(obj, list):
        obj = {"list": obj}
    if not isinstance(obj, dict):
        return _empty()
    items = obj.get("list") or obj.get("entries") or []
    nudges = obj.get("nudges") if isinstance(obj.get("nudges"), dict) else {}
    return {"list": items if isinstance(items, list) else [],
            "keep_reachable": list(obj.get("keep_reachable") or []), "nudges": dict(nudges)}

def _hosts(exp):
    seen, out = set(), []
    for entry in exp.get("list") or []:
        for host in (entry.get("hosts") or [] if isinstance(entry, dict) else []):
            if isinstance(host, str) and host not in seen:
                seen.add(host)
                out.append(host)
    return out

def _env(event, purpose=None):
    lk = state.read_lock()
    return {"DS_EVENT": event, "DS_PURPOSE": purpose if purpose is not None else (lk.get("purpose") or ""),
            "DS_MINUTES": "", "DS_REASON": "", "DS_HELD": "{}"}

def _scan(entries):
    try:
        clients = hypr.hyprctl_json("clients")
    except Exception:
        return
    for client in clients if isinstance(clients, list) else []:
        if not isinstance(client, dict):
            continue
        klass = client.get("class") or client.get("initialClass") or ""
        ws = client.get("workspace") if isinstance(client.get("workspace"), dict) else {}
        if not klass or ws.get("name") == hypr.SPACE:
            continue
        for entry in entries:
            for pat in (entry.get("classes") or [] if isinstance(entry, dict) else []):
                if not isinstance(pat, str) or not pat:
                    continue
                try:
                    hit = bool(re.search(pat, klass))
                except re.error:
                    hit = pat == klass
                if hit:
                    hypr.move_to_space(client.get("address"))
                    break
            else:
                continue
            break

def _workspace_name(line):
    raw = (line or "").strip().removeprefix(">>")
    if ">>" not in raw:
        return None
    kind, payload = raw.split(">>", 1)
    if kind == "workspacev2" and "," in payload:
        return payload.split(",", 1)[1]
    return payload or None if kind == "workspace" else None

def _bind_reload():
    path = state.runtime_path("distraction-space.sock")
    try:
        path.unlink()
    except OSError:
        pass
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.listen(8)
    sock.setblocking(False)
    return sock

def _connect_socket2():
    path = os.environ.get("DS_SOCKET2")
    if not path:
        sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        if not sig:
            return None
        found = next((p for p in (state.runtime_dir() / "hypr" / sig / ".socket2.sock",
                                  Path("/tmp/hypr") / sig / ".socket2.sock") if p.exists()), None)
        if not found:
            return None
        path = str(found)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.2)
        sock.connect(path)
        sock.setblocking(False)
        return sock
    except OSError:
        sock.close()
        return None

def _recv_sock2(sock, buf):
    try:
        data = sock.recv(4096)
    except (BlockingIOError, OSError):
        return [], buf, sock
    if not data:
        _close(sock)
        return [], b"", None
    buf += data
    lines = []
    while b"\n" in buf:
        raw, buf = buf.split(b"\n", 1)
        lines.append(raw.decode("utf-8", "replace"))
    return lines, buf, sock

def _send_reply(sock, msg):
    try:
        sock.sendall(msg)
    except OSError:
        pass
    _close(sock)

def _accept_reload(rs, ctx):
    while True:
        try:
            conn, _ = rs.accept()
        except (BlockingIOError, OSError):
            return
        try:
            conn.setblocking(False)
        except OSError:
            _close(conn)
            continue
        ctx.clients.append(_Client(conn))

def _dispatch_client(c, ctx, verb):
    result = ctx.reload() if verb == "reload" else ctx.refresh() if verb == "refresh" else False
    if result is True:
        _send_reply(c.sock, b"ok\n")
        c.gen = "done"
        return
    if result is False:
        _send_reply(c.sock, b"error\n")
        c.gen = "done"
        return
    c.gen = result
    c.deadline = time.monotonic() + _reload_wait()

def _read_client(c, ctx):
    try:
        data = c.sock.recv(CLIENT_CAP)
    except BlockingIOError:
        return
    except OSError:
        _close(c.sock)
        c.gen = "done"
        return
    if c.gen == "done":
        return
    if isinstance(c.gen, int):
        if not data:
            _close(c.sock)
            c.gen = "done"
        return
    if not data:
        _close(c.sock)
        c.gen = "done"
        return
    if len(c.buf) + len(data) > CLIENT_CAP:
        _close(c.sock)
        c.gen = "done"
        return
    c.buf += data
    if b"\n" not in c.buf:
        if len(c.buf) >= CLIENT_CAP:
            _close(c.sock)
            c.gen = "done"
        return
    verb = c.buf.split(b"\n", 1)[0].decode("utf-8", "replace").strip()
    _dispatch_client(c, ctx, verb)

def _service_clients(ctx, ready):
    now = time.monotonic()
    for c in ctx.clients:
        if c.gen == "done":
            continue
        if now >= c.deadline:
            _close(c.sock)
            c.gen = "done"
            continue
        if c.sock in ready:
            _read_client(c, ctx)
    ctx.clients = [c for c in ctx.clients if c.gen != "done"]
