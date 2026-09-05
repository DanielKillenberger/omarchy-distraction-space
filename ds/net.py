"""Hostname resolution, last-good cache, and sudo nft apply."""

from __future__ import annotations

import ipaddress
import os
import signal
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from ds import config, setup, state

BATCH_DEADLINE = 10.0
RESOLVE_TIMEOUT = 2.0
POOL_SIZE = 8
COMMAND_TIMEOUT = 10.0
command_context = threading.local()

site_block = "off"

_pool = None
_pool_lock = threading.Lock()
_child_lock = threading.Lock()
_children: dict[int, subprocess.Popen] = {}
_noticed = False


def run_command(args, *, timeout, input=None, capture_output=False, check=False, **kwargs):
    """Run a bounded child group; the reconciliation worker can cancel its waits."""
    cancel = getattr(command_context, "cancel", None)
    if cancel is not None and cancel.is_set():
        raise OSError("reconciliation stopped")
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    if capture_output:
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc = subprocess.Popen(args, start_new_session=True, **kwargs)
    _track(proc)
    deadline = time.monotonic() + timeout
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or (cancel is not None and cancel.is_set()):
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                out, err = proc.communicate(input=input, timeout=min(remaining, 0.1))
                break
            except subprocess.TimeoutExpired:
                input = None
        result = subprocess.CompletedProcess(args, proc.returncode, out, err)
        if check:
            result.check_returncode()
        return result
    finally:
        try:
            if proc.poll() is None:
                # Give sudo's monitor a chance to forward termination to its child.
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except OSError:
                    pass
                try:
                    proc.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    pass
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                proc.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                for stream in (proc.stdin, proc.stdout, proc.stderr):
                    if stream is not None:
                        stream.close()
                proc.kill()
                proc.wait(timeout=1)
        finally:
            _untrack(proc)


def _log_path() -> Path:
    data = state.read_json(config.config_path(), None)
    log = data.get("log") if isinstance(data, dict) else None
    if isinstance(log, str) and log:
        return Path(os.path.expanduser(log))
    return state.state_path("log")


