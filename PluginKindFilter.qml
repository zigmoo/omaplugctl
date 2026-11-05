import QtQuick
import qs.Commons as Commons
import qs.Ui as Ui
import "PluginKinds.js" as Kinds

Ui.MultiSelect {
  id: root
  required property var host
  property var plugins: []
  readonly property var filteredPlugins: plugins.filter(function(plugin) { return Kinds.matches(plugin.kinds, root.values) })
  readonly property bool allSelected: values.length === Kinds.keys.length
  objectName: "pluginKindFilter"
  showLabel: false
  values: Kinds.keys.slice()
  options: Kinds.keys.map(function(kind) {
    return {value: kind, label: Kinds.icons[kind] + " " + root.host.text("kind." + kind + ".label"), description: root.host.text("kind." + kind + ".help")}
  })
  function selectionLabel() {
    return allSelected ? host.text("kinds.all") : values.length === 0 ? host.text("kinds.none")
      : values.length === 1 ? host.text("kind." + values[0] + ".label")
      : host.text("kinds.selected").arg(Commons.I18n.formatNumber(values.length))
  }
  noSelectionText: host.text("kinds.none")
  placeholderText: host.text("kinds.search")
  fontFamily: host.themeFont
}
