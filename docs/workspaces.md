# Workspace integration

[Back to OmaPlugCtl](../README.md)

The workspace stepper controls a minimum number of visible buttons. It does not limit Hyprland workspaces or alter window placement. A value of zero leaves existing workspaces visible without reserving extra empty buttons.

Omarchy’s default widget currently reserves five buttons per monitor and adds other existing workspaces. It reads monitor assignments, but it does not read a configured button count. Earlier clones may reserve a different number in their QML source.

OmaPlugCtl enables the control only when exactly one active workspace widget advertises support. Its manifest must identify `omarchy.workspaces`, or declare `omarchy.clonedFrom` as `omarchy.workspaces`, and expose an integer `pinnedCount` entry in `barWidget.schema`. The saved value is an integer from 0 to 10 in that widget’s bar layout entry. The widget must read this setting and retain existing workspaces when constructing its buttons. `barWidget.defaults.pinnedCount` supplies its initial minimum; otherwise OmaPlugCtl uses five.

## This machine’s clone

The installed `moo.workspaces` clone reads `setting("pinnedCount", 10)`. Its default and the current saved minimum are ten. It follows the current monitor-aware built-in: each monitor has a block of ten workspace IDs, the requested minimum reserves slots in that block, existing workspaces remain visible, and visiting workspaces retain the built-in behavior. Its manifest exposes the integer setting. Zero is supported without assigning a zero-column layout.

The exact customization is preserved in [workspace-count.patch](../integrations/workspace-count.patch), based on Omarchy source commit `81fd2d23ca6e3462183a4dc8360de3113fa8d80c`. The manifest records that source revision and credits Jason Ziegler's local customization separately from upstream authorship. OmaPlugCtl's hover metadata traces the upstream widget's original author/commit when the clone has no Git history. Source opens the copied upstream revision.

The stock widget can replace the clone after a layout change or reset. A `pinnedCount` value on the stock widget has no effect: it does not implement the setting. Enable the supported clone to restore the control. OmaPlugCtl never patches another widget automatically. Integrate the setting into a user-owned clone rather than changing packaged Omarchy sources.
