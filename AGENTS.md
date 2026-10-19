# OmaPlugCtl

Read `$HOME/READ_THIS_DIL_FIRST.md` and follow the DIL bootstrap and local guidance before working here.

- Canonical source: `$HOME/dil/plugins/omaplugctl`; the active plugin is symlinked from `$HOME/.config/omarchy/plugins/moo.omaplugctl`.
- The trunk is `master`. Commit through `scm_tool` with a task-prefixed subject, an existing `compose_tool` composition reference, validation evidence, and the generated session signature.
- Follow the Omarchy skill for plugin changes. Do not patch Omarchy's packaged or development source to implement this manager.
- Run `python3 -m unittest -v` with `TMPDIR` resolved under DIL's task scratch directory, and Qt 6 `/usr/lib/qt6/bin/qmllint` on changed QML (the default binary may be Qt 5). Exercise relevant pointer interactions with Quickshell/QtTest.
- Keep the menu and controller in `Service.qml`; orientation changes recreate `Widget.qml`.
- Plugin and repository text must render as plain text. Source checks never install code. An update click authorizes the local ClamAV check and update; no further prompt is required. Preserve local changes.
- Runtime cache belongs under the user's XDG state directory; never commit it. Historical `archive/` artifacts and Python caches are ignored.
- Agentic review code is retired from master and preserved on `archive/agentic-reviews` locally and on both remotes. Do not restore it without operator direction.
- Normal update clicks fast-forward the running independent checkout on its origin tracking branch. Reconcile rewritten history only when every installed-only commit has a verbatim patch match upstream; reject merge/empty commits, verify a backup branch first, and use a non-forced checkout with ignored-file protection. Never stash, hard-reset, rebase or create a merge. Shared Omarchy plugins remain system-managed.
- ClamAV scanning defaults on and runs against every blob at the pinned commit before checkout changes. Do not trust Git archive export-ignore or follow source symlinks. Detection, incomplete coverage and scanner/signature failures stop updates. No plugin content is uploaded. Keep engine/database files outside the source repo.
- For missing/generic authors, trace plugin files through renames to first recorded commits; retain meaningful manifest attribution and label shallow history. Config state must remain storage-confirmed.

- Runtime helpers are plain PHP 8.1+ CLI with `php -n`; no Composer, optional PHP extensions or build step. Python files remain a development reference. Syntax-check PHP and run the combined Python/PHP contract suite. Keep the missing-PHP probe and explicit terminal install action independent of PHP itself.
