# OmaPlugCtl

Read `$HOME/READ_THIS_DIL_FIRST.md` and follow the DIL bootstrap and local guidance before working here.

- Canonical source: `$HOME/dil/plugins/omaplugctl`; the active plugin is symlinked from `$HOME/.config/omarchy/plugins/moo.omaplugctl`.
- The trunk is `master`. Commit through `scm_tool` with a task-prefixed subject, an existing `compose_tool` composition reference, validation evidence, and the generated session signature.
- Follow the Omarchy skill for plugin changes. Do not patch Omarchy's packaged or development source to implement this manager.
- Run `python3 -m unittest -v` with `TMPDIR` resolved under DIL's task scratch directory, and `qmllint` on changed QML. Exercise relevant pointer interactions with Quickshell/QtTest.
- Keep the menu and controller in `Service.qml`; orientation changes recreate `Widget.qml`.
- Plugin and repository text must render as plain text. Source checks never install code; installation requires the supported updater's review/confirmation flow. Preserve local changes.
- Runtime cache belongs under the user's XDG state directory; never commit it. Historical `archive/` artifacts and Python caches are ignored.
- Agentic review code is retired from master and preserved on `archive/agentic-reviews` locally and on both remotes. Do not restore it without operator direction.
- Update clicks fast-forward only the running independent plugin checkout on its origin tracking branch. Preserve local changes, local commits and divergence; never stash, reset, rebase or create a merge. Packaged/shared Omarchy plugins remain managed by the Omarchy updater.
