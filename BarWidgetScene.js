.pragma library

function visitHosts(item, visibleOnly, visit) {
  if (visibleOnly && !item.visible) return
  // Omarchy mounts a widget under its host's on-screen slot. The canonical
  // ID resolves legacy layout names and aliases to the installed plugin.
  if (typeof item.pluginApiId === "string" && item.owner && item.activeItem) {
    if (!visibleOnly || (item.activeItem.visible && item.activeItem.opacity > 0)) visit(item)
    if (!item.activeItem.sectionHost) return
  }
  for (let child of item.children) visitHosts(child, visibleOnly, visit)
}

function customArtwork(item, component) {
  for (let child of item.children) {
    if (child.visible && child.sourceComponent === component && typeof child.paintedWidth === "number")
      return child
    if (child.visible) {
      let found = customArtwork(child, component)
      if (found) return found
    }
  }
  return null
}

function iconFor(item, visibleOnly) {
  if (visibleOnly && (!item.visible || item.opacity === 0)) return null
  let iconButton = typeof item.glyphPaintedHeight === "number"
  if (iconButton && item.iconComponent) {
    let artwork = customArtwork(item, item.iconComponent)
    if (artwork) return { artwork: artwork }
  } else if ((iconButton || item.iconLabel === true) && typeof item.text === "string"
             && item.text.trim() && Array.from(item.text).length <= 2) {
    return { glyph: item.text, font: item.fontFamily || "", rotation: item.textRotation || 0 }
  }
  for (let child of item.children) {
    let icon = iconFor(child, visibleOnly)
    if (icon) return icon
  }
  return null
}
