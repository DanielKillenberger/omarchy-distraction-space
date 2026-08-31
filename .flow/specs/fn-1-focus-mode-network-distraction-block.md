# Focus-mode network distraction block

## Conversation Evidence

> user (turn 1): "ok so i want the first spec to actually block every distraction on a network level + additional ones that aren't permanently open like youtube. (user should be able to maintain a list easily) plugin should ship with defaults. This ofc while focus mode is on."
> user (turn 2): "we need to ship defaults in this spec"
> user (turn 3): "you can probably find a defaults list for this somewhere?"
> user (turn 4): "mate if you go on bluesky you should have to add it yourself on your list xD fuck that take that off. same for pinterest,tumblr"

## Goal & Context
<!-- scope: business -->
<!-- Source-tag breakdown: 70% [user] / 20% [paraphrase] / 10% [inferred] -->

The person using this plugin already has a named distraction workspace and a focus-mode lock. Focus mode still leaves the network open, so a browser tab or a background client can keep serving chat and video. This spec adds a network-level block for those destinations while focus mode is on. The user maintains one product-level list. The plugin ships the default product names in R7. Plan expands each name to the hostnames needed to block it.

## Architecture & Data Models
<!-- scope: technical -->
<!-- Source-tag breakdown: 80% [paraphrase] / 20% [inferred] -->

One active destination list drives the block. The plugin ships a default list whose membership is part of this spec. The user edits that list in place without rebuilding the plugin. Focus mode on applies the block for every entry. Focus mode off lifts the block this spec applied. The enforcement mechanism is not part of this spec.

## Acceptance Criteria
<!-- scope: both -->

- **R1:** While focus mode is on, the plugin blocks network access to every destination in the active list. Errors: if apply fails, the plugin tells the user and leaves the previous network state unchanged. [paraphrase]
- **R2:** Shipped defaults include YouTube. Errors: a missing defaults set omits YouTube and tells the user. [user]
- **R3:** The active list includes the permanently-open distraction destinations and extra destinations that are not permanently-open apps. Errors: no error surface beyond R1. [paraphrase]
- **R4:** The user can add, remove, and change list entries without rebuilding or reinstalling the plugin. Errors: a rejected entry does not join the active list; other entries still apply. [paraphrase]
- **R5:** The plugin ships a default list that is used until the user changes it. Errors: a missing defaults set tells the user and starts with an empty extra-destination set. [user]
- **R6:** Turning focus mode off removes the network blocks this spec applied. Errors: if the lift fails, the plugin tells the user and blocks may remain until a later successful lift. [inferred]
- **R7:** Shipped defaults are Telegram, Discord, WhatsApp, Signal, Google Messages, Facebook, Instagram, Threads, X, Reddit, TikTok, Snapchat, YouTube, Twitch, and Netflix. Errors: no error surface beyond R2 and R5. [paraphrase]

## Decision Context
<!-- scope: both -->

Hiding the distraction workspace does not stop traffic. The user asked for a network-level block while focus mode is on, plus a maintainable list that ships with defaults. [paraphrase]

Default membership is a product-name list, not a 3800-hostname dump. Sinfonietta social-hosts (updated 2026-05-15, the StevenBlack social source) names Facebook, Instagram, WhatsApp, Threads, Twitter, LinkedIn, MySpace, Pinterest, Tumblr, Reddit, TikTok, Clubhouse, Snapchat, Twitch, and Bluesky. Freedom's most-blocked set adds YouTube and Netflix. The plugin's permanently-open set adds Telegram, Discord, Signal, and Google Messages. YouTube is absent from Sinfonietta social. [paraphrase]

Left out of defaults: Bluesky, Pinterest, and Tumblr (user-add only). Also LinkedIn (work), CNN / Yahoo / Buzzfeed (news portals on Freedom's top 10), MySpace, Clubhouse, dating sites, and DateMeme. The user can add any of those. [user]

The block mechanism stays unset here so plan can pick it against Omarchy and Hyprland constraints. [inferred]

## Parked unknowns

- How the network block is enforced. Plan picks the mechanism.
- Whether connections that are already open drop as soon as focus turns on.
- Whether user edits overlay the shipped defaults or replace a first-run copy.

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | fn-N.M (TBD — populate via /flow-next:plan) |
| R2 | fn-N.M (TBD — populate via /flow-next:plan) |
| R3 | fn-N.M (TBD — populate via /flow-next:plan) |
| R4 | fn-N.M (TBD — populate via /flow-next:plan) |
| R5 | fn-N.M (TBD — populate via /flow-next:plan) |
| R6 | fn-N.M (TBD — populate via /flow-next:plan) |
| R7 | fn-N.M (TBD — populate via /flow-next:plan) |
