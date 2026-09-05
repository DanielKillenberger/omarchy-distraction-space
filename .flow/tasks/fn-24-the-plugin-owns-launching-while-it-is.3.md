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
Setup now asks about links once, in the spec's words: with no explicit `open_links_in_space` in the config file it prints the explanation naming the previous browser by its desktop entry's `Name` and asks `Route links through the distraction space? [Y/n]` before the root transaction; the answer is written to the config file, a rerun prints the current choice and the key that changes it, `--yes` or a non-terminal stdin takes the config value (true by default) and prints the paragraph as a notice, and no leaves the handler unregistered with `links: off` while the entries are still written (R4). README's Install section explains the handler, why, what no means, and that remove restores; Links, Configure, and Commands cover forwarding, the entry rewrite, `--app`, and `--yes`; docs/internals.md describes forwarding, the entry rewrite and its lock, the prompt, and the lazy config key (R6).

What the spec left open and the implementation settled:
- "Explicit in the file" had to survive every other config write, and `config.update` rewrote the whole merged config on each save. `open_links_in_space` is now the one default that stays out of the file until something sets it: `update` hands the mutation the file's own keys, treats an assignment (any value, `config set ... true` included) as the answer, and writes the file without the key otherwise; in memory every load still carries it at its default, so no reader outside this task changed. `config.links_answered()` and `config.set_links()` carry that for setup.
- The spec's paragraph says `"distractions remove" restores <Browser>`; the command is `distractions setup --remove`, and the printed text names the real one.
- A persistence failure (config busy, unwritable file) stops setup with exit 1 before the root transaction; nothing has been installed at that point, so the question returns next run. `--yes` runs the root transaction with `sudo -n`, so a first install that needs a password fails with one line instead of prompting (both from the review).
- `tests/test_setup.py` silences setup's stdout in `setUp`; the three direct `setup.install()` calls in `tests/test_clone.py` (outside this task's files) still print the `links: on` rerun line during a test run.
- Tests for R4: `test_setup_asks_about_links_once_naming_the_browser_before_sudo_and_a_rerun_prints_the_choice`, `test_answering_no_leaves_the_handler_unregistered_and_links_off`, `test_yes_and_a_non_terminal_never_prompt_and_print_the_explanation_as_a_notice`, `test_an_answer_that_cannot_be_recorded_stops_setup_before_the_root_transaction`, `test_yes_never_asks_for_a_password_either` (tests/test_setup.py); `test_open_links_in_space_stays_out_of_the_file_until_something_sets_it` (tests/test_config.py). Each ran red against the pre-fix code first. Full suite: 384 tests, green, about 160 s.

baseline: green via handoff (verified at 9410f589 by fn-24-the-plugin-owns-launching-while-it-is.2)
stage: impl-review - ran [codex fan-out round 1 NEEDS_WORK (2 findings: persistence failure fell back to memory; --yes still reached the sudo prompt) .. round 2 NEEDS_WORK (--yes must reach sudo -n, stale doc line) .. round 3 SHIP at e7984f5]
## Evidence
- Commits: b0164b9c4e6c164fad3fa0c42d0f5995d5b4e7e9, 388115a16a8b42e27dfbd18f5f720f035db2d3d5, e7984f53e2dc594bff78ecf6b43e2c4cab58913c
- Tests: PATH=/usr/bin:$PATH python3 -m unittest discover -s tests, ./distractions open --help, ./distractions setup --help
- PRs: