import QtQuick
import qs.Commons as Commons
import qs.Ui as Ui
import "PluginKinds.js" as Kinds

Ui.MultiSelect {
  id: root
  required property var host
  property var plugins: []
  property var favoriteOverrides: ({})
  readonly property bool enabledOnly: values.indexOf("enabled") !== -1
  readonly property bool updatesOnly: values.indexOf("updates") !== -1
  readonly property bool favoritesOnly: values.indexOf("favorites") !== -1
  readonly property var selectedKinds: values.filter(function(value) { return Kinds.keys.indexOf(value) !== -1 })
  readonly property bool allSelected: !enabledOnly && !updatesOnly && !favoritesOnly && selectedKinds.length === Kinds.keys.length
  readonly property var filteredPlugins: plugins.filter(function(plugin) {
    if (root.enabledOnly && !plugin.enabled) return false
    if (root.favoritesOnly && !root.isFavorite(plugin)) return false
    if (root.updatesOnly && (!plugin.update || ["available", "rewritten", "diverged"].indexOf(plugin.update.status) === -1)) return false
    if (root.selectedKinds.length === 0) return root.enabledOnly || root.updatesOnly || root.favoritesOnly
    return Kinds.matches(plugin.kinds, root.selectedKinds)
  })
  objectName: "pluginKindFilter"
  showLabel: false
  values: Kinds.keys.slice()
  options: [
    {value: "enabled", label: host.text("kinds.enabled"), description: host.text("kinds.enabledHelp")},
    {value: "updates", label: host.text("kinds.updates"), description: host.text("kinds.updatesHelp")},
    {value: "favorites", label: host.text("kinds.favorites"), description: host.text("kinds.favoritesHelp")}
  ].concat(Kinds.keys.map(function(kind) {
    return {value: kind, label: Kinds.icons[kind] + " " + root.host.text("kind." + kind + ".label"), description: root.host.text("kind." + kind + ".help")}
  }))
  function selectAllKinds() { values = Kinds.keys.slice() }
  function isFavorite(plugin) {
    var override = favoriteOverrides[plugin.id]
    return typeof override === "boolean" ? override : plugin.favorite === true
  }
  function selectionLabel() {
    if (selectedKinds.length === 0 || selectedKinds.length === Kinds.keys.length) {
      if (favoritesOnly) {
        if (!enabledOnly && !updatesOnly) return host.text("kinds.favorites")
        return host.text("kinds.selected").arg(Commons.I18n.formatNumber(values.length - selectedKinds.length))
      }
      if (enabledOnly && updatesOnly) return host.text("kinds.enabledUpdates")
      if (enabledOnly) return host.text("kinds.enabled")
      if (updatesOnly) return host.text("kinds.updates")
    }
    return allSelected ? host.text("kinds.all") : values.length === 0 ? host.text("kinds.none")
      : values.length === 1 ? host.text("kind." + values[0] + ".label")
      : host.text("kinds.selected").arg(Commons.I18n.formatNumber(values.length))
  }
  noSelectionText: host.text("kinds.none")
  placeholderText: host.text("kinds.search")
  fontFamily: host.themeFont
}
