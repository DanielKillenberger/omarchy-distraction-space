"""Event listener: socket2, network, feedback, lock tick, notification hold, reload, state."""

import fcntl
import json
import os
import select
import signal
import socket
import threading
import time
from pathlib import Path

from ds import catalog, cgroup, config, feedback, hold, hypr, launch, lock, net, setup, state, summary, ui

TICK, PERIOD, _APPLY = 1.0, 60.0, {"on": "ok", "off": "flush", "unavailable": "unavailable"}
CLIENT_CAP = 256


def _reload_wait():
    return 2 * net.BATCH_DEADLINE + 5


def cmd_listen(args): return run()

def cmd_reload(args): return _ask("reload")

def cmd_refresh(args): return _ask("refresh")

def cmd_release(args):
    """Exempt the focused window from containment (R17): 0 recorded, 1 no window or no listener.

    A non-positive duration never reaches here; the parser exits 2 on it.
    """
    minutes = getattr(args, "minutes", None)
    if minutes is None:
        minutes = (_read_cfg() or config.DEFAULTS)["containment"]["release_minutes"]
    window = hypr.active_window()
    if window is None:
        ui.notify("No window to release", "Focus the window first, then run: distractions release")
        return 1
    return _ask(f"release {window['address']} {lock.until_iso(minutes)}")

def _ask(line):
    """One request line to the running listener: 0 on an `ok` reply, 1 otherwise."""
    failed = f"{line.split()[0].capitalize()} failed"
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    connected = False
    try:
        sock.settimeout(_reload_wait())
        sock.connect(str(state.runtime_path("distraction-space.sock")))
        connected = True
        sock.sendall(line.encode() + b"\n")
        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(256)
            if not chunk:
                break
            buf += chunk
        if buf.split(b"\n", 1)[0] == b"ok":
            return 0
        ui.notify(failed, "The listener rejected the request.")
        return 1
    except OSError:
        if connected:
            ui.notify(failed, "The listener closed the connection.")
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
    return {"list": [], "keep_reachable": [], "nudges": {"app_banner": False, "block_page": False},
            "site_block": {"enabled": True}}