def _parse_ahosts(text: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in text.splitlines():
        token = raw.split()[0] if raw.strip() else ""
        if not token:
            continue
        try:
            addr = ipaddress.ip_address(token)
        except ValueError:
            continue
        if addr.is_unspecified:
            continue
        rendered = str(addr)
        if rendered in seen:
            continue
        seen.add(rendered)
        out.append(rendered)
    return out


def _track(proc: subprocess.Popen) -> None:
    with _child_lock:
        _children[proc.pid] = proc


def _untrack(proc: subprocess.Popen) -> None:
    with _child_lock:
        _children.pop(proc.pid, None)


def _kill_children() -> None:
    with _child_lock:
        procs = list(_children.values())
    for proc in procs:
        try:
            proc.terminate()
        except OSError:
            pass


def _resolve_one(host: str) -> list[str]:
    try:
        proc = subprocess.Popen(
            ["getent", "ahosts", host],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return []
    _track(proc)
    try:
        out, _ = proc.communicate(timeout=RESOLVE_TIMEOUT)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return []
    finally:
        _untrack(proc)
    if proc.returncode != 0 or not out:
        return []
    return _parse_ahosts(out)


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=POOL_SIZE, thread_name_prefix="ds-net")
        return _pool


def _read_cache() -> dict:
    data = state.read_json(state.state_path("addrs.json"), {})
    if not isinstance(data, dict):
        return {}
    out = {}
    for host, addrs in data.items():
        if isinstance(host, str) and isinstance(addrs, list):
            out[host] = [a for a in addrs if isinstance(a, str) and a]
    return out


def _write_cache(cache: dict) -> None:
    state.write_json(state.state_path("addrs.json"), cache)


def _append_log(line: str) -> None:
    configured = _log_path()
    default = state.state_path("log")
    for path in (configured, default):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
            return
        except OSError:
            continue


def _notice_unavailable() -> None:
    global _noticed
    if _noticed:
        return
    _noticed = True
    try:
        run_command(
            ["omarchy-notification-send", "Site block unavailable",
             "Wrapper missing or sudo -n distractions-nft refused."],
            timeout=2,
            check=False,
            capture_output=True,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def resolve_batch(hosts, generation, reason, keep_reachable=()):
    hosts = [h for h in (hosts or []) if isinstance(h, str) and h]
    keep_hosts = [h for h in (keep_reachable or ()) if isinstance(h, str) and h]
    started = time.monotonic()
    cache = _read_cache()
    to_resolve = list(dict.fromkeys(hosts + keep_hosts))
    fresh: dict[str, list[str]] = {}
    marker = "ok"
    if to_resolve:
        pool = _executor()
        futures = {pool.submit(_resolve_one, h): h for h in to_resolve}
        deadline = started + BATCH_DEADLINE
        while futures:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                marker = "deadline"
                _kill_children()
                for fut in futures:
                    fut.cancel()
                break
            done, _ = wait(futures, timeout=remaining, return_when=FIRST_COMPLETED)
            for fut in done:
                host = futures.pop(fut)
                try:
                    fresh[host] = fut.result() or []
                except Exception:
                    fresh[host] = []
    resolved = failed = 0
    for host in hosts:
        got = fresh.get(host) or []
        if got:
            cache[host] = got
            resolved += 1
        else:
            failed += 1
    for host in keep_hosts:
        got = fresh.get(host) or []
        if got:
            cache[host] = got
    _write_cache(cache)
    keep_addrs = set()
    for host in keep_hosts:
        keep_addrs.update(cache.get(host) or [])
    addresses = []
    seen = set()
    for host in hosts:
        for addr in cache.get(host) or []:
            if addr in keep_addrs or addr in seen:
                continue
            seen.add(addr)
            addresses.append(addr)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    batch = {
        "generation": generation,
        "reason": reason,
        "hosts": len(hosts),
        "resolved": resolved,
        "failed": failed,
        "marker": marker,
        "started": started,
        "elapsed_ms": elapsed_ms,
    }
    return addresses, batch


resolve_batch.__signature__ = __import__("inspect").signature(
    lambda hosts, generation, reason: None
)


def finish_batch(batch, outcome):
    if not isinstance(batch, dict):
        return
    started = batch.get("started", time.monotonic())
    elapsed_ms = int((time.monotonic() - started) * 1000)
    marker = batch.get("marker", "ok")
    if outcome in ("stale", "coalesced", "dropped"):
        marker = outcome
    _append_log(
        f"net gen={batch.get('generation', 0)} reason={batch.get('reason', '')} "
        f"hosts={batch.get('hosts', 0)} resolved={batch.get('resolved', 0)} "
        f"failed={batch.get('failed', 0)} marker={marker} "
        f"apply={outcome} elapsed_ms={elapsed_ms}"
    )


def _apply_result(addresses):
    addrs = [a for a in (addresses or []) if a]
    wrapper = str(setup.wrapper_dest())
    try:
        proc = run_command(
            ["sudo", "-n", wrapper, "replace" if addrs else "flush", "ds"],
            input="\n".join(addrs) + "\n" if addrs else None,
            **({} if addrs else {"stdin": subprocess.DEVNULL}),
            capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
        )
        result = ("on" if addrs else "off") if proc.returncode == 0 else "unavailable"
    except (OSError, subprocess.TimeoutExpired):
        result = "unavailable"
    if result == "unavailable":
        _notice_unavailable()
    return result


def apply(addresses):
    global site_block
    site_block = _apply_result(addresses)
    return site_block


def shutdown():
    global _pool, _noticed, site_block
    _kill_children()
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        done = threading.Event()

        def stop():
            pool.shutdown(wait=True, cancel_futures=True)
            done.set()

        threading.Thread(target=stop, daemon=True).start()
        done.wait(3.0)
    _noticed = False
    site_block = "off"
