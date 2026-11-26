import QtQuick
import "BarWidgetScene.js" as Scene

QtObject {
  id: root
  property Item barContent: null
  property var rememberedGlyphs: Object.create(null)
  readonly property var liveIcons: {
    let icons = Object.create(null)
    if (!barContent) return icons
    let hidden = Object.create(null)
    Scene.visitHosts(barContent, false, function(host) {
      if (icons[host.pluginApiId]) return
      let item = host.activeItem
      let icon = Scene.iconFor(item, true)
      if (icon) icons[host.pluginApiId] = icon
      else if (!hidden[host.pluginApiId]) hidden[host.pluginApiId] = Scene.iconFor(item, false)
    })
    return Object.assign(hidden, icons)
  }
  readonly property bool hasArtwork: Object.values(liveIcons).some(function(icon) { return icon && !!icon.artwork })

  onLiveIconsChanged: {
    let next = Object.assign(Object.create(null), rememberedGlyphs)
    let changed = false
    for (let id of Object.keys(liveIcons)) {
      let icon = liveIcons[id]
      if (!icon || !icon.glyph) continue
      let previous = next[id]
      if (!previous || previous.glyph !== icon.glyph || previous.font !== icon.font || previous.rotation !== icon.rotation) {
        next[id] = icon
        changed = true
      }
    }
    if (changed) rememberedGlyphs = next
  }

  function forPlugin(id) { return liveIcons[id] || rememberedGlyphs[id] || null }
}
