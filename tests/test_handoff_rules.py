#!/usr/bin/env python3
"""The shipped handoff rules in handoff.json: every recognised shape maps, and a link
the app's scheme has no page for is left to the browser.

Each class names where its scheme mapping comes from.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ROOT

sys.path.insert(0, str(ROOT))
from ds import handoff


def _uris(url):
    rules, skipped = handoff.load_rules()
    assert skipped == [], skipped
    return [uri for _rule, uri in handoff.matches(url, rules)]


class _Table(unittest.TestCase):
    MAPS: tuple = ()
    LEAVES: tuple = ()

    def test_recognised_shapes_map(self):
        for url, uri in self.MAPS:
            with self.subTest(url=url):
                self.assertEqual(_uris(url), [uri])

    def test_unmappable_links_stay_with_the_browser(self):
        for url in self.LEAVES:
            with self.subTest(url=url):
                self.assertEqual(_uris(url), [])


class ShippedSetTests(unittest.TestCase):
    def test_the_shipped_apps(self):
        rules, skipped = handoff.load_rules()
        self.assertEqual(skipped, [])
        # Discord is left out: its scheme routes are documented only unofficially.
        self.assertEqual([r.app for r in rules], ["Spotify", "Zoom", "Slack", "Steam", "Telegram"])


class ZoomTests(_Table):
    # zoommtg://zoom.us/join?action=join&confno=...&pwd=..., as posted on Zoom's developer
    # forum (devforum.zoom.us/t/96064); the Linux client registers x-scheme-handler/zoommtg.
    MAPS = (
        ("https://zoom.us/j/1234567890?pwd=AbC.12-x", "zoommtg://zoom.us/join?action=join&confno=1234567890&pwd=AbC.12-x"),
        ("https://us02web.zoom.us/j/98765432101?pwd=xyz&from=addon", "zoommtg://zoom.us/join?action=join&confno=98765432101&pwd=xyz"),
        ("https://zoom.us/w/123456789", "zoommtg://zoom.us/join?action=join&confno=123456789"),
    )
    LEAVES = (
        "https://zoom.us/", "https://zoom.us/j/abc", "https://zoom.us/j/12345", "https://zoom.us/signin",
        "https://acme.zoom.us/j/123456789", "https://zoom.us/rec/share/abc",
        # A password the rule will not pass on refuses the link; it never joins without it.
        "https://zoom.us/j/123456789?pwd=a%20b", "https://zoom.us/j/123456789?pwd=ab%63",
        "https://zoom.us/j/123456789?pwd=",
    )


class SlackTests(_Table):
    # slack://channel?team={TEAM_ID}&id={CHANNEL_ID} and slack://open?team={TEAM_ID},
    # docs.slack.dev/interactivity/deep-linking; the web client names both IDs in its path.
    MAPS = (
        ("https://app.slack.com/client/T12345/C123ABC456", "slack://channel?team=T12345&id=C123ABC456"),
        ("https://app.slack.com/client/T12345/D0ABCDEF/", "slack://channel?team=T12345&id=D0ABCDEF"),
        ("https://app.slack.com/client/T12345", "slack://open?team=T12345"),
    )
    LEAVES = (
        "https://app.slack.com/", "https://app.slack.com/client/t12345/C1", "https://app.slack.com/client/T1/C1/thread/x",
        "https://acme.slack.com/archives/C123ABC456", "https://slack.com/",
    )


class SteamTests(_Table):
    # steam://store/<id> "Opens up the store for an app",
    # developer.valvesoftware.com/wiki/Steam_browser_protocol. steam://openurl is not used:
    # it opens the system's default browser, which is this plugin.
    MAPS = (
        ("https://store.steampowered.com/app/620/Portal_2/", "steam://store/620"),
        ("https://store.steampowered.com/app/620", "steam://store/620"),
        ("https://store.steampowered.com/app/620/?snr=1_7", "steam://store/620"),
    )
    LEAVES = (
        "https://store.steampowered.com/", "https://store.steampowered.com/app/abc",
        "https://store.steampowered.com/app/620/Portal 2/", "https://store.steampowered.com/sub/123",
        "https://steamcommunity.com/app/620",
    )


class TelegramTests(_Table):
    # tg://resolve?domain=<username>[&post=<id>], core.telegram.org/api/links
    # ("Public username links", "Message links").
    MAPS = (
        ("https://t.me/durov", "tg://resolve?domain=durov"),
        ("https://t.me/telegram/123", "tg://resolve?domain=telegram&post=123"),
        ("https://telegram.me/some_name/", "tg://resolve?domain=some_name"),
    )
    LEAVES = (
        "https://t.me/", "https://t.me/joinchat/AbCdEf", "https://t.me/joinchat", "https://t.me/+AbCdEf",
        "https://t.me/addstickers/pack", "https://t.me/share/url?url=x", "https://t.me/s/channel",
        "https://t.me/c/123/45", "https://t.me/abc", "https://t.me/1abcde",
    )


if __name__ == "__main__":
    unittest.main()
