"""Hostname resolution, last-good cache, and sudo nft apply."""

from __future__ import annotations

import ipaddress
import os
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

from ds import config, state

BATCH_DEADLINE = 10.0
RESOLVE_TIMEOUT = 2.0
POOL_SIZE = 8

site_block = "off"

_pool = None
_pool_lock = threading.Lock()
_child_lock = threading.Lock()
_children: dict[int, subprocess.Popen] = {}
_noticed = False
_batch: dict | None = None


def _log_path() -> Path:
    data = state.read_json(config.config_path(), None)
    log = data.get("log") if isinstance(data, dict) else None
    if isinstance(log, str) and log:
        return Path(os.path.expanduser(log))
    return state.state_path("log")


def _keep_reachable_hosts() -> list[str]:
    data = state.read_json(config.config_path(), None)
    if not isinstance(data, dict):
        return []
    hosts = data.get("keep_reachable")
    if not isinstance(hosts, list):
        return []
    return [h for h in hosts if isinstance(h, str) and h]


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
            proc.kill()
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
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _notice_unavailable() -> None:
    global _noticed
    if _noticed:
        return
    _noticed = True
    try:
        subprocess.run(
            ["omarchy-notification-send", "Site block unavailable",
             "Wrapper missing or sudo -n distractions-nft refused."],
            timeout=2,
            check=False,
            capture_output=True,
        )
    except OSError:
        pass


def resolve_batch(hosts, generation, reason):
    global _batch
    hosts = [h for h in (hosts or []) if isinstance(h, str) and h]
    keep_hosts = _keep_reachable_hosts()
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
    _batch = {
        "generation": generation,
        "reason": reason,
        "hosts": len(hosts),
        "resolved": resolved,
        "failed": failed,
        "marker": marker,
        "started": started,
    }
    return addresses


def apply(addresses):
    global site_block, _batch
    addrs = [a for a in (addresses or []) if a]
    try:
        if not addrs:
            proc = subprocess.run(
                ["sudo", "-n", "distractions-nft", "flush", "ds"],
                capture_output=True,
                text=True,
            )
            ok = proc.returncode == 0
            site_block = "off" if ok else "unavailable"
            apply_result = "flush" if ok else "unavailable"
        else:
            proc = subprocess.run(
                ["sudo", "-n", "distractions-nft", "replace", "ds"],
                input="\n".join(addrs) + "\n",
                capture_output=True,
                text=True,
            )
            ok = proc.returncode == 0
            site_block = "on" if ok else "unavailable"
            apply_result = "ok" if ok else "unavailable"
    except OSError:
        site_block = "unavailable"
        apply_result = "unavailable"
    if site_block == "unavailable":
        _notice_unavailable()
    meta = _batch or {
        "generation": 0,
        "reason": "apply",
        "hosts": 0,
        "resolved": 0,
        "failed": 0,
        "marker": "ok",
        "started": time.monotonic(),
    }
    elapsed_ms = int((time.monotonic() - meta["started"]) * 1000)
    _append_log(
        f"net gen={meta['generation']} reason={meta['reason']} hosts={meta['hosts']} "
        f"resolved={meta['resolved']} failed={meta['failed']} marker={meta['marker']} "
        f"apply={apply_result} elapsed_ms={elapsed_ms}"
    )
    _batch = None
    return site_block


def shutdown():
    global _pool, _noticed, _batch, site_block
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
    _batch = None
    site_block = "off"
