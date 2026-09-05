---
satisfies: [R4, R6]
---
# fn-24-the-plugin-owns-launching-while-it-is.3 Setup asks about links once in plain words, persists the answer, and the docs say so

## Description
Setup makes the default-browser change an explicit, explained choice, per spec section "Setup asks once, in plain words", and the docs say the same.

### Files

- `ds/setup.py`: before the root prompt, when the config file has no explicit `open_links_in_space` and stdin is a terminal and `--yes` is absent, print the spec's paragraph with the previous browser's desktop Name substituted and ask `Route links through the distraction space? [Y/n]`; write the answer into the config file (preserving the rest of the file) so the question never repeats; a rerun prints the current choice and the key; non-interactive or `--yes` takes the config value (default true) and prints the paragraph as a notice. An answer of no leaves the handler unregistered and `links: off`.
- `ds/config.py`: a helper that reports whether the key is explicit in the file and one that writes it back without disturbing other keys (follow the existing read path; JSON or TOML as the file is).
- `distractions`: `setup --yes`.
- `README.md`: Install section, near the top, explains the handler, why, what no means, and that remove restores; Commands lists `--yes`.
- `docs/internals.md`: forwarding, the entry rewrite, the prompt, and the test count.
- `tests/test_setup.py`, `tests/test_config.py`: prompt shown once with the browser name, answer persisted, rerun silent, `--yes` and non-tty never prompt, no leaves links off.

### Reuse

`default_handler()`, `launch.desktop_files` for the Name, the fake `xdg-settings` in `tests/test_setup.py`.
## Acceptance
- [ ] TBD

## Done summary
TBD

## Evidence
- Commits:
- Tests:
- PRs:
