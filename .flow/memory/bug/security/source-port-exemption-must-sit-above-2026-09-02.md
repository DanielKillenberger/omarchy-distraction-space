---
title: Source-port exemption must sit above the ephemeral port range
date: "2026-09-02"
track: bug
category: security
module: "distractions-nft,ds/feedback.py"
tags: [nft, splice, ephemeral-ports]
problem_type: security
symptoms: Listed sites load about 1 in 30 tries with the site block on
root_cause: Exempt range 60000-60999 lay inside ip_local_port_range 32768-60999
resolution_type: fix
---

## Problem
The spec for the hostname router exempted TCP source ports 60000-60999 from the site block so the listener's splice sockets could reach the real destination. Linux's default `net.ipv4.ip_local_port_range` is 32768-60999, so the exempt range sat inside the ephemeral range: any program's ordinary outbound connection had about a 3.5 percent chance (1000 of 28232 ports) of drawing an exempt source port and bypassing the block entirely.

## What Didn't Work
Implementing the number as written. The worker flagged it; nothing in the test suite could catch it because the tests override the range to a free loopback pair.

## Solution
Moved the range to 61000-61999, above the default ceiling (325708f). `sysctl net.ipv4.ip_local_port_range` on this machine confirmed 32768-60999.

## Prevention
Any nft rule that accepts by source port must use ports above `net.ipv4.ip_local_port_range`'s ceiling, and the spec review should check that sysctl before fixing a number. A machine whose sysctl widens the ephemeral range past 61000 keeps the exposure; `net.ipv4.ip_local_reserved_ports` is the follow-up if that ever matters.
