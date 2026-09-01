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

# A blocked host and a wanted host can share one CDN anycast address, and an
# IP-only block cannot tell them apart: pbs.twimg.com and grok.com both answer
# on 104.18.28.234, so blocking X takes Grok down with it. Addresses that also
# serve a keep-reachable host are dropped from the nftables set. Suffix DNS
# blocking is exact and keeps blocking the site itself.
KEEP_REACHABLE_DEFAULT = (
    "grok.com",
    "www.grok.com",
    "assets.grok.com",
    "api.x.ai",
    "grok.x.ai",
)

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
SINKHOLE_UNIT = "omarchy-focus-dns"
SINKHOLE_PID = Path("/run/omarchy-focus-dns.pid")
SINKHOLE_SUFFIXES = Path("/run/omarchy-focus.suffixes")
SINKHOLE_UPSTREAMS = Path("/run/omarchy-focus.upstreams")
RESOLVED_DROPIN = Path("/etc/systemd/resolved.conf.d/omarchy-focus.conf")
RESOLV_PATH = Path("/etc/resolv.conf")
RESOLV_BACKUP = Path("/run/omarchy-focus.resolv.bak")

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
            catalog = {**FALLBACK_CATALOG, **(loaded.get("catalog") or {})}
            names = [
                item
                for item in names
                if _norm_name(item) != "youtube"
                and (
                    is_hostname_or_ip(item)
                    or catalog_lookup(catalog, item) is not None
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


def resolved_fragment(suffixes: list[str], port: int = SINKHOLE_PORT) -> str:
    domains = " ".join(f"~{suffix}" for suffix in suffixes)
    return (
        "# Managed by omarchy-distraction-space. Do not edit by hand.\n"
        "[Resolve]\n"
        f"DNS=127.0.0.1:{port} [::1]:{port}\n"
        f"Domains={domains}\n"
    )


def resolv_fragment() -> str:
    return (
        "# Managed by omarchy-distraction-space. Do not edit by hand.\n"
        "nameserver 127.0.0.1\n"
        "nameserver ::1\n"
    )


def encode_dns_name(name: str) -> bytes:
    out = bytearray()
    labels = [label for label in name.rstrip(".").split(".") if label]
    for label in labels:
        encoded = label.encode("ascii")
        out.append(len(encoded))
        out.extend(encoded)
    out.append(0)
    return bytes(out)


def dns_query_packet(name: str, qtype: int) -> bytes:
    return b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00" + encode_dns_name(name) + qtype.to_bytes(2, "big") + b"\x00\x01"


def sinkhole_probe_name(suffix: str) -> str:
    tail = suffix.rstrip(".").lower()
    if not tail:
        return "blocked.invalid"
    return f"r4---sn-abc.{tail}"


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


def keep_reachable_hosts(config: dict | None = None, path: Path | None = None) -> list[str]:
    """Hosts that must survive an IP block, shipped defaults plus config."""
    data = load_config(path) if config is None else config
    names = list(KEEP_REACHABLE_DEFAULT)
    extra = data.get("keep_reachable") if isinstance(data, dict) else None
    if isinstance(extra, list):
        names.extend(item for item in extra if isinstance(item, str))
    kept: list[str] = []
    seen: set[str] = set()
    for raw in names:
        host = raw.strip().rstrip(".").lower()
        if not host or host in seen or not is_hostname_or_ip(host):
            continue
        seen.add(host)
        kept.append(host)
    return kept


def keep_reachable_addrs(
    config: dict | None = None,
    resolve=None,
    path: Path | None = None,
) -> set[str]:
    """Every address a keep-reachable host answers on right now."""
    lookup = resolve or resolve_host
    addrs: set[str] = set()
    for host in keep_reachable_hosts(config, path):
        try:
            ipv4, ipv6 = lookup(host)
        except Exception:
            continue
        addrs.update(ipv4)
        addrs.update(ipv6)
    return addrs


def drop_keep_reachable(addresses: list[str], keep: set[str]) -> list[str]:
    """Drop one host's shared addresses, unless that would unblock it outright.

    The carve-out exists to rescue an address a wanted host happens to share,
    not to lift a block. If every address of a blocked host looks shared the
    block wins, so a resolver that answers the same for every name -- a captive
    portal, an NXDOMAIN hijack, a wildcard -- cannot empty the set.
    """
    kept = [address for address in addresses if address not in keep]
    return kept if kept else list(addresses)


SINKHOLE_V4 = {"0.0.0.0", "127.0.0.1"}
SINKHOLE_V6 = {"::", "::1", "0:0:0:0:0:0:0:1"}


def usable_v4(address: str) -> bool:
    return address not in SINKHOLE_V4 and not address.startswith("127.")


def usable_v6(address: str) -> bool:
    lowered = address.lower().split("%", 1)[0]
    return lowered not in SINKHOLE_V6 and not lowered.startswith("fe80:")


def parse_nft_sets(ruleset: str | None) -> tuple[list[str], list[str]]:
    if not ruleset:
        return [], []
    blocks = re.findall(r"elements\s*=\s*\{([^}]*)\}", ruleset)
    parsed: list[list[str]] = []
    for block in blocks:
        parsed.append([item.strip() for item in block.split(",") if item.strip()])
    ipv4 = [item for item in (parsed[0] if parsed else []) if usable_v4(item)]
    ipv6 = [item for item in (parsed[1] if len(parsed) > 1 else []) if usable_v6(item)]
    return ipv4, ipv6


def parse_dns_addresses(reply: bytes) -> tuple[list[str], list[str]]:
    import focus_dns

    if len(reply) < 12:
        return [], []
    parsed = focus_dns.parse_qname(reply)
    if parsed is None:
        return [], []
    pos = parsed[1]
    ancount = int.from_bytes(reply[6:8], "big")
    ipv4: list[str] = []
    ipv6: list[str] = []
    for _ in range(ancount):
        if pos >= len(reply):
            break
        if reply[pos] & 0xC0:
            pos += 2
        else:
            while pos < len(reply) and reply[pos] != 0:
                pos += 1 + reply[pos]
            pos += 1
        if pos + 10 > len(reply):
            break
        rtype = int.from_bytes(reply[pos : pos + 2], "big")
        rdlen = int.from_bytes(reply[pos + 8 : pos + 10], "big")
        pos += 10
        rdata = reply[pos : pos + rdlen]
        pos += rdlen
        if rtype == 1 and len(rdata) == 4:
            ipv4.append(".".join(str(part) for part in rdata))
        elif rtype == 28 and len(rdata) == 16:
            ipv6.append(socket.inet_ntop(socket.AF_INET6, rdata))
    return ipv4, ipv6


def resolve_via_upstreams(host: str, servers: list[str]) -> tuple[list[str], list[str]]:
    import focus_dns

    if IPV4_RE.match(host):
        return [host], []
    ipv4: list[str] = []
    ipv6: list[str] = []
    for qtype in (1, 28):
        reply = focus_dns.forward(dns_query_packet(host, qtype), servers)
        if not reply:
            continue
        got_v4, got_v6 = parse_dns_addresses(reply)
        ipv4.extend(got_v4)
        ipv6.extend(got_v6)
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


def _command_output_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


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
                text=True,
                capture_output=True,
                check=True,
                env=env,
            )
        except FileNotFoundError as exc:
            last = exc
            details.append(str(exc))
            continue
        except subprocess.CalledProcessError as exc:
            detail = _command_output_text(exc.stderr or exc.stdout).strip()
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

    def resolve(self, host: str, upstreams: list[str] | None = None) -> tuple[list[str], list[str]]:
        if upstreams:
            return resolve_via_upstreams(host, upstreams)
        return resolve_host(host)

    def flush_conntrack(self, addresses: list[str]) -> None:
        for address in addresses:
            try:
                privileged(["conntrack", "-D", "-d", address])
            except BlockError:
                continue

    def dnsmasq_owner(self) -> str | None:
        nm = Path("/etc/NetworkManager/NetworkManager.conf")
        if nm.exists():
            try:
                text = nm.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            if re.search(r"(?im)^\s*dns\s*=\s*dnsmasq\b", text):
                return "nm"
        try:
            privileged(["systemctl", "is-active", "--quiet", "dnsmasq"])
            return "system"
        except BlockError:
            return None

    def dns_targets(self) -> list[Path]:
        owner = self.dnsmasq_owner()
        if owner == "nm":
            return [Path("/etc/NetworkManager/dnsmasq.d/omarchy-focus.conf")]
        if owner == "system":
            return [Path("/etc/dnsmasq.d/omarchy-focus.conf")]
        return []

    def read_dns(self, path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write_dns(self, path: Path, text: str | None) -> None:
        if text is None:
            if path.exists():
                privileged(["rm", "-f", str(path)])
            return
        privileged(["mkdir", "-p", str(path.parent)])
        privileged(["tee", str(path)], stdin=text)

    def resolved_active(self) -> bool:
        if Path("/run/systemd/resolve/resolv.conf").exists():
            return True
        try:
            privileged(["systemctl", "is-active", "--quiet", "systemd-resolved"])
            return True
        except BlockError:
            return False

    def resolver_kind(self) -> str:
        if self.resolved_active():
            return "resolved"
        if self.dnsmasq_owner():
            return "dnsmasq"
        return "resolv"

    def sinkhole_port(self, kind: str) -> int:
        return 53 if kind == "resolv" else SINKHOLE_PORT

    def read_resolved(self) -> str | None:
        if not RESOLVED_DROPIN.exists():
            return None
        return RESOLVED_DROPIN.read_text(encoding="utf-8")

    def write_resolved(self, text: str | None) -> None:
        if text is None:
            if RESOLVED_DROPIN.exists():
                privileged(["rm", "-f", str(RESOLVED_DROPIN)])
            return
        privileged(["mkdir", "-p", str(RESOLVED_DROPIN.parent)])
        privileged(["tee", str(RESOLVED_DROPIN)], stdin=text)

    def read_resolv(self) -> str:
        if not RESOLV_PATH.exists():
            return ""
        return RESOLV_PATH.read_text(encoding="utf-8")

    def write_resolv(self, text: str) -> None:
        privileged(["tee", str(RESOLV_PATH)], stdin=text)

    def backup_resolv(self) -> str | None:
        current = self.read_resolv()
        if not RESOLV_BACKUP.exists() and current:
            privileged(["tee", str(RESOLV_BACKUP)], stdin=current)
        return current

    def restore_resolv(self) -> None:
        if not RESOLV_BACKUP.exists():
            return
        text = RESOLV_BACKUP.read_text(encoding="utf-8")
        self.write_resolv(text)
        privileged(["rm", "-f", str(RESOLV_BACKUP)])

    def capture_upstreams(self) -> list[str]:
        live = self._live_upstreams()
        if RESOLV_BACKUP.exists():
            existing = self.read_upstreams()
            if existing:
                return existing
        return live

    def _live_upstreams(self) -> list[str]:
        servers: list[str] = []
        for path in (Path("/run/systemd/resolve/resolv.conf"), RESOLV_PATH):
            if not path.exists():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            found = []
            for line in lines:
                parts = line.split()
                if len(parts) < 2 or parts[0] != "nameserver":
                    continue
                server = parts[1]
                if server.startswith("127.") or server in {":1", "::1"}:
                    continue
                found.append(server)
            if found:
                servers = found
                break
        return _unique(servers)

    def read_upstreams(self) -> list[str] | None:
        if not SINKHOLE_UPSTREAMS.exists():
            return None
        return [line.strip() for line in SINKHOLE_UPSTREAMS.read_text(encoding="utf-8").splitlines() if line.strip()]

    def write_upstreams(self, servers: list[str]) -> None:
        privileged(["tee", str(SINKHOLE_UPSTREAMS)], stdin="".join(f"{item}\n" for item in servers))

    def clear_runtime_files(self) -> None:
        for path in (SINKHOLE_UPSTREAMS, SINKHOLE_SUFFIXES):
            if path.exists():
                privileged(["rm", "-f", str(path)])

    def reload_resolver(self, kind: str) -> None:
        if kind == "resolved":
            try:
                privileged(["systemctl", "reload", "systemd-resolved"])
            except BlockError:
                privileged(["systemctl", "restart", "systemd-resolved"])
            try:
                privileged(["resolvectl", "flush-caches"])
            except BlockError:
                pass
            return
        if kind == "dnsmasq":
            owner = self.dnsmasq_owner()
            if owner == "nm":
                privileged(["systemctl", "reload", "NetworkManager"])
                return
            if owner == "system":
                try:
                    privileged(["systemctl", "reload", "dnsmasq"])
                except BlockError:
                    privileged(["killall", "-HUP", "dnsmasq"])
                return
            raise BlockError("dnsmasq is not the active resolver")
        return

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

    def query_sinkhole(self, name: str, qtype: int, port: int, address: str = "127.0.0.1") -> bytes:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_DGRAM)
        try:
            sock.settimeout(0.4)
            sock.sendto(dns_query_packet(name, qtype), (address, port))
            data, _addr = sock.recvfrom(512)
            return data
        finally:
            sock.close()

    def wait_sinkhole_ready(self, suffixes: list[str], port: int = SINKHOLE_PORT) -> None:
        if not suffixes:
            raise BlockError("suffix DNS sinkhole has no suffixes to serve")
        probe = sinkhole_probe_name(suffixes[0])
        deadline = time.time() + 3
        last: Exception | None = None
        while time.time() < deadline:
            try:
                answer = self.query_sinkhole(probe, 1, port)
                if answer.endswith(b"\x00\x00\x00\x00"):
                    aaaa = self.query_sinkhole(probe, 28, port)
                    if aaaa.endswith(bytes(16)):
                        return
                    last = BlockError("suffix sinkhole AAAA was not ::")
                    continue
                last = BlockError("suffix sinkhole A was not 0.0.0.0")
            except (OSError, BlockError) as exc:
                last = exc
            time.sleep(0.05)
        raise BlockError(f"suffix DNS sinkhole did not answer {probe} with 0.0.0.0/:: : {last}")

    def verify_suffix_block(self, suffixes: list[str], port: int, kind: str) -> None:
        if kind == "dnsmasq":
            self.wait_sinkhole_ready(suffixes, 53)
        elif kind in {"resolved", "resolv"}:
            self.wait_sinkhole_ready(suffixes, port)
        if kind == "resolved":
            probe = sinkhole_probe_name(suffixes[0])
            try:
                result = privileged(["resolvectl", "query", "--legend=no", probe])
            except BlockError as exc:
                raise BlockError(f"systemd-resolved did not apply the suffix block: {exc}") from exc
            text = (result.stdout or "").lower()
            if "0.0.0.0" not in text and "::" not in text:
                raise BlockError(f"systemd-resolved still resolves {probe} instead of sinkholing it")
        self.verify_libc_suffix(suffixes)

    def verify_libc_suffix(self, suffixes: list[str]) -> None:
        probe = sinkhole_probe_name(suffixes[0])
        ipv4, ipv6 = resolve_host(probe)
        leaked = [item for item in ipv4 if usable_v4(item)] + [item for item in ipv6 if usable_v6(item)]
        if leaked:
            raise BlockError(f"system resolver still reaches {probe} at {', '.join(leaked)}")
        if not ipv4 and not ipv6:
            raise BlockError(f"system resolver did not sinkhole {probe}")

    def _launch_sinkhole(self, port: int) -> None:
        script = str(PLUGIN_ROOT / "focus_dns.py")
        privileged(
            [
                "systemd-run",
                f"--unit={SINKHOLE_UNIT}",
                sys.executable,
                script,
                "--suffixes",
                str(SINKHOLE_SUFFIXES),
                "--upstreams",
                str(SINKHOLE_UPSTREAMS),
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
            ]
        )

    def start_sinkhole(self, suffixes: list[str], port: int = SINKHOLE_PORT, upstreams: list[str] | None = None) -> None:
        previous_suffixes = self.read_suffixes()
        previous_upstreams = self.read_upstreams()
        was_running = self.sinkhole_running()
        try:
            if upstreams is not None:
                self.write_upstreams(upstreams)
            privileged(["tee", str(SINKHOLE_SUFFIXES)], stdin="\n".join(suffixes) + "\n")
            if was_running:
                self.stop_sinkhole()
            self._launch_sinkhole(port)
            self.wait_sinkhole_ready(suffixes, port)
        except Exception:
            if previous_suffixes:
                try:
                    privileged(["tee", str(SINKHOLE_SUFFIXES)], stdin="\n".join(previous_suffixes) + "\n")
                except BlockError:
                    pass
            if previous_upstreams is not None:
                try:
                    self.write_upstreams(previous_upstreams)
                except BlockError:
                    pass
            if was_running and previous_suffixes:
                try:
                    if self.sinkhole_running():
                        self.stop_sinkhole()
                    self._launch_sinkhole(port)
                    self.wait_sinkhole_ready(previous_suffixes, port)
                except Exception:
                    pass
            elif not was_running:
                try:
                    self.stop_sinkhole()
                except Exception:
                    pass
            raise

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
    if not hostnames:
        message = "Could not apply the network block: the active list expanded to no hostnames"
        if notify:
            notify_user("Focus mode", message)
        raise BlockError(message)
    if notify:
        for warning in warnings:
            notify_user("Focus mode", warning)

    hosts_written = False
    nft_written = False
    dns_written: list[str] = []
    resolved_written = False
    resolv_written = False
    sinkhole_started = False
    previous_hosts = ""
    previous_nft = None
    previous_dns: dict[str, str | None] = {}
    previous_resolved = None
    previous_resolv = None
    previous_suffixes = None
    ipv4: list[str] = []
    ipv6: list[str] = []
    port = SINKHOLE_PORT

    def rollback() -> None:
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
        if dns_written:
            try:
                backend.reload_resolver("dnsmasq")
            except Exception:
                pass
        if resolved_written:
            try:
                backend.write_resolved(previous_resolved)
                backend.reload_resolver("resolved")
            except Exception:
                pass
        if resolv_written:
            try:
                if previous_resolv is not None:
                    backend.write_resolv(previous_resolv)
            except Exception:
                pass
        if sinkhole_started:
            try:
                if previous_suffixes:
                    backend.start_sinkhole(previous_suffixes, port)
                else:
                    backend.stop_sinkhole()
            except Exception:
                pass

    try:
        previous_hosts = backend.read_hosts()
        previous_nft = backend.nft_list()
        dns_targets = backend.dns_targets()
        previous_dns = {str(path): backend.read_dns(path) for path in dns_targets}
        previous_resolved = backend.read_resolved() if hasattr(backend, "read_resolved") else None
        previous_resolv = backend.read_resolv() if hasattr(backend, "read_resolv") else None
        previous_suffixes = backend.read_suffixes() if hasattr(backend, "read_suffixes") else None
        new_hosts = splice_hosts(previous_hosts, hosts_fragment(hostnames))
        suffixes = suffix_names(hostnames)
        kind = backend.resolver_kind() if suffixes else None
        port = backend.sinkhole_port(kind) if kind else SINKHOLE_PORT

        captured = backend.capture_upstreams() if hasattr(backend, "capture_upstreams") else []
        if suffixes and kind == "resolv" and not captured:
            raise BlockError("no upstream DNS servers captured for unblocked names")
        keep = keep_reachable_addrs(config)
        for host in hostnames:
            v4, v6 = backend.resolve(host, captured or None)
            usable = [item for item in v4 if usable_v4(item)]
            usable += [item for item in v6 if usable_v6(item)]
            for item in drop_keep_reachable(usable, keep):
                (ipv6 if ":" in item else ipv4).append(item)
        ipv4 = _unique(ipv4)
        ipv6 = _unique(ipv6)
        ruleset = nft_ruleset(ipv4, ipv6)

        if suffixes and kind in {"resolved", "resolv"}:
            backend.start_sinkhole(suffixes, port, captured)
            sinkhole_started = True
        backend.write_hosts(new_hosts)
        hosts_written = True
        backend.nft_apply(ruleset)
        nft_written = True
        if suffixes and kind == "resolved":
            backend.write_resolved(resolved_fragment(suffixes, port))
            resolved_written = True
            backend.reload_resolver("resolved")
            backend.verify_suffix_block(suffixes, port, "resolved")
        elif suffixes and kind == "dnsmasq":
            if not dns_targets:
                raise BlockError("dnsmasq is the resolver but no drop-in directory is available")
            new_dns = dns_fragment(hostnames)
            for path in dns_targets:
                backend.write_dns(path, new_dns)
                dns_written.append(str(path))
            backend.reload_resolver("dnsmasq")
            backend.verify_suffix_block(suffixes, 53, "dnsmasq")
        elif suffixes and kind == "resolv":
            if hasattr(backend, "backup_resolv"):
                backend.backup_resolv()
            backend.write_resolv(resolv_fragment())
            resolv_written = True
            backend.verify_suffix_block(suffixes, port, "resolv")
    except Exception as exc:
        rollback()
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
    hosts_written = False
    dns_written: list[str] = []
    resolved_cleared = False
    previous_hosts = ""
    previous_dns: dict[str, str | None] = {}
    previous_resolved = None
    try:
        previous_hosts = backend.read_hosts()
        dns_targets = backend.dns_targets()
        previous_dns = {str(path): backend.read_dns(path) for path in dns_targets}
        previous_resolved = backend.read_resolved() if hasattr(backend, "read_resolved") else None
        new_hosts = splice_hosts(previous_hosts, None)
        if new_hosts != previous_hosts:
            backend.write_hosts(new_hosts)
            hosts_written = True
        if hasattr(backend, "write_resolved") and previous_resolved:
            backend.write_resolved(None)
            resolved_cleared = True
            backend.reload_resolver("resolved")
        if hasattr(backend, "restore_resolv"):
            backend.restore_resolv()
        for path in dns_targets:
            if backend.read_dns(path) is None:
                continue
            backend.write_dns(path, None)
            dns_written.append(str(path))
        if dns_written:
            backend.reload_resolver("dnsmasq")
        backend.nft_delete()
        backend.stop_sinkhole()
        if hasattr(backend, "clear_runtime_files"):
            backend.clear_runtime_files()
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
        if resolved_cleared:
            try:
                backend.write_resolved(previous_resolved)
                backend.reload_resolver("resolved")
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
