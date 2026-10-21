#!/usr/bin/env python3
"""ds/handoff.py: rule parsing and link matching, with no launch involved."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT

sys.path.insert(0, str(ROOT))
from ds import handoff


def _uris(url, rules=None):
    if rules is None:
        rules, skipped = handoff.load_rules()
        assert skipped == [], skipped
    return [uri for _rule, uri in handoff.matches(url, rules)]


def _rule(**over):
    obj = {"app": "Demo", "scheme": "demo", "hosts": ["demo.example"],
           "shapes": [{"path": "/item/(?P<id>[a-z0-9]+)", "uri": "demo:item:{id}"}]}
    obj.update(over)
    return obj


class SpotifyTests(unittest.TestCase):
    def test_every_type_maps_with_and_without_locale_and_si(self):
        for kind in ("track", "album", "playlist", "artist", "episode", "show"):
            for prefix in ("", "/intl-de", "/intl-pt-br"):
                for query in ("", "?si=abc123XYZ", "?si=a&utm_source=copy-link"):
                    url = f"https://open.spotify.com{prefix}/{kind}/4uLU6hMCjMI75M1A2tKUQC{query}"
                    with self.subTest(url=url):
                        self.assertEqual(_uris(url), [f"spotify:{kind}:4uLU6hMCjMI75M1A2tKUQC"])

    def test_trailing_slash_fragment_http_and_host_case_still_map(self):
        for url in ("https://open.spotify.com/track/abc/", "https://open.spotify.com/track/abc#x",
                    "http://open.spotify.com/track/abc", "https://Open.Spotify.COM./track/abc",
                    "https://open.spotify.com:443/track/abc"):
            with self.subTest(url=url):
                self.assertEqual(_uris(url), ["spotify:track:abc"])

    def test_unmappable_links_do_not_match(self):
        for url in ("https://open.spotify.com/", "https://open.spotify.com/user/someone",
                    "https://open.spotify.com/track/", "https://open.spotify.com/Track/abc",
                    "https://open.spotify.com/intl-deu/track/abc", "https://spotify.com/track/abc",
                    "https://www.open.spotify.com/track/abc", "https://example.com/track/abc"):
            with self.subTest(url=url):
                self.assertEqual(_uris(url), [])

    def test_crafted_links_do_not_match(self):
        # R5: encoded or out-of-pattern captures, a non-default port, and userinfo.
        for url in ("https://open.spotify.com/track/ab%63", "https://open.spotify.com/track/ab-c",
                    "https://open.spotify.com/track/ab:c", "https://open.spotify.com:8443/track/abc",
                    "https://user@open.spotify.com/track/abc", "https://open.spotify.com:bad/track/abc"):
            with self.subTest(url=url):
                self.assertEqual(_uris(url), [])


class EngineTests(unittest.TestCase):
    def test_shipped_rules_all_load(self):
        rules, skipped = handoff.load_rules()
        self.assertEqual(skipped, [])
        self.assertIn("Spotify", [r.app for r in rules])

    def test_refused_and_malformed_schemes(self):
        for scheme in sorted(handoff.REFUSED_SCHEMES) + ["", "Spotify", "1x", "a b", None]:
            with self.subTest(scheme=scheme):
                self.assertIsInstance(handoff.parse_rule(_rule(scheme=scheme)), str)
        self.assertIsInstance(handoff.parse_rule(_rule()), handoff.Rule)

    def test_malformed_rules_name_a_reason(self):
        bad = (
            "not a rule", _rule(extra=1), _rule(app=""), _rule(hosts=[]), _rule(hosts="demo.example"),
            _rule(shapes=[]), _rule(shapes=[{"path": "(", "uri": "demo:x"}]),
            _rule(shapes=[{"path": "/x", "uri": "demo:{nope}"}]),
            _rule(shapes=[{"path": "/x", "uri": "demo:{"}]),
            _rule(shapes=[{"path": "/x", "uri": "demo:x", "extra": 1}]),
            _rule(shapes=[{"path": "/x", "uri": "demo:x", "query": {"p": {"pattern": "("}}}]),
            _rule(shapes=[{"path": "/x", "uri": "demo:x", "query": {"p": {"pattern": ".*", "x": 1}}}]),
        )
        for obj in bad:
            with self.subTest(obj=obj):
                reason = handoff.parse_rule(obj)
                self.assertIsInstance(reason, str)
                self.assertTrue(reason)

    def test_query_parameters_required_optional_and_raw(self):
        rule = handoff.parse_rule(_rule(shapes=[
            {"path": "/j/(?P<id>[0-9]+)", "query": {"pwd": {"pattern": "[A-Za-z0-9.]+", "required": True}},
             "uri": "demo:join?id={id}&pwd={pwd}"},
            {"path": "/j/(?P<id>[0-9]+)", "uri": "demo:join?id={id}"},
        ]))
        self.assertEqual(_uris("https://demo.example/j/12?pwd=ab.c&pwd=zz", [rule]), ["demo:join?id=12&pwd=ab.c"])
        self.assertEqual(_uris("https://demo.example/j/12", [rule]), ["demo:join?id=12"])
        # An encoded or out-of-pattern parameter refuses the whole rule: the later shape
        # would drop it, so the link goes to the browser instead.
        self.assertEqual(_uris("https://demo.example/j/12?pwd=a%26b", [rule]), [])
        self.assertEqual(_uris("https://demo.example/j/12?pwd=", [rule]), [])

    def test_a_strict_shape_refuses_parameters_it_does_not_declare(self):
        loose = handoff.parse_rule(_rule())
        strict = handoff.parse_rule(_rule(shapes=[
            {"path": "/item/(?P<id>[a-z0-9]+)", "query": {"ref": {"pattern": "[a-z]*"}}, "strict": True, "uri": "demo:item:{id}"},
        ]))
        self.assertEqual(_uris("https://demo.example/item/a1?si=x", [loose]), ["demo:item:a1"])
        self.assertEqual(_uris("https://demo.example/item/a1?ref=x", [strict]), ["demo:item:a1"])
        self.assertEqual(_uris("https://demo.example/item/a1", [strict]), ["demo:item:a1"])
        self.assertEqual(_uris("https://demo.example/item/a1?si=x", [strict]), [])
        self.assertEqual(_uris("https://demo.example/item/a1?ref=x&si=y", [strict]), [])
        for value in ("yes", 1, None):
            with self.subTest(strict=value):
                shape = {"path": "/x", "uri": "demo:x", "strict": value}
                self.assertIsInstance(handoff.parse_rule(_rule(shapes=[shape])), str)

    def test_a_pattern_too_large_to_compile_is_a_reason_not_a_crash(self):
        huge = "a{99999999999999999999999999}"
        for shape in ({"path": huge, "uri": "demo:x"},
                      {"path": "/x", "uri": "demo:{p}", "query": {"p": {"pattern": huge}}}):
            with self.subTest(shape=shape):
                self.assertIsInstance(handoff.parse_rule(_rule(shapes=[shape])), str)
        rules, skipped = handoff.load_rules({"handoff": {"rules": [_rule(app="Huge", shapes=[{"path": huge, "uri": "demo:x"}])], "off": []}})
        self.assertEqual(len(skipped), 1)
        self.assertEqual(_uris("https://open.spotify.com/track/abc", rules), ["spotify:track:abc"])

    def test_whole_url_placeholder_refuses_forbidden_characters(self):
        rule = handoff.parse_rule(_rule(shapes=[{"path": "/.*", "uri": "demo://open/{url}"}]))
        self.assertEqual(_uris("https://demo.example/a/b?c=d", [rule]), ["demo://open/https://demo.example/a/b?c=d"])
        for url in ('https://demo.example/a"b', "https://demo.example/a<b", "https://demo.example/a\\b",
                    "https://demo.example/a`b", "https://demo.example/a b"):
            with self.subTest(url=url):
                self.assertEqual(_uris(url, [rule]), [])

    def test_first_matching_shape_per_rule_and_rule_order(self):
        a = handoff.parse_rule(_rule(app="A"))
        b = handoff.parse_rule(_rule(app="B", scheme="other"))
        self.assertEqual([r.app for r, _ in handoff.matches("https://demo.example/item/x1", [a, b])], ["A", "B"])


class PersonRuleTests(unittest.TestCase):
    """R4: the person's rules in config `handoff`, merged with the shipped ones."""

    TRACK = "https://open.spotify.com/track/abc"

    def _load(self, rules=(), off=()):
        return handoff.load_rules({"handoff": {"rules": list(rules), "off": list(off)}})

    def test_a_person_rule_maps_a_link_no_shipped_rule_knows(self):
        rules, skipped = self._load([_rule()])
        self.assertEqual(skipped, [])
        self.assertEqual(_uris("https://demo.example/item/x1", rules), ["demo:item:x1"])
        self.assertEqual(_uris(self.TRACK, rules), ["spotify:track:abc"])

    def test_same_app_name_replaces_the_shipped_rule_and_comes_first(self):
        own = _rule(app=" spotify ", scheme="spotify-alt", hosts=["open.spotify.com"],
                    shapes=[{"path": "/track/(?P<id>[a-z]+)", "uri": "spotify-alt:{id}"}])
        rules, _ = self._load([_rule(), own])
        self.assertEqual([r.app for r in rules][:2], ["Demo", "spotify"])
        self.assertNotIn("Spotify", [r.app for r in rules])
        self.assertEqual(_uris(self.TRACK, rules), ["spotify-alt:abc"])

    def test_off_turns_a_shipped_rule_off_by_name(self):
        rules, _ = self._load(off=["SPOTIFY"])
        self.assertEqual(_uris(self.TRACK, rules), [])
        rules, _ = self._load(off=["Someone else"])
        self.assertEqual(_uris(self.TRACK, rules), ["spotify:track:abc"])

    def test_a_person_rule_is_checked_before_a_shipped_rule_for_the_same_link(self):
        own = _rule(app="Mine", scheme="mine", hosts=["open.spotify.com"],
                    shapes=[{"path": "/track/(?P<id>[a-z]+)", "uri": "mine:{id}"}])
        rules, _ = self._load([own])
        self.assertEqual(_uris(self.TRACK, rules), ["mine:abc", "spotify:track:abc"])

    def test_a_bad_rule_is_skipped_with_a_reason_and_the_others_apply(self):
        bad = [_rule(app="Typo", host=["x.example"]), _rule(app="Js", scheme="javascript"),
               _rule(app="Re", shapes=[{"path": "(", "uri": "demo:x"}]), "nope"]
        rules, skipped = self._load(bad + [_rule()])
        self.assertEqual(len(skipped), 4, skipped)
        for reason, name in zip(skipped, ("Typo", "Js", "Re", "#4")):
            self.assertTrue(reason.startswith(f"rule {name}: "), reason)
        self.assertEqual(_uris("https://demo.example/item/x1", rules), ["demo:item:x1"])
        self.assertEqual(_uris(self.TRACK, rules), ["spotify:track:abc"])

    def test_a_broken_rule_named_after_a_shipped_app_still_replaces_it(self):
        rules, skipped = self._load([_rule(app="Spotify", scheme="https")])
        self.assertEqual(len(skipped), 1)
        self.assertEqual(_uris(self.TRACK, rules), [])

    def test_a_section_of_the_wrong_shape_counts_as_no_person_rules(self):
        for cfg in (None, {}, {"handoff": []}, {"handoff": {"rules": "x", "off": 3}}):
            with self.subTest(cfg=cfg):
                rules, skipped = handoff.load_rules(cfg)
                self.assertEqual(skipped, [])
                self.assertEqual(_uris(self.TRACK, rules), ["spotify:track:abc"])


if __name__ == "__main__":
    unittest.main()
