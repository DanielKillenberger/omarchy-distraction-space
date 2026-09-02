# Banner provenance for blocked-site notices

## Conversation Evidence

> user (turn 1): "i still have "X blocked on this workspace" notifications pop up occasionally"
> user (turn 2): "i need another test i didn't pay attention to a banner appearing. what should happen?"
> user (turn 3): "i saw reddit banner"
> user (turn 4): "merge pr 20 and /capture that spec"

## Goal & Context

<!-- Source-tag breakdown: 30% [user] / 50% [paraphrase] / 20% [inferred] -->

Daniel still sees occasional "X opens in the distraction space" banners while he is off the space and has not opened X. The listener's state log carries no attribution failures for those moments, so each banner came from a redirected HTTPS connection to a listed host that the listener could not tie to a window on the distraction space, and treated as a deliberate off-space fetch. The plugin records nothing about a banner beyond showing it, so today nobody can say which process or window opened the connection. The likeliest source is an off-space browser preconnecting or prefetching links it renders, such as embedded posts or hovered links, which the router cannot tell from a visit the person meant. [paraphrase]

After this spec, every banner decision leaves one line in the state log naming the host, the process, and the window it was attributed to, so a week of normal use shows what triggers the banners. Whether connections that carry no user intent should raise a banner at all is decided on that evidence, in a follow-up, and recorded in this spec's Decision Context when it lands. [paraphrase]

## Architecture & Data Models

<!-- scope: technical -->
<!-- Source-tag breakdown: 20% [paraphrase] / 80% [inferred] -->

**Provenance line.** The banner path already recovers the client's peer port, maps it to a socket inode and an owning process, and walks that process to a Hyprland client to decide whether the origin sits on the space. Each decision, whether the banner fired or not, appends one line to the state log with a fixed field order: timestamp, the host from the SNI, the catalog entry it matched, the peer port, the attributed process id and executable basename (or `none`), the window class and workspace name of the attributed Hyprland client (or `none`), and the decision with its reason. Reasons are a closed set: `shown`, `debounced` (inside the 30 second per-entry window), `on-space` (the owner's windows all sit on the space), `entry-on-space` (the owner runs an app whose entry has windows on the space), and `unattributed` (no socket, process, or client match, which shows the banner as today). [inferred]

**Bounds.** Lines are rate-limited per host to a fixed count per minute so a burst of prefetches cannot flood the log; the count of dropped lines is appended to the next line for that host. No notification text, URL path, or request body is ever logged; the line carries the hostname only. [inferred]

**Read-back.** A `distractions banners` command prints the most recent provenance lines in reverse order, defaulting to the last 20, so the person does not need to open the log file. [inferred]

## Edge Cases & Constraints

<!-- scope: technical -->

- The attribution step can fail partway (socket found, process gone before it is read); the line records how far it got and the reason `unattributed`. [inferred]
- The log write follows the existing state-log discipline: append only, never blocks the connection handler, an unwritable log drops the line silently. [inferred]
- IPv6 clients are attributed through the same peer-port lookup as IPv4 today; the line does not distinguish families. [inferred]

## Acceptance Criteria

<!-- scope: both -->

- **R1:** Every banner decision on the HTTPS path appends one provenance line to the state log with, in order, the host, the matched entry, the peer port, the attributed process id and executable basename or `none`, the attributed window class and workspace or `none`, and one of the closed decision reasons `shown`, `debounced`, `on-space`, `entry-on-space`, `unattributed`. Errors: an unwritable log drops the line and never delays or changes the banner. [inferred]
- **R2:** A burst of connections to one host writes at most a fixed number of lines per minute for that host, and the next line for the host carries the count dropped. Errors: none beyond R1. [inferred]
- **R3:** `distractions banners` prints the most recent provenance lines, newest first, 20 by default, with a `--count` option. Errors: an absent or empty log prints nothing and exits 0. [inferred]
- **R4:** The banner's text, its 30 second per-entry debounce, and the on-space suppression rules from the blocked-site banner spec are unchanged; the existing banner tests still pass unmodified. Errors: none. [paraphrase]
- **R5:** No line ever contains a URL path, query, request body, or notification text; the tests assert the line for a request with a path and a query carries the hostname alone. Errors: none. [inferred]

## Boundaries

<!-- scope: business -->

- Whether intent-free connections (browser preconnect, prefetch, link previews) raise a banner is not decided here; this spec collects the evidence that decision needs. [paraphrase]
- The site block, the hostname router, and the pass-through are unchanged. [inferred]
- The window-open banner (`nudges.app_banner`) is out of scope; only the blocked-fetch banner gains provenance. [inferred]

## Decision Context

<!-- scope: both -->

Log first, then decide. Guessing the source and suppressing banners for, say, every browser connection would also hide the banner Daniel wants when he opens X on purpose in an off-space tab; the listener cannot tell the two apart today, and a week of provenance lines shows which processes and window classes actually trigger the banners. Rejected: suppressing banners for connections whose owning process has no window at all, before knowing whether the X banners come from such a process. [paraphrase]

## Parked unknowns

- Which connections count as intent-free, and whether they should be silent, is resolved by reading the provenance lines after about a week of normal use and then writing the suppression rule as a follow-up spec. [paraphrase]

## Requirement coverage

| R-ID | Task |
|------|------|
| R1 | TBD — populate via /flow-next:plan |
| R2 | TBD — populate via /flow-next:plan |
| R3 | TBD — populate via /flow-next:plan |
| R4 | TBD — populate via /flow-next:plan |
| R5 | TBD — populate via /flow-next:plan |
