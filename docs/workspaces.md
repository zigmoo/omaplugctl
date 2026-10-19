# Workspace integration

[Back to OmaPlugCtl](../README.md)

The workspace stepper controls a minimum number of visible buttons. It does not limit Hyprland workspaces or alter window placement. A value of zero leaves existing workspaces visible without reserving extra empty buttons.

Omarchy’s default widget currently reserves five buttons per monitor and adds other existing workspaces. It reads monitor assignments, but it does not read a configured button count. Earlier clones may reserve a different number in their QML source.

OmaPlugCtl enables the control only when exactly one active workspace widget advertises support. Its manifest must identify `omarchy.workspaces`, or declare `omarchy.clonedFrom` as `omarchy.workspaces`, and expose an integer `pinnedCount` entry in `barWidget.schema`. The saved value is an integer from 0 to 10 in that widget’s bar layout entry. The widget must read this setting and retain existing workspaces when constructing its buttons. `barWidget.defaults.pinnedCount` supplies its initial minimum; otherwise OmaPlugCtl uses five.

## This machine’s clone

The installed `moo.workspaces` clone now reads `setting("pinnedCount", 9)`. Its default stays at nine, matching its previous appearance. Positive existing workspace IDs are included regardless of the minimum. Its manifest exposes the integer setting.

The exact customization is preserved in [workspace-count.patch](../integrations/workspace-count.patch). It targets this older clone and is not a general patch for newer Omarchy widgets. OmaPlugCtl never patches another widget automatically. Integrate the setting into a user-owned clone rather than changing packaged Omarchy sources.
