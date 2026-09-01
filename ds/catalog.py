"""Shipped catalog and expansion of list entries into identities."""

import json
import re
from pathlib import Path

DEFAULT_LIST = [
    "Telegram", "Discord", "WhatsApp", "Signal", "Google Messages",
    "Facebook", "Instagram", "Threads", "X", "Reddit", "TikTok",
    "Snapchat", "YouTube", "Twitch", "Netflix",
]


def load_catalog():
    path = Path(__file__).resolve().parent.parent / "catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))


def names():
    return list(load_catalog())


def is_hostname(s):
    return (
        isinstance(s, str) and s and "." in s
        and "://" not in s and "/" not in s and not any(c.isspace() for c in s)
    )


def is_class_entry(s):
    return isinstance(s, str) and s.startswith("class=") and bool(s[6:])


def pwa_class(host):
    return "^chrome-" + re.escape(host) + "__.*$"


def _ident(name, classes, hosts, spec=None):
    spec = spec or {}
    return {
        "name": name, "classes": classes, "hosts": hosts,
        "senders": list(spec.get("senders") or []),
        "audio": dict(spec.get("audio") or {}),
    }


def _expand_product(name, spec):
    classes = [spec["class"]] if spec.get("class") else []
    hosts = list(spec.get("hosts") or [])
    pwa = spec.get("pwa")
    if pwa or hosts:
        classes.append(pwa_class(pwa or hosts[0]))
    return _ident(name, classes, hosts, spec)


def expand_entry(entry):
    if isinstance(entry, str):
        if is_class_entry(entry):
            return _ident(entry, [entry[6:]], [])
        if is_hostname(entry):
            twin = entry[4:] if entry.startswith("www.") else "www." + entry
            hosts = [entry] if twin == entry else [entry, twin]
            return _ident(entry, [pwa_class(entry)], hosts)
        spec = load_catalog().get(entry)
        return _expand_product(entry, spec) if spec else None
    if isinstance(entry, dict):
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            return None
        hosts = list(entry["hosts"]) if isinstance(entry.get("hosts"), list) else []
        classes = [entry["class"]] if entry.get("class") else []
        if hosts:
            classes.append(pwa_class(hosts[0]))
        return _ident(name, classes, hosts, entry)
    return None


def expand(cfg):
    return [item for entry in (cfg or {}).get("list") or [] if (item := expand_entry(entry))]


def cmd_catalog(args):
    print("\n".join(names()))
    return 0
