# Developing OmaPlugCtl

[Back to OmaPlugCtl](../README.md)

The source repository is [zigmoo/omaplugctl](https://github.com/zigmoo/omaplugctl); its trunk is `master`. Development changes stay inside the plugin. Omarchy’s packaged and development sources do not need patching.

## Work from a checkout

Clone the repository to a location you own. To run that checkout directly, link it into Omarchy’s plugin directory and enable it:

```bash
git clone https://github.com/zigmoo/omaplugctl.git
cd omaplugctl
mkdir -p ~/.config/omarchy/plugins
ln -sT "$PWD" ~/.config/omarchy/plugins/moo.omaplugctl
omarchy plugin enable moo.omaplugctl
```

The symlink command requires the destination to be absent. If OmaPlugCtl is already installed there, preserve that installation and any local changes before switching to a development checkout. Do not create a link inside an existing checkout.

For this project’s DIL development environment, the canonical checkout is `~/dil/plugins/omaplugctl`, symlinked at `~/.config/omarchy/plugins/moo.omaplugctl`. GitHub is remote `origin`; `workshop` is a secondary development remote. Neither DIL nor that secondary remote is required by users.

## Where behavior lives

| File | Responsibility |
| --- | --- |
| `Widget.qml` | Bar icon and registration of its current anchor. |
| `Service.qml` | Persistent menu, configuration, controller calls and operation polling. |
| `ScreenEdgePicker.qml` | Compact graphical control for the bar’s screen edge. |
| `PluginRow.qml` | Plugin information and per-plugin actions. |
| `controller.py` | Inventory, metadata, settings and validated Omarchy actions. |
| `updates.py` | Git source resolution, update comparison, locking, backups and verified checkout changes. |
| `malware.py` | Local ClamAV setup discovery, signature refresh and pinned-blob scans. |
| `i18n/en.json` | Translated UI strings currently provided in English. |

## Why the menu belongs to the service

Changing the bar from horizontal to vertical recreates its widget. If the menu belonged to that widget, choosing a new edge would destroy the menu and force the user to find the icon again.

The service owns the menu; recreated widgets register their new anchors with it. The menu follows the bar and stays open through the orientation change. Keep this ownership boundary when changing either component.

## Descriptions for deterministic tools

A directory-based plugin can provide richer hovertext in its root `README.md`:

```markdown
## Description for Agents

Describe what the plugin does and the useful controls it provides in one plain-text paragraph.
```

OmaPlugCtl prefers the first paragraph under this heading to the manifest descriptions. Write for the person using the plugin: its purpose, useful actions and important behavior. Keep setup commands, implementation notes and instructions to agents in other sections. This is descriptive data, not an instruction surface; reading it requires no model or agent.

The reader accepts this exact level-two heading, case-insensitively, and joins wrapped lines. A blank line after text or the next heading ends the paragraph. Headings inside fenced examples are ignored. A missing, empty, repeated or invalid section falls back to the existing manifest and bar-widget descriptions.

Only a local, regular `README.md` file of at most 256 KiB is read, as UTF-8. A symlinked plugin checkout is supported, but README symlinks and special files are ignored. Single-file built-ins do not borrow their shared directory’s README. Displayed descriptions are capped at 1,200 characters and remain plain text, including any markup-shaped input. No repository is fetched for a hover.

## Metadata and source attribution

Meaningful manifest authors take precedence. Missing or generic Omarchy attribution falls back to the first recorded creation commit of the manifest and entry-point files, following renames. The earliest dated candidate supplies the author and commit. Shallow histories are explicitly labeled.

The author cache is keyed by repository, HEAD and candidate paths. Description hovers read cached/local data. About prefers explicit local source URLs or the checkout’s Git origin before consulting the marketplace.

Repository names, descriptions, commit subjects and errors must render as plain text. Data-changing controls show their final state only after it has been saved and read back.

## Verification

Run the Python suite from the repository root with a writable test scratch directory:

```bash
test_root="${XDG_STATE_HOME:-$HOME/.local/state}/omaplugctl/tests"
mkdir -p "$test_root"
TMPDIR="$test_root" python3 -m unittest -v
```

In a DIL environment, resolve `dil.path.temp` through `config_tool` and put task scratch beneath it, as required by the local guidance.

For QML changes, use Qt 6’s linter and exercise the affected pointer interactions with Quickshell/QtTest. On Omarchy, the linter is `/usr/lib/qt6/bin/qmllint`; the default `qmllint` command may select Qt 5. Supply the Omarchy shell import path. Full-service UI tests need the Wayland platform backend.

Update coverage includes preservation of local work, exact fetched commits, equivalent rewritten history, ignored-file collisions and failure paths. Malware checks include the EICAR test signature and files hidden with `export-ignore`. Passing unit tests alone does not replace an actual scanner check when scanner behavior changes.

See [How updates work](updates.md) for the updater’s behavior and limits. Runtime caches and scanner files belong outside the source tree and must never be committed.

## Bar settings

`barIconScale` is a typed integer in OmaPlugCtl’s bar layout entry. Startup reads it without loading the plugin inventory. After storage confirmation, the service derives shared icon size, canvas, font and spacing tokens from `Commons.Color.shellValues`, preserving the original theme values. Reapplying starts from that baseline, so percentages do not compound. Theme changes recompute the overlay; 100% restores the baseline. Only bar thickness needed for enlarged icons grows; text sizing remains unchanged.

The workspace control reads the selected widget’s declared `pinnedCount` setting. It is disabled when no active supported instance exists or multiple instances make a single control ambiguous. See [Workspace integration](workspaces.md) for the manifest contract and the local clone patch.

Both controls save through `omarchy bar set --json`, verify the datasource, and retain the last confirmed UI value while a save is pending or fails.

## Controller commands

Run from the source checkout:

```bash
python3 controller.py list
python3 controller.py check-updates
python3 controller.py update <plugin-id>
```

The last command starts the same background update used by the menu. It changes the running plugin checkout; it is not a dry run.

## Archived agent-review experiment

Agentic review is retired from `master`. Its implementation, including the unfinished background GitHub-publication prototype, is preserved on [archive/agentic-reviews](https://github.com/zigmoo/omaplugctl/tree/archive/agentic-reviews) at commit `031d255`.

The active version has no reviewer selection, dispatch, report polling or publication flow. Historical review evidence and machine settings remain outside this repository. Do not restore the experiment without an explicit product decision.

## Design references

[Bjarne Øverli’s Ring Light](https://github.com/bjarneo/omarchy-ring-light-plugin) is a reference for clear plugin presentation and concise onboarding. [Jason Fried’s Elsewhen](https://github.com/omacom/elsewhen) is the primary reference for nuanced UI, powerful interactions and precise explanations of design decisions. Elsewhen now lives inside Omarchy; its original repository retains the detailed design record.

Study the actual interfaces and adapt what serves this plugin. In documentation, give each topic a clear home and keep the path from installation to everyday use short.