def _apply(addrs):
    """`replace` renders the slice's cgroup rule, so the slice is started before it.

    The wrapper is the check: it refuses when the cgroup is missing and `net.apply`
    reports that as `unavailable`, so a failed start is not a reason to skip the
    call. `flush` only destroys the table and needs no slice at all.
    """
    if addrs:
        cgroup.ensure_slice()
    return net.apply(addrs)

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
        _clone_check()
        ctx.capture.tick()
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
            bus, pa = ctx.capture.fileno(), ctx.mute.fileno()
            fds = [rs, r_fd] + [fd for fd in (sock2, bus, pa) if fd is not None] + [c.sock for c in ctx.clients]
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
            if bus is not None and bus in ready:
                if ctx.capture.pump(ctx.hold_on is True, ctx.hold_table()):
                    ctx.write_state()
            if pa is not None and pa in ready:
                ctx.mute.pump()
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
        ctx.capture.stop()
        ctx.release_hold()
        ctx.mute.release()
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
        self.hold_on, self.hold_ipc, self.hold_noted, self.pushed = None, "off", False, []
        self.hold_failed_at = 0.0
        self.links, self.browser = "off", None
        self.links_noted = False
        self.capture, self.mute = hold.Capture(), hold.Mute()
    def _note_invalid(self):
        if not self.noted:
            ui.notify("Invalid config", "Using the last saved expansion.")
            self.noted = True
    def _note_resolve(self):
        if not self.resolve_noted:
            ui.notify("Network update failed", "Keeping the current site block.")
            self.resolve_noted = True
    def _note_hold(self):
        if not self.hold_noted:
            ui.notify("Notification hold unavailable", "The shell lacks silencedSenders. Run: distractions setup")
            self.hold_noted = True
    def release(self, address, until):
        """Record one exemption; a past or unreadable deadline, or a window that is gone, is refused.

        The address was read from `activewindow` a moment ago; if that window
        closed in between, its `closewindow` may already have passed and nothing
        would ever prune the record, so only a client Hyprland still lists counts.
        """
        if not address or hypr.past(until):
            return False
        if hypr._client_by_address(address) is None:
            return False
        hypr.release(address, until)
        self.write_state()
        return True
    def expire_released(self):
        """An exemption past its deadline ends; with snap_back on, that window is contained once more."""
        gone = hypr.expire_released()
        if not gone:
            return
        self.write_state()
        if hypr.snap_back:
            for address in gone:
                hypr.contain_address(address)
    def check_links(self):
        """Whether listed links still route here; a displaced handler is noticed once per lifetime."""
        self.links = _links_state(self.cfg)
        if self.links == "displaced" and not self.links_noted:
            ui.notify("Links no longer open in the space", "Another browser is the default. Run: distractions setup")
            self.links_noted = True
    def hold_table(self):
        return hold.key_table(self.exp.get("list") or [])
    def block_enabled(self):
        sb = self.exp.get("site_block")
        return sb.get("enabled") is not False if isinstance(sb, dict) else True
    def sync_hold(self, force=False):
        """Push the plugin's sender keys on every change of effective hold or of the keys.

        While the shell answered `unavailable`, the push is retried once per PERIOD until it takes.
        """
        want = hold.effective_hold(self.cfg, self.prev, lock.is_locked())
        keys = list(self.hold_table())
        now = time.monotonic()
        retry = self.hold_ipc == "unavailable" and now - self.hold_failed_at >= PERIOD
        if not force and not retry and want == self.hold_on and keys == self.pushed:
            return
        self.hold_ipc = hold.push(keys, want, retire=[k for k in self.pushed if k not in keys])
        self.hold_on, self.pushed = want, keys
        if self.hold_ipc == "unavailable":
            self.hold_failed_at = now
            self._note_hold()
        self.mute.sync(want and hold.mute_on(self.cfg), hold.audio_table(self.exp.get("list") or []))
    def release_hold(self):
        if self.pushed:
            hold.push(self.pushed, False)
    def summarize(self):
        """A boundary this listener marks (a lock expired, the space was entered): claim the records, start the notice.

        Returns the per-app counts for the hook of the same boundary. A manual
        `distractions unlock` is the command's boundary; it claims and notifies itself.
        """
        records = summary.take()
        summary.start(records, self.cfg)
        return summary.counts(records)
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
        self.browser = _browser_name(self.cfg)
        hypr.snap_back = (self.cfg or config.DEFAULTS)["containment"]["snap_back"]
        hypr.apply_rules(self.exp)
        # The scan's Opened banners read the nudge and the lock through feedback, so it starts first.
        feedback.start(self.cfg or {"nudges": self.exp.get("nudges") or {}}, lock.is_locked)
        _scan()
        if reason == "reload":
            self.space()
        else:
            here = hypr.on_space()
            if here is not None and self.prev is None:
                self.prev = here
        self.sync_hold(force=True)
        self.check_links()
        if not self.block_enabled():
            return self.flush(reason)
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
        result = _apply(addrs)
        net.finish_batch(batch, _APPLY.get(result, result))
        # A wrapper refusal is an enforcement failure: whoever asked for this
        # generation hears `error`, not `ok`, and the state carries `unavailable`.
        self._reply_waiters(gen, result in ("on", "off"))
        self.write_state()
        self._follow()
    def _follow(self):
        if self.rerun:
            self.rerun = False
            self._launch(self.latest, self.reason)
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
        """Destroy the table; True when the wrapper accepted it, False when it refused."""
        self.gen += 1
        self.latest, self.rerun = self.gen, False
        result = _apply([])
        self._drop_waiters()
        self.write_state(True)
        return result == "off"
    def event(self, line):
        if hypr.is_config_reload(line):
            hypr.apply_rules(self.exp)
            _scan()
            return
        hypr.handle_event(line)
        name = _workspace_name(line)
        if name is not None:
            self.space(name)
    def tick(self):
        raw = state.read_json(state.state_path("lock.json"), None)
        if lock.expire_if_due():
            purpose = raw.get("purpose") if isinstance(raw, dict) else ""
            ui.notify("Lock ended", purpose or "")
            lock.run_hook("unlock", _env("unlock", purpose or "", self.summarize()))
            self.write_state(True)
        self.space()
        self.expire_released()
        self.capture.tick()
        self.mute.tick()
        self.sync_hold()
        self.write_state()
        if time.monotonic() - self.last_period >= PERIOD:
            self.last_period = time.monotonic()
            setup.refresh_entries(self.exp, self.cfg)
            self.check_links()
            self.write_state()
            if self.block_enabled():
                self.request("periodic")
    def space(self, name=None):
        here = (name == hypr.SPACE) if name is not None else hypr.on_space()
        if here is None:
            return
        prev = self.prev
        if prev is None:
            self.prev = here
            self.write_state()
            return
        if here is True and prev is not True:
            lock.run_hook("enter", _env("enter", held=self.summarize()))
        elif here is False and prev is True:
            lock.run_hook("leave", _env("leave"))
        self.prev = here
        self.sync_hold()
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
        setup.refresh_entries(self.exp, self.cfg)
        if not self.block_enabled():
            # Nothing to resolve. The switch is honored already unless the last
            # flush was refused, in which case this is the retry.
            return net.site_block == "off" or self.flush("refresh")
        self.request("refresh")
        return self.latest
    def write_state(self, force=False):
        lk = state.read_lock()
        obj = {
            "locked": bool(lk.get("locked")), "until": lk.get("until"),
            "purpose": lk.get("purpose") or "", "on_space": self.prev,
            "site_block": net.site_block, "listener_pid": os.getpid(),
            "hold": self.hold_on is True, "held": hold.held_counts(), "notification_hold": self.hold_ipc,
            "pass_through": feedback.pass_through_state(),
            "links": self.links, "browser": self.browser, "released": hypr.released(),
            "updated": state.now_iso(),
        }
        key = (obj["locked"], obj["until"], obj["purpose"], obj["on_space"], obj["site_block"],
               obj["hold"], obj["notification_hold"], obj["pass_through"], tuple(sorted(obj["held"].items())),
               obj["links"], obj["browser"], tuple(sorted(obj["released"].items())))
        if not force and key == self.last_state:
            return
        self.last_state = key
        state.write_state(obj)
