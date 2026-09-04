# Marketplace submission

The filled-in submit-plugin issue for the Omarchy Plugin Marketplace, the command that files it, and the per-check mapping against the marketplace's Automated Security Baseline. Filing is the owner's action; this file is what gets pasted. The form and the command follow [SUBMISSION.md](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md) in `omacom/omarchy-plugin-marketplace`; the baseline is described in that repository's [SECURITY.md](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SECURITY.md#automated-security-baseline). Both were read on 2026-09-02.

## Before filing

- `manifest.json` carries the id `io.github.danielkillenberger.distraction-space` and version `2.1.0`, the README paths use that id, and the merged commit on `main` is tagged `v2.1.0`. The listing binds to a commit, not the tag, but the tag names the same commit for humans.
- `omarchy plugin validate .` passes on that commit.
- The owner has read every checklist statement below and each one is true. The ownership statement covers the code and `preview.png`.
- The marketplace search at plugins.omarchy.org shows no listing with this id.

## The issue

Title: `[Plugin]: Distraction space`

The body, written to the temp file SUBMISSION.md uses. Every heading and the checklist text are verbatim from the marketplace; only the values and the maintainer notes are ours.

```bash
cat > /tmp/omarchy-plugin-submission.md <<'EOF'
### Repository URL

https://github.com/DanielKillenberger/omarchy-distraction-space

### Category

Productivity

### Tags

hyprland, workspaces, system

### Suggest a missing tag

_No response_

### Maintainer notes

`omarchy plugin add` runs no sudo and writes nothing outside `~/.config/omarchy/plugins/io.github.danielkillenberger.distraction-space`. The bar widget works after that alone. The window rules, keys, and listener need the three Hyprland snippets under `hypr/` copied by hand into the user's own Hyprland config, and the network block and notification hold need one explicit command, `distractions setup`. The `manual-setup` label is expected.

`distractions setup` is the only place privilege enters. It asks for the sudo password interactively, once, and everything privileged happens inside that single invocation: one `sudo python3 -c` transaction that receives the wrapper and the rendered grant as bytes on its stdin. Root is handed content, never a pathname it has to resolve a second time, so nothing the installing account can write sits between validation and activation. Inside root, the grant is written to a fresh file in `/etc/sudoers.d` itself — a directory only root can write, under a dotted name sudo's `#includedir` skips while it waits — held open by descriptor, set to mode 0440, and checked with `visudo -cf`. Root then re-reads that same descriptor, confirms the path still names the same inode with one link and root's own ownership and the bytes visudo accepted, and renames it into place atomically. A rejected grant aborts before anything moves and leaves any prior grant untouched. The wrapper `distractions-nft` lands the same way — staged in its own destination directory, mode 0755, renamed into place — and it lands before the grant that names it. The unprivileged half opens the shipped wrapper once with `O_NOFOLLOW`, refuses a symlink or a non-regular file, and sends those exact bytes, so what root installs is what was checked. The drop-in is `install/sudoers.omarchy-distraction-space` with `__INSTALL_USER__` replaced by the installing account: one user, NOPASSWD as root, on that one absolute path, and nothing else. After both files are in place, root writes one more file beside the wrapper, `.installed.sha256` at mode 0444, holding the digests of the wrapper and the grant it just installed. That record is what lets the unprivileged half of a later `distractions setup` see that nothing has changed and skip the transaction entirely, so a matching re-run asks for no password; the grant itself is 0440 in a directory the account cannot traverse, and is never read from the unprivileged side. Setup refuses to run when any ancestor of either destination is writable by the user, refuses principal names that are empty, `ALL`, a `%group`, or contain sudoers metacharacters, and never reads or lists `/etc/sudoers.d` from the unprivileged side.

The wrapper is a short Python script with no options. It accepts exactly two arguments, `replace ds` or `flush ds`, and refuses any other argv. `replace` reads addresses on stdin, one per line: each token must parse with Python's `ipaddress.ip_address` and is refused when it contains `/` or `\`, so no prefix, path, or nft syntax reaches the ruleset, and duplicates are dropped. `flush` refuses any non-whitespace stdin. Both forms bound the read itself at 256 KiB and refuse more than 4096 addresses while parsing, so nothing root allocates, renders, or commits grows with whatever the granted account sends. The validated addresses are the only variable content in a fixed nft script that destroys and recreates the table `inet omarchy_ds`: two address sets, an output filter chain that rejects traffic to set members, and an output nat chain that redirects their ports 80 and 443 to the plugin's local routers on 28080 and 28443. The wrapper refuses to commit a script that does not name that table, then feeds it to `nft -f -`. The listener calls it with `sudo -n` every 30 seconds while the user is off the space, and with `flush ds` when the user enters it.

