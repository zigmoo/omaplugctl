# OmaPlugCtl

Manage Omarchy bar plugins from the plug icon in the bar.

The compact screen diagram moves the bar to any edge. The current edge is highlighted and the other edges remain faintly visible. The menu follows the bar without closing, including changes between horizontal and vertical placement. Sorting defaults to screen appearance order, with name and pending-update date also available.

Hover a plugin row for its function, local update date, author and default Omarchy status. Enable/disable, About, movement and uninstall actions remain available. Uninstall requires confirmation. Default Omarchy plugins cannot be removed, and OmaPlugCtl cannot disable or remove itself.

**Check updates** fetches each installed source repository and caches its status. Normal refreshes do not contact upstream. An update icon appears when source changes are pending. Hover it for the latest change date and up to three commit subjects.

**Click an update icon to update that plugin.** A detached worker fetches the current branch’s configured origin ref and fast-forwards the actual running checkout to that exact fetched commit. Symlinked installations update their underlying source repo. It never creates a merge commit, rebases, stashes or resets local work. Dirty checkouts, diverged histories, detached HEAD and branches without origin tracking stop with an error. The menu displays progress and confirms the result only after Git readback. Source text and errors render as plain text. Per-repository locking prevents concurrent mutations. Git hooks are disabled for the fast-forward operation.

The worker survives a shell rescan and an update to OmaPlugCtl itself. After changing files it requests a plugin rescan. The menu’s lightweight status polling refreshes the installed version and clears the update indicator when the checkout is current. Failed updates display their reason; no terminal, agent, review task or confirmation prompt is opened by an update click. Built-in plugins belonging to the shared Omarchy repository remain managed by Omarchy’s system updater.

Agentic review is retired from `master`. The complete implementation, including the unfinished background GitHub-publication prototype, is preserved on [archive/agentic-reviews](https://github.com/zigmoo/omaplugctl/tree/archive/agentic-reviews) at commit `031d255`, locally and on both remotes. The active version contains no reviewer configuration, dispatch, report polling or publication code. Existing DIL review evidence and machine settings are retained outside this repository for future use. Malware scanning is not part of this update path.

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