def _clone_check():
    """Notice only: a stale notification-service clone is re-cloned by `setup`, never here."""
    why = setup.clone_drift()
    if why:
        ui.notify("Notification hold needs setup", f"{why[0].upper()}{why[1:]}. Run: distractions setup")

def _browser_name(cfg):
    """The distraction browser's basename for `state.json`, or None when none resolves.

    The same pick `open` makes: the config argv when set, else the Omarchy
    default when it is Chromium-family, else chromium; read at start and reload.
    """
    try:
        argv = launch.pick_browser(cfg or config.DEFAULTS)
    except Exception:
        return None
    return Path(argv[0]).name if argv else None

def _links_state(cfg):
    """`on` while setup's handler is still the default browser, `displaced` when another took it.

    `off` when the switch is off or setup never registered the handler (the
    manifest names it); `xdg-settings` is only asked once there is something to hold.
    """
    if not (cfg or config.DEFAULTS)["open_links_in_space"]:
        return "off"
    if not any(Path(item["path"]).name == setup.HANDLER_ID for item in state.read_entries()["files"]):
        return "off"
    answered, handler = setup.default_handler()
    # An unanswered query is not proof of displacement, but it is not proof the
    # handler still holds either; the notice tells the person to run setup.
    return "on" if answered and handler == setup.HANDLER_ID else "displaced"

def _read_cfg():
    if not config.config_path().exists():
        return None
    try:
        return config.load()
    except Exception:
        return None

def _from_cfg(cfg):
    return {"list": catalog.expand(cfg), "keep_reachable": list(cfg.get("keep_reachable") or []),
            "nudges": dict(cfg.get("nudges") or {}),
            "site_block": {"enabled": cfg["site_block"]["enabled"]}}

def _as_exp(obj):
    """The saved expansion; a version 2 file reads with `desktop: null` and the block on."""
    if isinstance(obj, list):
        obj = {"list": obj}
    if not isinstance(obj, dict):
        return _empty()
    items = obj.get("list") or obj.get("entries") or []
    nudges = obj.get("nudges") if isinstance(obj.get("nudges"), dict) else {}
    sb = obj.get("site_block") if isinstance(obj.get("site_block"), dict) else {}
    return {"list": [_with_desktop(e) for e in items] if isinstance(items, list) else [],
            "keep_reachable": list(obj.get("keep_reachable") or []), "nudges": dict(nudges),
            "site_block": {"enabled": sb.get("enabled") is not False}}

def _with_desktop(entry):
    if isinstance(entry, dict) and not isinstance(entry.get("desktop"), str):
        return {**entry, "desktop": None}
    return entry

def _hosts(exp):
    seen, out = set(), []
    for entry in exp.get("list") or []:
        for host in (entry.get("hosts") or [] if isinstance(entry, dict) else []):
            if isinstance(host, str) and host not in seen:
                seen.add(host)
                out.append(host)
    return out

def _env(event, purpose=None, held=None):
    lk = state.read_lock()
    return {"DS_EVENT": event, "DS_PURPOSE": purpose if purpose is not None else (lk.get("purpose") or ""),
            "DS_MINUTES": "", "DS_REASON": "", "DS_HELD": json.dumps(held or {})}

def _scan():
    """Start and reload: the same three containment layers over every existing client."""
    try:
        clients = hypr.hyprctl_json("clients")
    except Exception:
        return
    for client in clients if isinstance(clients, list) else []:
        hypr.contain(client)

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
    words = verb.split()
    if words[:1] == ["release"] and len(words) == 3:
        result = ctx.release(words[1], words[2])
    else:
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