The notification hold needs a per-sender silenced list the first-party notification service does not have yet. Setup runs Omarchy's own `omarchy-plugin-clone omarchy.notifications`, which copies `/usr/share/omarchy/shell/plugins/notifications` to `~/.config/omarchy/plugins/<user>.notifications` under the user's own config, applies `shell/notifications-silenced-senders.patch` inside that clone after a dry run, and records the SHA-256 of every copied file plus the patch in the plugin's state directory. Nothing under `/usr/share` is written and no git is involved. `setup --remove` deletes the clone only when the plugin created it, and once Omarchy ships the method itself setup removes the clone on its own.

Runtime dependencies, all present on an Omarchy 4 install: `python3` (3.11), `nft`, `sudo`, `visudo`, `hyprctl`, `getent`, `busctl`, `pactl`, `patch`, and the Omarchy tools `omarchy`, `omarchy-shell`, `omarchy-plugin-clone`, `omarchy-menu-select`, `omarchy-menu-input`, `omarchy-notification-send`, and `omarchy-launch-editor`. Optional: one agent CLI (`claude`, `grok`, `codex`, `gemini`, `opencode`, or `copilot`) runs only when the user sets `summary.command` to `auto`, with the held notification records on stdin; the default keeps everything on the machine. No package manager, no systemd unit, no download, and no compilation anywhere.

User configuration: the plugin owns `~/.config/omarchy/distraction-space.json`. The first load creates it with the defaults, and `distractions config set`, `list add`, `list remove`, and its own menu update it. It never edits `~/.config/hypr` or any other file the user owns.

Removal: `distractions setup --remove` flushes the nft sets through the wrapper, removes the wrapper, the sudoers drop-in, and root's install record with `sudo rm -f`, and removes the clone it created; then `omarchy plugin remove io.github.danielkillenberger.distraction-space`. The Hyprland snippets are removed by hand, the same way they went in.

Expected baseline result: `review-required` with the capabilities `installer`, `privilege`, and `sudoers-modification`, and no findings. `docs/marketplace-submission.md` in the repository maps every documented pattern and capability to the file that carries it.

### Submission checklist

- [x] The repository is public and contains installation and removal instructions.
- [x] I have documented the plugin license and any external dependencies.
- [x] I confirm that I own or have permission to submit this plugin and its preview assets.
- [x] The plugin does not overwrite user configuration without explicit consent.
- [x] I understand that approval is for listing and is not a security review.
EOF
```

Then, with an authenticated GitHub CLI (`gh auth login` first if needed):

```bash
gh issue create \
  --repo omacom/omarchy-plugin-marketplace \
  --title "[Plugin]: Distraction space" \
  --body-file /tmp/omarchy-plugin-submission.md
```

The marketplace applies the `submission` label when the title starts with `[Plugin]:`, all six headings stand in this order, the category matches exactly, and all five boxes are checked. If no validation comment appears, edit the issue; editing reruns detection.

## Automated Security Baseline mapping

The baseline reads the exact validated commit without running anything and reports each pattern below as a finding (blocks or needs review) or a capability (needs review, not a finding). One line per documented item, with the file that triggers it or the evidence that nothing does. Line numbers are as of 2026-09-02.

Findings:

- `curl-pipe-shell`: not triggered. No `curl` or `wget` in any runtime file. The only `curl` strings in the tree are plain `curl https://...` live-check commands in the `.flow/` planning and evidence records (Markdown and JSON, outside the scan scope), never piped to a shell or written to an executed file. Installation is `omarchy plugin add` alone (README.md, Install).
- `cargo-git-unpinned`: not triggered. No Rust, no `cargo` anywhere.
- `remote-git-execution-unpinned`: not triggered. No `git` command in the tree. The one "clone" is `omarchy-plugin-clone omarchy.notifications` (ds/setup.py:280), Omarchy's own tool copying a plugin already on disk under `/usr/share/omarchy/shell/plugins/notifications`; nothing is fetched. If the word trips a rule, that line is the answer.
- `sudoers-dangerous-passwordless-command`: not triggered. install/sudoers.omarchy-distraction-space is one line granting one user NOPASSWD on one absolute path, `/usr/local/libexec/omarchy-distraction-space/distractions-nft`. No `ALL` command, no shell or interpreter, no wildcard, no `kill`, `systemctl`, or file-management tool. The policy text says this shape is the reviewable `sudoers-modification` capability, not the finding.
- `privileged-process-control-from-shared-temp`: not triggered. No PID file under `/tmp`. The listener PID lives in the plugin's own state file under `~/.local/state/omarchy/distraction-space/` and is only probed unprivileged with `os.kill(pid, 0)` (ds/state.py:140); nothing passes a PID to `sudo`. The two `/tmp` references are the control-socket directory fallback when `XDG_RUNTIME_DIR` is unset (ds/state.py:22) and Hyprland's own socket2 path (ds/listener.py:521), both sockets, not PIDs.

