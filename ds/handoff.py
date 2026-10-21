"""Handoff rules: which web links a native app can open, and as what URI.

A rule names an app, the URI scheme its handler takes, the hosts it covers, and
one or more link shapes. A shape's `path` is a regular expression matched
against the whole raw path (never percent-decoded); `query` maps a parameter
name to `{"pattern": ..., "required": ...}`; with `strict`, any other query
parameter makes the shape refuse the link, for apps whose link carries meaning
the URI would drop; `uri` is a template whose `{name}`
placeholders come from the path's named groups and the query parameters, with
`{url}` standing for the whole original link. Every captured value must also be
free of `%`, `/`, whitespace and control characters, so a crafted link cannot
put anything into the app's URI that the rule did not mean.

This module only reads rules and matches links. It neither logs nor launches:
`ds.launch` owns both, and gets the rules that did not load back as reasons.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

REFUSED_SCHEMES = frozenset({
    "http", "https", "file", "about", "javascript", "data", "ftp", "mailto", "ws", "wss",
})
_SCHEME_NAME = re.compile(r"[a-z][a-z0-9+.-]*")
_RULE_KEYS = frozenset({"app", "scheme", "hosts", "shapes"})
_SHAPE_KEYS = frozenset({"path", "query", "strict", "uri"})
_QUERY_KEYS = frozenset({"pattern", "required"})
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# What any captured value may hold, whatever its own pattern allows.
_SAFE_VALUE = re.compile(r"[^%/\s\x00-\x1f\x7f]+")
# What the whole link may not hold when a template wraps it.
_URL_FORBIDDEN = re.compile(r"[\s\"'<>\\`\x00-\x1f\x7f]")
_DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass(frozen=True)
class Shape:
    path: re.Pattern
    query: tuple  # ((name, pattern, required), ...)
    uri: str
    strict: bool = False


@dataclass(frozen=True)
class Rule:
    app: str
    scheme: str
    hosts: frozenset
    shapes: tuple


def shipped():
    """The rules the plugin ships, as raw objects, in file order."""
    path = Path(__file__).resolve().parent.parent / "handoff.json"
    return json.loads(path.read_text(encoding="utf-8"))


def scheme_ok(scheme):
    return isinstance(scheme, str) and bool(_SCHEME_NAME.fullmatch(scheme)) and scheme not in REFUSED_SCHEMES


def _host(h):
    return h.strip().lower().rstrip(".") if isinstance(h, str) else ""


def _parse_shape(obj):
    if not isinstance(obj, dict):
        return "a shape is not an object"
    extra = set(obj) - _SHAPE_KEYS
    if extra:
        return f"unknown shape field {sorted(extra)[0]}"
    if not isinstance(obj.get("path"), str) or not isinstance(obj.get("uri"), str) or not obj["uri"]:
        return "a shape needs a path and a uri"
    try:
        path = re.compile(obj["path"])
    except (re.error, OverflowError, RecursionError):
        return "a shape path is not a valid pattern"
    if not isinstance(obj.get("strict", False), bool):
        return "a shape strict is not true or false"
    query = []
    raw_query = obj.get("query", {})
    if not isinstance(raw_query, dict):
        return "a shape query is not an object"
    for name, spec in raw_query.items():
        if not _NAME.fullmatch(name) or not isinstance(spec, dict) or set(spec) - _QUERY_KEYS:
            return f"query parameter {name} is malformed"
        if not isinstance(spec.get("pattern"), str) or not isinstance(spec.get("required", False), bool):
            return f"query parameter {name} is malformed"
        try:
            query.append((name, re.compile(spec["pattern"]), spec.get("required", False)))
        except (re.error, OverflowError, RecursionError):
            return f"query parameter {name} is not a valid pattern"
    known = set(path.groupindex) | {q[0] for q in query} | {"url"}
    for m in _PLACEHOLDER.finditer(obj["uri"]):
        if m.group(1) not in known:
            return f"uri placeholder {{{m.group(1)}}} names nothing the shape captures"
    if "{" in _PLACEHOLDER.sub("", obj["uri"]) or "}" in _PLACEHOLDER.sub("", obj["uri"]):
        return "uri has an unbalanced brace"
    return Shape(path, tuple(query), obj["uri"], obj.get("strict", False))


def parse_rule(obj):
    """A Rule, or a reason string when `obj` is not one."""
    if not isinstance(obj, dict):
        return "not an object"
    extra = set(obj) - _RULE_KEYS
    if extra:
        return f"unknown field {sorted(extra)[0]}"
    app = obj.get("app")
    if not isinstance(app, str) or not app.strip():
        return "no app name"
    if not scheme_ok(obj.get("scheme")):
        return f"scheme {obj.get('scheme')!r} is refused"
    hosts = obj.get("hosts")
    if not isinstance(hosts, list) or not hosts or not all(_host(h) for h in hosts):
        return "hosts must be a non-empty list of host names"
    shapes = obj.get("shapes")
    if not isinstance(shapes, list) or not shapes:
        return "shapes must be a non-empty list"
    parsed = []
    for s in shapes:
        shape = _parse_shape(s)
        if isinstance(shape, str):
            return shape
        parsed.append(shape)
    return Rule(app.strip(), obj["scheme"], frozenset(_host(h) for h in hosts), tuple(parsed))


def _label(obj, index):
    app = obj.get("app") if isinstance(obj, dict) else None
    return app if isinstance(app, str) and app.strip() else f"#{index + 1}"


def load_rules(cfg=None):
    """(rules in match order, [reason for each rule that did not load]).

    The person's rules (config `handoff.rules`) come first, in file order; then
    each shipped rule that is neither turned off by app name (`handoff.off`)
    nor replaced by a person rule of the same app name. Names compare without
    case. A value of the wrong shape counts as no rules, never as an error.
    """
    section = (cfg or {}).get("handoff") if isinstance(cfg, dict) else None
    section = section if isinstance(section, dict) else {}
    own_raw = section.get("rules") if isinstance(section.get("rules"), list) else []
    off_raw = section.get("off") if isinstance(section.get("off"), list) else []
    rules, skipped = [], []
    for i, obj in enumerate(own_raw):
        rule = parse_rule(obj)
        if isinstance(rule, str):
            skipped.append(f"rule {_label(obj, i)}: {rule}")
        else:
            rules.append(rule)
    # A person rule that did not parse still claims its app name: the person
    # meant to replace that shipped rule, and the log says why theirs is not used.
    taken = {_label(obj, i).strip().casefold() for i, obj in enumerate(own_raw)}
    taken |= {n.strip().casefold() for n in off_raw if isinstance(n, str)}
    shipped_rules, shipped_skipped = _load_shipped()
    rules.extend(r for r in shipped_rules if r.app.casefold() not in taken)
    return rules, skipped + shipped_skipped


def _load_shipped():
    rules, skipped = [], []
    try:
        raw = shipped()
    except (OSError, ValueError) as e:
        raw = []
        skipped.append(f"shipped rules unreadable: {e}")
    if not isinstance(raw, list):
        raw = []
        skipped.append("shipped rules are not a list")
    for i, obj in enumerate(raw):
        rule = parse_rule(obj)
        if isinstance(rule, str):
            skipped.append(f"shipped rule {_label(obj, i)}: {rule}")
        else:
            rules.append(rule)
    return rules, skipped


def _query_values(query):
    """First occurrence of each parameter, raw: no decoding, so `%` stays and refuses the value."""
    out = {}
    for part in query.split("&") if query else ():
        name, _, value = part.partition("=")
        out.setdefault(name, value)
    return out


# A link a shape recognises but whose values it will not pass on: the whole rule
# refuses it, so a crafted value never falls through to a shape that would drop it.
_REFUSED = object()


def _render(shape, url, parts):
    """The URI, None when the shape does not recognise the link, or _REFUSED."""
    path = parts.path or "/"
    m = shape.path.fullmatch(path)
    if m is None and len(path) > 1 and path.endswith("/"):
        m = shape.path.fullmatch(path[:-1])
    if m is None:
        return None
    values = {k: v for k, v in m.groupdict().items() if v is not None}
    params = _query_values(parts.query)
    if shape.strict and set(params) - {q[0] for q in shape.query}:
        return _REFUSED
    for name, pattern, required in shape.query:
        if name not in params:
            if required:
                return None
            values[name] = ""
            continue
        if not pattern.fullmatch(params[name]):
            return _REFUSED
        values[name] = params[name]
    for value in values.values():
        if value and not _SAFE_VALUE.fullmatch(value):
            return _REFUSED
    if "{url}" in shape.uri:
        if _URL_FORBIDDEN.search(url):
            return _REFUSED
        values["url"] = url
    return _PLACEHOLDER.sub(lambda p: values.get(p.group(1), ""), shape.uri)


def matches(url, rules):
    """Each (rule, uri) that recognises `url`, in rule order, one per rule."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return
    scheme = parts.scheme.lower()
    if scheme not in _DEFAULT_PORTS or "@" in parts.netloc:
        return
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        return
    host = _host(parts.hostname)
    for rule in rules:
        if host not in rule.hosts:
            continue
        for shape in rule.shapes:
            uri = _render(shape, url, parts)
            if uri is _REFUSED:
                break
            if uri is not None:
                yield rule, uri
                break
