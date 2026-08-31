"""Focus-mode network block: product list, hosts fragment, and nftables apply/lift."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent
DEFAULTS_PATH = PLUGIN_ROOT / "defaults" / "destinations.json"
CONFIG_PATH = Path(os.environ.get("OMARCHY_FOCUS_CONFIG", Path.home() / ".config/omarchy/focus.json"))
HOSTS_PATH = Path("/etc/hosts")
NFT_TABLE = "omarchy_focus"
HOSTS_BEGIN = "# BEGIN omarchy-focus"
HOSTS_END = "# END omarchy-focus"
LOCK_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "omarchy-focus.block.lock"
DNS_DROPINS = (
    Path("/etc/NetworkManager/dnsmasq.d/omarchy-focus.conf"),
    Path("/etc/dnsmasq.d/omarchy-focus.conf"),
)

_lock_depth = 0
_lock_fp = None

PERMANENT_OPEN = (
    "Telegram",
    "Discord",
    "WhatsApp",
    "Signal",
    "Google Messages",
    "X",
)

USER_ADD_ONLY = ("Bluesky", "Pinterest", "Tumblr")

FALLBACK_CATALOG = {
    "Telegram": [
        "telegram.org",
        "telegram.me",
        "t.me",
        "telesco.pe",
        "tdesktop.com",
        "telegram-cdn.org",
        "telegramcdn.org",
    ],
    "Discord": [
        "discord.com",
        "discordapp.com",
        "discord.gg",
        "discord.media",
        "discordapp.net",
        "discordcdn.com",
    ],
    "WhatsApp": ["whatsapp.com", "whatsapp.net", "wa.me"],
    "Signal": ["signal.org", "signal.art", "whispersystems.org"],
    "Google Messages": ["messages.google.com"],
    "X": ["x.com", "twitter.com", "t.co", "twimg.com"],
}

SINKHOLE_PORT = 53553
SINKHOLE_MARK = 0x0F0C05
SINKHOLE_UNIT = "omarchy-focus-dns"
SINKHOLE_PID = Path("/run/omarchy-focus-dns.pid")
SINKHOLE_SUFFIXES = Path("/run/omarchy-focus.suffixes")

HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$"
)
IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


@contextmanager
def network_lock():
    """Reentrant process lock for focus-state plus network apply/lift."""
    global _lock_depth, _lock_fp
    if _lock_depth == 0:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        handle = open(LOCK_PATH, "w", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        _lock_fp = handle
    _lock_depth += 1
    try:
        yield
    finally:
        _lock_depth -= 1
        if _lock_depth == 0 and _lock_fp is not None:
            fcntl.flock(_lock_fp.fileno(), fcntl.LOCK_UN)
            _lock_fp.close()
            _lock_fp = None


class BlockError(Exception):
    """User-visible apply/lift/list failure."""


class MissingTable(BlockError):
    """nftables table is absent."""


class DefaultsMissing(BlockError):
    """Shipped defaults file is absent or unreadable."""


def notify_user(title: str, body: str = "") -> None:
    cmd = ["omarchy-notification-send", "-u", "normal", "-t", "5000", title]
    if body:
        cmd.append(body)
    try:
        subprocess.check_call(cmd)
        return
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    subprocess.call(["notify-send", "-t", "5000", title, body])


def load_defaults(path: Path | None = None) -> dict:
    defaults_path = path or DEFAULTS_PATH
    if not defaults_path.exists():
        raise DefaultsMissing("shipped defaults set is missing")
    try:
        data = json.loads(defaults_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DefaultsMissing(f"shipped defaults set is unreadable: {exc}") from exc
    if not isinstance(data, dict):
        raise DefaultsMissing("shipped defaults set is not an object")
    catalog = data.get("catalog")
    default = data.get("default")
    if not isinstance(catalog, dict) or not isinstance(default, list):
        raise DefaultsMissing("shipped defaults set is missing catalog or default")
    return data


def load_config(path: Path | None = None) -> dict:
    config_path = path or CONFIG_PATH
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_config(data: dict, path: Path | None = None) -> None:
    config_path = path or CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = config_path.with_name(config_path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(config_path)


def _norm_name(name: str) -> str:
    return " ".join(name.split()).casefold()


def catalog_lookup(catalog: dict, name: str) -> str | None:
    wanted = _norm_name(name)
    for key in catalog:
        if _norm_name(str(key)) == wanted:
            return str(key)
    return None


def shipped_default_names(defaults: dict) -> list[str]:
    names: list[str] = []
    seen = set()
    for raw in defaults.get("default", []):
        name = str(raw).strip()
        if not name:
            continue
        key = catalog_lookup(defaults.get("catalog") or {}, name) or name
        folded = _norm_name(key)
        if folded in seen:
            continue
        seen.add(folded)
        names.append(key)
    for name in PERMANENT_OPEN:
        folded = _norm_name(name)
        if folded in seen:
            continue
        seen.add(folded)
        names.append(name)
    return names


def active_names(
    config: dict | None = None,
    defaults: dict | None = None,
    defaults_path: Path | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    notes = warnings if warnings is not None else []
    loaded = defaults
    missing = False
    if loaded is None:
        try:
            loaded = load_defaults(defaults_path)
        except DefaultsMissing as exc:
            missing = True
            notes.append(str(exc))
            loaded = {"default": [], "catalog": {}}

    if missing:
        notes.append("YouTube is omitted because the shipped defaults set is missing")
    else:
        catalog = loaded.get("catalog") or {}
        if catalog_lookup(catalog, "YouTube") is None and not any(
            _norm_name(str(item)) == "youtube" for item in loaded.get("default", [])
        ):
            notes.append("YouTube is omitted because it is not in the shipped defaults set")

    cfg = config if config is not None else load_config()
    if "destinations" in cfg:
        raw_list = cfg.get("destinations")
        if not isinstance(raw_list, list):
            raw_list = []
        names = []
        seen = set()
        for raw in raw_list:
            if not isinstance(raw, str):
                continue
            accepted, reason = validate_entry(raw, loaded)
            if accepted is None:
                notes.append(reason or "rejected entry")
                continue
            folded = _norm_name(accepted)
            if folded in seen:
                continue
            seen.add(folded)
            names.append(accepted)
        if missing:
            names = [
                item
                for item in names
                if _norm_name(item) != "youtube"
                and (
                    is_hostname_or_ip(item)
                    or catalog_lookup(loaded.get("catalog") or {}, item) is not None
                )
            ]
        return names

    if missing:
        return list(PERMANENT_OPEN)
    return shipped_default_names(loaded)


def is_hostname_or_ip(value: str) -> bool:
    text = value.strip().rstrip(".")
    if IPV4_RE.match(text):
        return all(0 <= int(part) <= 255 for part in text.split("."))
    return bool(HOSTNAME_RE.match(text))


def validate_entry(raw: str, defaults: dict | None = None) -> tuple[str | None, str | None]:
    if not isinstance(raw, str):
        return None, "entry must be a product name or hostname"
    name = " ".join(raw.split())
    if not name:
        return None, "empty entry"
    if any(ch in name for ch in "#;/\\\n\r\t") or ".." in name:
        return None, f"rejected entry: {raw!r}"
    loaded = defaults if defaults is not None else {"catalog": {}}
    catalog = {**FALLBACK_CATALOG, **(loaded.get("catalog") or {})}
    canonical = catalog_lookup(catalog, name)
    if canonical is not None:
        return canonical, None
    if is_hostname_or_ip(name):
        return name.rstrip(".").lower(), None
    return None, f"rejected entry: {raw!r}"


def add_destination(name: str, config_path: Path | None = None, defaults_path: Path | None = None) -> str:
    warnings: list[str] = []
    defaults = None
    try:
        defaults = load_defaults(defaults_path)
    except DefaultsMissing as exc:
        warnings.append(str(exc))
        defaults = {"default": [], "catalog": {}}
    accepted, reason = validate_entry(name, defaults)
    if accepted is None:
        raise BlockError(reason or "rejected entry")
    config = load_config(config_path)
    current = active_names(config, defaults, defaults_path, warnings)
    if any(_norm_name(item) == _norm_name(accepted) for item in current):
        return accepted
    current.append(accepted)
    config["destinations"] = current
    write_config(config, config_path)
    return accepted


def remove_destination(name: str, config_path: Path | None = None, defaults_path: Path | None = None) -> str:
    warnings: list[str] = []
    defaults = None
    try:
        defaults = load_defaults(defaults_path)
    except DefaultsMissing:
        defaults = {"default": [], "catalog": {}}
    accepted, reason = validate_entry(name, defaults)
    target = accepted or " ".join(str(name).split())
    if not target:
        raise BlockError(reason or "rejected entry")
    config = load_config(config_path)
    current = active_names(config, defaults, defaults_path, warnings)
    folded = _norm_name(target)
    kept = [item for item in current if _norm_name(item) != folded]
    if len(kept) == len(current):
        raise BlockError(f"not on the active list: {target}")
    config["destinations"] = kept
    write_config(config, config_path)
    return target


def expand_www(host: str) -> list[str]:
    host = host.strip().rstrip(".").lower()
    hosts = [host]
    if host.count(".") == 1 and not host.startswith("www.") and not IPV4_RE.match(host):
        hosts.append(f"www.{host}")
    return hosts


def hostnames_for(name: str, defaults: dict) -> list[str]:
    catalog = {**FALLBACK_CATALOG, **(defaults.get("catalog") or {})}
    canonical = catalog_lookup(catalog, name)
    raw_hosts: list[str] = []
    if canonical is not None:
        listed = catalog.get(canonical) or []
        if isinstance(listed, list):
            raw_hosts.extend(str(item) for item in listed if isinstance(item, str))
    elif is_hostname_or_ip(name):
        raw_hosts.append(name)
    hosts: list[str] = []
    seen = set()
    for host in raw_hosts:
        for expanded in expand_www(host):
            if expanded in seen:
                continue
            seen.add(expanded)
            hosts.append(expanded)
    return hosts


def active_hostnames(
    config: dict | None = None,
    defaults: dict | None = None,
    defaults_path: Path | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    notes = warnings if warnings is not None else []
    loaded = defaults
    if loaded is None:
        try:
            loaded = load_defaults(defaults_path)
        except DefaultsMissing as exc:
            notes.append(str(exc))
            loaded = {"default": [], "catalog": {}}
    names = active_names(config, loaded, defaults_path, notes)
    hosts: list[str] = []
    seen = set()
    for name in names:
        for host in hostnames_for(name, loaded):
            if host in seen:
                continue
            seen.add(host)
            hosts.append(host)
    return hosts


def suffix_matches(hostname: str, suffix: str) -> bool:
    name = hostname.rstrip(".").lower()
    tail = suffix.rstrip(".").lower()
    return name == tail or name.endswith("." + tail)


def suffix_names(hostnames: list[str]) -> list[str]:
    hosts = [host.rstrip(".").lower() for host in hostnames if not IPV4_RE.match(host)]
    unique = sorted(set(hosts), key=lambda host: (host.count("."), len(host), host))
    kept: list[str] = []
    for host in unique:
        if any(suffix_matches(host, suffix) for suffix in kept):
            continue
        kept.append(host)
    return kept


def dns_fragment(hostnames: list[str]) -> str:
    lines = ["# Managed by omarchy-distraction-space. Do not edit by hand."]
    for suffix in suffix_names(hostnames):
        lines.append(f"address=/{suffix}/0.0.0.0")
        lines.append(f"address=/{suffix}/::")
    return "\n".join(lines) + "\n"


def hosts_fragment(hostnames: list[str]) -> str:
    lines = [HOSTS_BEGIN, "# Managed by omarchy-distraction-space. Do not edit by hand."]
    for host in hostnames:
        if IPV4_RE.match(host):
            continue
        lines.append(f"0.0.0.0 {host}")
        lines.append(f"::1 {host}")
    lines.append(HOSTS_END)
    return "\n".join(lines) + "\n"


def splice_hosts(existing: str, fragment: str | None) -> str:
    text = existing.replace("\r\n", "\n")
    begin = text.find(HOSTS_BEGIN)
    end = text.find(HOSTS_END)
    if begin != -1 and end != -1 and end > begin:
        end = end + len(HOSTS_END)
        while end < len(text) and text[end] == "\n":
            end += 1
        prefix = text[:begin].rstrip("\n")
        suffix = text[end:].lstrip("\n")
        parts = [prefix]
        if fragment:
            if prefix:
                parts.append("")
            parts.append(fragment.rstrip("\n"))
        if suffix:
            parts.append("")
            parts.append(suffix.rstrip("\n"))
        return "\n".join(p for p in parts if p is not None).rstrip("\n") + "\n"
    base = text.rstrip("\n")
    if not fragment:
        return (base + "\n") if base else ""
    if base:
        return base + "\n\n" + fragment
    return fragment


def nft_ruleset(ipv4: list[str], ipv6: list[str], table: str = NFT_TABLE) -> str:
    lines = [
        f"table inet {table}",
        f"flush table inet {table}",
        f"table inet {table} {{",
        "  set v4 {",
        "    type ipv4_addr",
        "    flags interval",
    ]
    if ipv4:
        lines.append("    elements = { " + ", ".join(ipv4) + " }")
    lines.extend(
        [
            "  }",
            "  set v6 {",
            "    type ipv6_addr",
            "    flags interval",
        ]
    )
    if ipv6:
        lines.append("    elements = { " + ", ".join(ipv6) + " }")
    lines.extend(
        [
            "  }",
            "  chain output {",
            "    type filter hook output priority 0; policy accept;",
            "    ip daddr @v4 drop",
            "    ip6 daddr @v6 drop",
            "  }",
            "  chain dnsnat {",
            "    type nat hook output priority -100; policy accept;",
            f"    meta mark {SINKHOLE_MARK:#x} return",
            f"    ip daddr != 127.0.0.1 udp dport 53 dnat to 127.0.0.1:{SINKHOLE_PORT}",
            f"    ip6 daddr != ::1 udp dport 53 dnat to [::1]:{SINKHOLE_PORT}",
            "  }",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def resolve_host(host: str) -> tuple[list[str], list[str]]:
    if IPV4_RE.match(host):
        return [host], []
    ipv4: list[str] = []
    ipv6: list[str] = []
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return [], []
    for family, _type, _proto, _canon, sockaddr in infos:
        if family == socket.AF_INET:
            ipv4.append(sockaddr[0])
        elif family == socket.AF_INET6:
            ipv6.append(sockaddr[0].split("%", 1)[0])
    return _unique(ipv4), _unique(ipv6)


def _unique(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _missing_table_text(text: str) -> bool:
    lowered = text.lower()
    return "does not exist" in lowered or "no such file" in lowered


def privileged(argv: list[str], stdin: str | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    attempts = [argv, ["pkexec", *argv], ["sudo", "-n", *argv]]
    last: Exception | None = None
    details: list[str] = []
    for cmd in attempts:
        try:
            return subprocess.run(
                cmd,
                input=stdin,
                text=True if stdin is not None else None,
                capture_output=True,
                check=True,
                env=env,
            )
        except FileNotFoundError as exc:
            last = exc
            details.append(str(exc))
            continue
        except subprocess.CalledProcessError as exc:
            detail = ((exc.stderr or exc.stdout or "")).strip()
            if _missing_table_text(detail):
                raise MissingTable(detail or "nftables table does not exist") from exc
            last = exc
            if detail:
                details.append(detail)
            continue
    suffix = f": {'; '.join(details)}" if details else ""
    raise BlockError(f"could not run {' '.join(argv)} with privilege{suffix}") from last


class NetworkBackend:
    hosts_path = HOSTS_PATH

    def read_hosts(self) -> str:
        return self.hosts_path.read_text(encoding="utf-8")

    def write_hosts(self, text: str) -> None:
        privileged(["tee", str(self.hosts_path)], stdin=text)

    def nft_available(self) -> bool:
        return shutil.which("nft") is not None

    def nft_list(self) -> str | None:
        if not self.nft_available():
            raise BlockError("nftables (nft) is not available")
        try:
            result = privileged(["nft", "list", "table", "inet", NFT_TABLE])
        except MissingTable:
            return None
        return result.stdout

    def nft_apply(self, ruleset: str) -> None:
        if not self.nft_available():
            raise BlockError("nftables (nft) is not available")
        privileged(["nft", "-f", "-"], stdin=ruleset)

    def nft_delete(self) -> None:
        existing = self.nft_list()
        if existing is None:
            return
        privileged(["nft", "delete", "table", "inet", NFT_TABLE])

    def resolve(self, host: str) -> tuple[list[str], list[str]]:
        return resolve_host(host)

    def flush_conntrack(self, addresses: list[str]) -> None:
        for address in addresses:
            try:
                privileged(["conntrack", "-D", "-d", address])
            except BlockError:
                return

    def dns_targets(self) -> list[Path]:
        return [path for path in DNS_DROPINS if path.parent.is_dir()]

    def read_dns(self, path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write_dns(self, path: Path, text: str | None) -> None:
        if text is None:
            if path.exists():
                privileged(["rm", "-f", str(path)])
            return
        privileged(["tee", str(path)], stdin=text)

    def reload_dns(self) -> None:
        for argv in (
            ["systemctl", "reload", "NetworkManager"],
            ["systemctl", "reload", "dnsmasq"],
            ["killall", "-HUP", "dnsmasq"],
        ):
            try:
                privileged(argv)
                return
            except BlockError:
                continue

    def read_suffixes(self) -> list[str] | None:
        if not SINKHOLE_SUFFIXES.exists():
            return None
        return [line.strip() for line in SINKHOLE_SUFFIXES.read_text(encoding="utf-8").splitlines() if line.strip()]

    def sinkhole_running(self) -> bool:
        try:
            privileged(["systemctl", "is-active", "--quiet", SINKHOLE_UNIT])
            return True
        except BlockError:
            pass
        if SINKHOLE_PID.exists():
            pid = SINKHOLE_PID.read_text(encoding="utf-8").strip()
            if pid.isdigit():
                try:
                    os.kill(int(pid), 0)
                    return True
                except OSError:
                    return False
        return False

    def wait_sinkhole_ready(self) -> None:
        query = b"\x00\x01\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x00\x01"
        deadline = time.time() + 2
        last = None
        while time.time() < deadline:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.settimeout(0.3)
                sock.sendto(query, ("127.0.0.1", SINKHOLE_PORT))
                sock.recvfrom(512)
                return
            except OSError as exc:
                last = exc
            finally:
                sock.close()
        raise BlockError(f"suffix DNS sinkhole did not become ready: {last}")

    def start_sinkhole(self, suffixes: list[str]) -> None:
        privileged(["tee", str(SINKHOLE_SUFFIXES)], stdin="\n".join(suffixes) + "\n")
        script = str(PLUGIN_ROOT / "focus_dns.py")
        if self.sinkhole_running():
            privileged(["killall", "-HUP", "focus_dns.py"])
            self.wait_sinkhole_ready()
            return
        try:
            privileged(
                [
                    "systemd-run",
                    f"--unit={SINKHOLE_UNIT}",
                    sys.executable,
                    script,
                    "--suffixes",
                    str(SINKHOLE_SUFFIXES),
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(SINKHOLE_PORT),
                ]
            )
        except BlockError:
            privileged(
                [
                    sys.executable,
                    script,
                    "--daemon",
                    "--suffixes",
                    str(SINKHOLE_SUFFIXES),
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(SINKHOLE_PORT),
                    "--pid",
                    str(SINKHOLE_PID),
                ]
            )
        self.wait_sinkhole_ready()

    def stop_sinkhole(self) -> None:
        errors = []
        try:
            privileged(["systemctl", "stop", SINKHOLE_UNIT])
        except BlockError as exc:
            errors.append(str(exc))
        if SINKHOLE_PID.exists():
            try:
                pid = SINKHOLE_PID.read_text(encoding="utf-8").strip()
                if pid.isdigit():
                    privileged(["kill", pid])
            except (OSError, BlockError) as exc:
                errors.append(str(exc))
            try:
                privileged(["rm", "-f", str(SINKHOLE_PID)])
            except BlockError as exc:
                errors.append(str(exc))
        if self.sinkhole_running():
            raise BlockError("could not stop the suffix DNS sinkhole: " + "; ".join(errors))


def apply_block(
    backend: NetworkBackend | None = None,
    config: dict | None = None,
    defaults_path: Path | None = None,
    notify: bool = True,
) -> None:
    backend = backend or NetworkBackend()
    with network_lock():
        _apply_block_locked(backend, config, defaults_path, notify)


def _apply_block_locked(
    backend: NetworkBackend,
    config: dict | None,
    defaults_path: Path | None,
    notify: bool,
) -> None:
    if not backend.nft_available():
        message = "nftables (nft) is not available"
        if notify:
            notify_user("Focus mode", message)
        raise BlockError(message)
    warnings: list[str] = []
    loaded = None
    try:
        loaded = load_defaults(defaults_path)
    except DefaultsMissing as exc:
        warnings.append(str(exc))
        loaded = {"default": [], "catalog": {}}
    names = active_names(config, loaded, defaults_path, warnings)
    unexpanded = [name for name in names if not hostnames_for(name, loaded)]
    if unexpanded:
        message = "Could not apply the network block: no hostnames for " + ", ".join(unexpanded)
        if notify:
            notify_user("Focus mode", message)
        raise BlockError(message)
    hostnames = active_hostnames(config, loaded, defaults_path, warnings)
    if notify:
        for warning in warnings:
            notify_user("Focus mode", warning)

    previous_hosts = backend.read_hosts()
    previous_nft = backend.nft_list()
    dns_targets = backend.dns_targets()
    previous_dns = {str(path): backend.read_dns(path) for path in dns_targets}
    new_hosts = splice_hosts(previous_hosts, hosts_fragment(hostnames))
    new_dns = dns_fragment(hostnames)

    ipv4: list[str] = []
    ipv6: list[str] = []
    for host in hostnames:
        v4, v6 = backend.resolve(host)
        ipv4.extend(v4)
        ipv6.extend(v6)
    ipv4 = _unique(ipv4)
    ipv6 = _unique(ipv6)
    ruleset = nft_ruleset(ipv4, ipv6)

    hosts_written = False
    nft_written = False
    dns_written: list[str] = []
    previous_suffixes = backend.read_suffixes() if hasattr(backend, "read_suffixes") else None
    sinkhole_started = False
    try:
        backend.start_sinkhole(suffix_names(hostnames))
        sinkhole_started = True
        backend.write_hosts(new_hosts)
        hosts_written = True
        backend.nft_apply(ruleset)
        nft_written = True
        for path in dns_targets:
            backend.write_dns(path, new_dns)
            dns_written.append(str(path))
        if dns_written:
            backend.reload_dns()
    except Exception as exc:
        if hosts_written:
            try:
                backend.write_hosts(previous_hosts)
            except Exception:
                pass
        if nft_written:
            try:
                backend.nft_delete()
                if previous_nft:
                    backend.nft_apply(previous_nft)
            except Exception:
                pass
        for path_text in dns_written:
            try:
                backend.write_dns(Path(path_text), previous_dns.get(path_text))
            except Exception:
                pass
        if sinkhole_started:
            try:
                if previous_suffixes:
                    backend.start_sinkhole(previous_suffixes)
                else:
                    backend.stop_sinkhole()
            except Exception:
                pass
        message = f"Could not apply the network block: {exc}"
        if notify:
            notify_user("Focus mode", message)
        raise BlockError(message) from exc

    backend.flush_conntrack(ipv4 + ipv6)


def lift_block(backend: NetworkBackend | None = None, notify: bool = True) -> None:
    backend = backend or NetworkBackend()
    with network_lock():
        _lift_block_locked(backend, notify)


def _lift_block_locked(backend: NetworkBackend, notify: bool) -> None:
    if not backend.nft_available():
        message = "nftables (nft) is not available"
        if notify:
            notify_user("Focus mode", message)
        raise BlockError(message)
    previous_hosts = backend.read_hosts()
    dns_targets = backend.dns_targets()
    previous_dns = {str(path): backend.read_dns(path) for path in dns_targets}
    new_hosts = splice_hosts(previous_hosts, None)
    hosts_written = False
    dns_written: list[str] = []
    try:
        if new_hosts != previous_hosts:
            backend.write_hosts(new_hosts)
            hosts_written = True
        for path in dns_targets:
            backend.write_dns(path, None)
            dns_written.append(str(path))
        if dns_written:
            backend.reload_dns()
        backend.nft_delete()
        backend.stop_sinkhole()
    except Exception as exc:
        if hosts_written:
            try:
                backend.write_hosts(previous_hosts)
            except Exception:
                pass
        for path_text in dns_written:
            try:
                backend.write_dns(Path(path_text), previous_dns.get(path_text))
            except Exception:
                pass
        message = f"Could not lift the network block: {exc}"
        if notify:
            notify_user("Focus mode", message)
        raise BlockError(message) from exc


def report_defaults_warnings(warnings: list[str], notify: bool = True) -> None:
    if not notify:
        return
    for warning in warnings:
        notify_user("Focus mode", warning)
