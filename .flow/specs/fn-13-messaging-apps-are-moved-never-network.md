# Messaging apps are moved, never network-blocked

## Conversation Evidence

> user: "is there still connection block of whatsapp and other messaging apps in there? i though that was removed?"

## Goal & Context

<!-- scope: business -->

Two independent things happen to a listed app: its windows move to the distraction space, and its hosts are dropped from the network off-space. Messaging apps get only the first. PR #8 (`fix/messaging-apps-not-network-blocked`, never merged) recorded that decision on the legacy tree; the fn-9 rewrite rebuilt the catalog and silently reverted it. This spec restores it in the shipped catalog.

| | Windows moved | Network blocked off-space |
|---|---|---|
| Telegram, Discord, WhatsApp, Signal, Google Messages | yes | no |
| X | yes | yes |
| Facebook, Instagram, Threads, Reddit, TikTok, Snapchat, YouTube, Twitch, Netflix | no | yes |

## Architecture & Data Models

<!-- scope: technical -->

`catalog.json`: the five messaging entries keep `class`, `pwa`, `senders`, and `audio`, and carry `"hosts": []`. `expand_entry` must not re-derive hosts from `pwa` for a catalog entry whose hosts are explicitly empty; the PWA class is still derived from `pwa` so the window still moves. README gains PR #8's table. A test pins the table: for each messaging name the expansion has classes and no hosts; X has both; the rest have hosts only.

## Edge Cases & Constraints

<!-- scope: technical -->

- A user custom entry `{"name": "Slack", "class": ..., "hosts": [...]}` keeps its hosts (unchanged).
- A user string entry naming a catalog product uses the catalog row, so "WhatsApp" on the list yields no hosts.
- `keep_reachable` is unchanged.
- The live expansion cache is rewritten on the next listener boot or reload; no manual migration.

## Quick commands

```bash
python3 -m unittest discover -s tests > /tmp/ds-suite.log 2>&1; tail -3 /tmp/ds-suite.log
```

## Acceptance Criteria

<!-- scope: both -->

- **R1:** Expanding Telegram, Discord, WhatsApp, Signal, or Google Messages yields at least one window class and an empty hosts list. Errors: none.
- **R2:** Expanding X yields a class and hosts; expanding each of the other nine catalog names yields hosts. Errors: none.
- **R3:** README documents the moved-versus-blocked table.

## Boundaries

<!-- scope: business -->

- No change to the network stack, window rules, lock, or nudges.
- PR #8 is closed as superseded after this lands; its branch is deleted.

## Decision Context

<!-- scope: both -->

Restores the user's 2026-09-01 decision from PR #8. Rejected: a per-user `keep_reachable` workaround, because the intent is a product default.
