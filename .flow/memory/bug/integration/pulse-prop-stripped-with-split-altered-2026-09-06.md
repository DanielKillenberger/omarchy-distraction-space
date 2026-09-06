---
title: PULSE_PROP stripped with split() altered quoted values and missed a quoted ident
date: "2026-09-06"
track: bug
category: integration
module: ds/launch.py
tags: [pulse, libpulse, forward, parser, review]
problem_type: integration
symptoms: forward collapsed whitespace inside quoted PULSE_PROP values and left a quoted application.id in place
root_cause: whitespace tokenising instead of libpulse's quote-aware grammar
resolution_type: fix
related_to: [bug/integration/ask-once-setup-answer-fell-back-to-2026-09-05]
---

## Problem
Stripping the plugin's `application.id` from an inherited `PULSE_PROP` with `prop.split()` altered other properties and missed the identity in quoted form. libpulse reads the line with a state machine: whitespace between pairs and around `=`, values bare or in double quotes or single ticks with backslash escapes, and a key may follow a closing quote directly. `split()` collapsed whitespace inside quoted values and left `application.id="io.github..."` in place, which libpulse honours.

## What Didn't Work
Whitespace tokenising and comparing whole `key=value` tokens against one literal.

## Solution
`launch._pulse_pairs` parses the line as libpulse does and `_strip_identity` removes only the matching pair, keeping the rest verbatim; a line libpulse would refuse is returned untouched since it carries no identity (ds/launch.py). Table-driven cases in `tests/test_launch.py::test_strip_identity_reads_the_line_as_libpulse_does`; syntax verified live with paplay and `pactl -f json list sink-inputs` through a custom key (paplay overrides `media.name`, so probe through a key the client does not set).

## Prevention
When editing an environment line another program parses, mirror that program's grammar, not a whitespace split; probe the real parser once with quoted, escaped, and spacing variants before writing the tokenizer.
