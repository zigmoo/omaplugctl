# OmaPlugCtl

Enable, arrange and update Omarchy bar plugins from one menu.

Click the plug icon in the bar to see what is running, move the bar to another screen edge, or update an installed plugin without leaving the menu.

<img src="docs/assets/overview.png" alt="OmaPlugCtl menu with a graphical bar-position selector, sort control and plugin rows with individual actions" width="420">

## Install

Requires Omarchy’s Quickshell shell and plugin commands, plus Git and Python 3.

Install ClamAV for local malware checks, then add the plugin:

```bash
omarchy pkg add clamav
omarchy plugin add https://github.com/zigmoo/omaplugctl.git --enable
```

The plug icon appears in the bar’s right section. Open it to manage your installed bar plugins, including OmaPlugCtl itself.

## The plugin list

Each row shows a plugin’s name, bar position and update status. Hover the row for its description, local update date, author and whether it ships with Omarchy.

| Control | Action |
| --- | --- |
| Power or play | Disable or enable the plugin. |
| Update arrows | Update this plugin when a source update is available. Hover for the latest change date and up to three commit subjects. |
| Information | Open the plugin’s source page. |
| Three dots | Move an instance to another bar section, or uninstall an installed third-party plugin. |

Uninstall asks for confirmation and removes the plugin’s local checkout. Disabling keeps its files. Built-in plugins cannot be uninstalled here; OmaPlugCtl keeps itself enabled so its controls remain available.

If a plugin provides no meaningful author attribution, OmaPlugCtl traces its manifest and entry-point files through Git history to their first recorded commits. The hover footer identifies the author and commit; shallow histories are labeled as the earliest available record.

## Move the bar

Click an edge of the little screen diagram to move the bar there. The highlighted edge is the current position; the other three remain faintly visible.

The menu moves with the bar and stays open, even when switching between horizontal and vertical placement. You can try another edge immediately without searching for the plug icon again.

## Find and arrange plugins

**Sort by** offers three views:

- **Screen order**, the default, follows the bar’s sections and slots, then lists plugins without a position.
- **Name** sorts alphabetically.
- **Pending update date** puts pending updates first, newest change first.

Sorting changes the list, not the bar. To move a plugin, open its three-dot controls and choose a destination section. Plugins with multiple bar instances have a separate movement control for each instance.

## Update a plugin

Click **Check updates** to fetch installed source repositories and look for changes. The refresh icon reloads local state without contacting upstream repositories.

When an update icon appears, hover it to see what changed, then click to update. The work happens in the background; progress and the result appear in the menu. The first scanned update may take longer while ClamAV downloads its signatures.

Updates apply to the checkout actually running the plugin, including the target of a symlink. Local edits and unmatched local commits are preserved. Built-in plugins in Omarchy’s shared repository are updated with `omarchy update`.

If an update stops, read the row or footer message for the reason. Common causes are local changes, divergent commits, missing ClamAV, or a failed scan. Resolve the cause, then check again. [How updates work](docs/updates.md) explains reconciliation, backups and scanning limits.

## Config

The **Config** tab holds the saved sort order and **Scan with ClamAV before updating**, which defaults to on. Settings appear as saved only after Omarchy confirms them.

ClamAV checks the fetched source locally before an update changes the checkout. Signatures refresh as needed, at most once per day. Plugin contents are never uploaded to a scanning service.

A detection, scanner error or incomplete scan stops the update. A clean result means **no threats detected**, not proof of safety. Turning the toggle off explicitly skips scanning for subsequent updates.

## Commands

```bash
omarchy-shell moo.omaplugctl show
omarchy-shell moo.omaplugctl hide
omarchy-shell moo.omaplugctl status
```

To remove OmaPlugCtl itself:

```bash
omarchy plugin remove moo.omaplugctl
```

## Description for Agents

OmaPlugCtl manages Omarchy bar plugins from a menu that stays open when the bar moves. Enable or disable plugins, move their bar instances, and sort by screen order, name or pending update date. Hover rows for function, author and local update date. Check source repositories and update individual running checkouts, with local ClamAV scanning enabled by default and protection for local changes.

## Development

See the [development guide](docs/development.md) for local checkouts, architecture, verification and the archived agent-review experiment. Report problems through [GitHub issues](https://github.com/zigmoo/omaplugctl/issues), including the message shown and the affected plugin’s source repository.
