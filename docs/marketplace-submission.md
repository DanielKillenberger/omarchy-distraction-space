# Marketplace submission

The existing submission is [omacom/omarchy-plugin-marketplace#4518](https://github.com/omacom/omarchy-plugin-marketplace/issues/4518). Update that issue after merging v3; keep its metadata, checklist and review history. Do not open a replacement issue. The plugin id remains `io.github.danielkillenberger.distraction-space`, and `manifest.json` declares `3.0.0`.

The marketplace's [submission format](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SUBMISSION.md) and [security policy](https://github.com/omacom/omarchy-plugin-marketplace/blob/main/SECURITY.md) were checked again for this update. Editing the submission starts validation again. Its evidence and any maintainer acceptance must bind to the new exact commit; earlier v2 review is not approval of v3.

## Maintainer notes for v3

Version 3 makes `app-distraction.slice` under the user's systemd manager the network boundary. Listed programs launch inside it; listed web products use a separate Chromium-family browser profile. Listed windows stay on the distraction workspace, but the firewall no longer switches off when the person enters that workspace. The fixed nft policy accepts sockets in the installing user's distraction slice before applying the listed-address block elsewhere. Existing distraction windows can keep syncing while the work browser remains blocked.

Installation remains manual setup. `omarchy plugin add` installs the bar plugin. The owner copies the three `hypr/` snippets into their Hyprland configuration and runs `distractions setup`; the plugin does not edit `~/.config/hypr` itself.

### Privileged setup and firewall helper

`ds/setup.py` retains the root-owned staging transaction introduced in response to the earlier marketplace review. One explicit `sudo python3 -c` invocation receives the wrapper and rendered grant as bytes on stdin. It stages them in root-owned destination directories, validates the grant with `visudo`, revalidates staged ownership/inode/mode/content, and atomically renames them into place. The unprivileged side reads the shipped wrapper with no-follow, regular-file and size checks. The installed files are:

- `/usr/local/libexec/omarchy-distraction-space/distractions-nft` (0755).
- `/etc/sudoers.d/omarchy-distraction-space` (0440), granting only the installing user passwordless execution of that absolute helper path.
- `/usr/local/libexec/omarchy-distraction-space/.installed.sha256` (0444), recording the installed wrapper/grant digests so matching setup reruns can avoid sudo.

The record does not let an unprivileged caller inspect arbitrary later edits to the root-only grant. Runtime permission failures remain visible; removal followed by setup is the documented repair for grant drift.

The helper accepts only `replace ds`, `check ds`, and `flush ds`. It bounds stdin at 256 KiB and permits at most 4096 unique parsed IP addresses, with no prefixes or nft syntax accepted. It derives the user slice path from the validated invoking UID rather than accepting a cgroup path from stdin. `replace` requires the slice and loads the fixed `inet omarchy_ds` table; `flush` removes that table and rejects non-whitespace stdin. `check` compares the live normalized policy with the expected policy, with bounded output and a timeout. The listener can skip an unchanged replacement only after a fresh successful check; missing or drifted policy is repaired. Workspace transitions do not invoke sudo or rewrite the table.

The table retains IPv4/IPv6 sets, output filtering and HTTP/HTTPS redirects to the local block-page routers. The cgroup exemption is placed before the rejects and redirects. Review the full helper, including its existing router source-port exemptions; this is an attention aid, not a hostile-user security boundary.

### User-level setup and data

Setup installs and starts `install/app-distraction.slice` in the user's systemd manager. Launches use `systemd-run --user`. The listener is still started through the user's Hyprland autostart snippet; there is no privileged listener service.

Setup creates launcher entries and a URL-handler desktop entry under the user's applications directory, recording its files and backing up entries it replaces. It asks whether to route links through the space. With consent, it records the previous browser and registers the router with `xdg-settings`: listed URLs go to the distraction profile, while other URLs and ordinary browser launches go to the previous browser. The saved answer controls later noninteractive runs. `setup --yes` does not prompt, including for sudo; it fails if required privilege is unavailable.

Browser profile import is optional and explicit (`distractions profile import`). It refuses while either browser runs and requires `--replace` to replace an existing destination. Ordinary launch does not import the person's existing profile.

Notification holding still uses a clone of the installed first-party notification plugin, patched in the user's plugin directory. No packaged file under `/usr/share` is edited. Ownership records control cleanup of the clone and launcher entries. State reads retain no-follow, regular-file and size limits before data enters the bar; claimed summary records are bounded too.

The plugin owns its configuration and state directories. Agent summaries remain off by default; enabling them explicitly sends held notification records to the selected agent CLI. Dependencies and the complete setup/removal commands are listed in the [README](../README.md).

`distractions setup --remove` reverses setup: firewall/helper/grant/install-record removal, user slice cleanup, owned notification-clone cleanup, launcher restoration and previous-browser restoration. The owner removes their Hyprland snippets and then removes the plugin through Omarchy. User data such as profiles is not described as automatically erased.

## Review surface and validation

The v3 submission should disclose `installer`, `privilege`, `sudoers-modification`, and now `service-management` (the user slice and `systemctl`/`systemd-run`). These are disclosures of shipped behavior, not a claim about the scanner's eventual verdict. Do not predeclare a clean baseline or maintainer acceptance.

The prior marketplace findings concerned the setup transaction, root-input bounds and untrusted state/summary reads. Their fixes remain in v3. Additional review surfaces are `ds/launch.py`, `ds/setup.py`, `ds/net.py`, `distractions-nft`, and the user slice unit. The committed `.flow/` evidence records implementation reviews, tests, local installation, real-kernel firewall checks and native UI checks; planning prose is not runtime behavior.

Before editing issue #4518, verify the merged SHA, `omarchy plugin validate .`, the test results and the retained review receipts. The notes must name the merged SHA, describe version 3.0.0, and distinguish completed local verification from marketplace validation that has not yet run. A merge is not a GitHub release or tag; do not claim either unless it actually exists.
