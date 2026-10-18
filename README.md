# OmaPlugCtl

Manage Omarchy bar plugins from the plug icon in the bar.

The compact screen diagram moves the bar to any edge. The current edge is highlighted and the other edges remain faintly visible. The menu follows the bar without closing, including changes between horizontal and vertical placement. Sorting defaults to screen appearance order, with name and pending-update date also available.

Hover a plugin row for its function, local update date, author and default Omarchy status. Meaningful manifest attribution is retained. When attribution is missing or only says Omarchy, the manager follows each plugin file’s Git history through renames to its first recorded commit, and identifies that author and commit in the footer. Shallow history is labeled as the earliest available commit. Results are cached by source commit; hovering never contacts GitHub. Enable/disable, About, movement and uninstall actions remain available. Uninstall requires confirmation. Default Omarchy plugins cannot be removed, and OmaPlugCtl cannot disable or remove itself.

**Check updates** fetches each installed source repository and caches its status. Normal refreshes do not contact upstream. An update icon appears when source changes are pending. Hover it for the latest change date and up to three commit subjects.

**Click an update icon to update that plugin.** A detached worker fetches the current branch’s configured origin ref and fast-forwards the actual running checkout to that exact fetched commit. Symlinked installations update their underlying source repo. It never creates a merge commit, rebases, stashes or hard-resets local work. When upstream has rewritten history, the updater checks every installed-only commit against upstream using whitespace-preserving verbatim patch IDs. Only complete matches without local-only merge or empty commits qualify for automatic reconciliation. It first saves and verifies a `backup/omaplugctl/<timestamp>-<old-commit>` branch, then uses a non-forced checkout to adopt the new upstream history. Dirty checkouts, unmatched commits, detached HEAD and branches without origin tracking stop with an accurate error. Ignored local files are protected from overwrite as well. The menu displays progress and confirms the result only after Git readback. Source text and errors render as plain text. Per-repository locking prevents concurrent mutations. Git hooks are disabled for the fast-forward operation.

The worker survives a shell rescan and an update to OmaPlugCtl itself. After changing files it requests a plugin rescan. The menu’s lightweight status polling refreshes the installed version and clears the update indicator when the checkout is current. Failed updates display their reason; no terminal, agent, review task or confirmation prompt is opened by an update click. Built-in plugins belonging to the shared Omarchy repository remain managed by Omarchy’s system updater.

Agentic review is retired from `master`. The complete implementation, including the unfinished background GitHub-publication prototype, is preserved on [archive/agentic-reviews](https://github.com/zigmoo/omaplugctl/tree/archive/agentic-reviews) at commit `031d255`, locally and on both remotes. The active version contains no reviewer configuration, dispatch, report polling or publication code. Existing DIL review evidence and machine settings are retained outside this repository for future use. **Config** remains available for the saved sort order and **Scan with ClamAV before updating**. Agentic reviewer controls remain retired.

**Malware checking defaults to enabled.** ClamAV runs locally before any update changes the checkout. Signature databases refresh automatically, at most once per day, using FreshClam’s signature verification. The scanner reads the exact fetched Git blobs into an inert archive; plugin code is never executed or uploaded. All tracked blobs are included, even files marked `export-ignore`. Symlinks are scanned as their target text without following them. Submodules, Git LFS payloads, oversized snapshots, encrypted archives and scan-limit failures stop the update because their contents cannot be fully checked. Any detection, signature-refresh failure or scanner error stops the update. A clean scan means **no threats detected**, not proof of safety.

Install the `clamav` package through your distribution to provide `clamscan` and `freshclam`. A user-local runtime is also supported at `$XDG_DATA_HOME/omaplugctl/scanner/usr/bin` with its matching `usr/lib` and `etc/clamav/certs` (default `~/.local/share/omaplugctl/scanner`). On this machine, that runtime was extracted from signature-verified Arch packages without changing system files. Scanner databases and logs are in the manager’s XDG state directory. The Config toggle is saved through Omarchy and rendered only after storage readback. Disabling it explicitly skips scans for subsequent updates.

Source: [zigmoo/omaplugctl](https://github.com/zigmoo/omaplugctl). The trunk is `master`. Local development checkout: `~/dil/plugins/omaplugctl`. The active installation is a symlink at `~/.config/omarchy/plugins/moo.omaplugctl`. GitHub is remote `origin`; the secondary development remote is `workshop`.

Useful commands:

```bash
omarchy-shell moo.omaplugctl show
omarchy-shell moo.omaplugctl hide
omarchy-shell moo.omaplugctl status
python3 ~/dil/plugins/omaplugctl/controller.py check-updates
python3 ~/dil/plugins/omaplugctl/controller.py update <plugin-id>
```

Runtime cache and operation state live under `$XDG_STATE_HOME/omarchy/omaplugctl` (default `~/.local/state/omarchy/omaplugctl`). They are never committed. No Omarchy packaged source is modified.

`Widget.qml` owns the bar icon; `Service.qml` owns the persistent menu and controller. Recreated icons register their anchor with the service. Tests: run `python3 -m unittest -v` with `TMPDIR` set to a task scratch directory; run `qmllint` for changed QML and exercise pointer behavior with Quickshell/QtTest.