Capabilities:

- `installer`: expected. `ds/setup.py` is a setup-named path and runs one `sudo python3 -c` transaction that writes the wrapper and the sudoers drop-in from bytes on its stdin (`ROOT_TRANSACTION`, and `install()` which hands it those bytes); README.md "Install" documents it. This is the intended one-time `distractions setup`.
- `package-manager`: not triggered. No `pacman`, `yay`, `paru`, `apt`, `pip install`, `npm install`, or `makepkg`.
- `privilege`: expected. Non-negated `sudo` in ds/setup.py (lines 68, 411, 420), ds/net.py (lines 247, 256), distractions-nft (docstring, line 6), docs/internals.md:27, and README.md (lines 31 and 86). No `pkexec` in runtime files. Every `sudo` call targets the wrapper path, `install`, or `rm -f` on the two installed files.
- `remote-build`: not triggered. Nothing is built; the plugin is Python and QML run in place. The clone step copies first-party files that are already installed.
- `bundled-executable-binary`: not triggered. The two executables, `distractions` and `distractions-nft`, are Python scripts with a shebang; `preview.png` is an image asset excluded by extension; no ELF, PE, or Mach-O file is tracked.
- `service-management`: not triggered. No `.service` unit, no `systemctl`, no `systemd-run`. The listener is started by the user's own Hyprland autostart snippet (hypr/autostart.lua), copied by hand.
- `sudoers-modification`: expected. install/sudoers.omarchy-distraction-space is the policy file; ds/setup.py stages, validates with `visudo -cf`, revalidates, and renames it into `/etc/sudoers.d/omarchy-distraction-space` inside one root-owned transaction (`ROOT_TRANSACTION`, and `install()` which hands it the bytes), and removes it on `--remove` (`remove()`); README.md lines 31 and 86 document the write. The helper the policy names is `distractions-nft`, a root-owned script with a fixed two-word command surface and stdin restricted to parsed IP addresses, which is the shape SECURITY.md sets aside for manual review rather than rejection.

Scan scope note: the tracked `.flow/` directory holds planning specs, task records, and review receipts as Markdown and JSON. Ordinary records in those formats are outside the scanner's recognized source set and are excluded. The exception is the rule that a file whose name contains `setup` stays a candidate whatever its extension: the six `.flow/tasks/fn-7-one-time-setup-privilege-and-helper.*` files are scanned as text. They are prose about this plugin's `setup` command and mention `sudo`, `visudo`, and `NOPASSWD`, so they can only re-raise `privilege`, `sudoers-modification`, and `installer`, the three capabilities the runtime files already produce; they contain no download, git, or shell-pipe pattern and so add no finding.

Expected outcome: `review-required`, capabilities `installer`, `privilege`, `sudoers-modification`, no findings, labels `security-review-required` and `manual-setup`. Two nft and hosts blockers with a sudoers or polkit grant (Self Control, issue #3293; Deeplok, issue #3756) were approved under that disposition on 2026-09-02, so a maintainer accepts the exact capability set through `approved-and-verified`.

## Pinning discipline

- Validation, the baseline scan, and approval all bind to the exact 40-character SHA of `main` HEAD at the moment the issue is filed. A changed branch head invalidates the recorded run.
- `main` stays frozen from filing until the issue carries `approved-and-verified`. No merge, no tag move, no README touch-up in between; GNO Recall (issue #3590) had its review refused after a three-line merge moved HEAD.
- If a push is unavoidable (a validation failure that needs a fix), push it, then edit the issue body (a no-op edit is enough) so detection reruns against the new HEAD, and wait for the fresh validation and baseline comments before asking for review.
- Later releases never reuse this form. Tag the release, then open the [Plugin verification](https://github.com/omacom/omarchy-plugin-marketplace/issues/new?template=verify-plugin.yml) form, choose "Verify and publish a newer upstream commit", and enter the plugin id `io.github.danielkillenberger.distraction-space`, the repository root URL, and the full 40-character SHA of the new HEAD. Until a maintainer approves it, the marketplace shows the old snapshot as `Update unverified`.
- `omarchy plugin add` installs upstream HEAD, not the approved SHA, so a user who installs between a push and its verification runs code the marketplace has not scanned. Keep pushes to `main` release-shaped for that reason.
