.pragma library

var keys = ["bar-widget", "bar", "overlay", "panel", "menu", "service", "other"]
var icons = {"bar-widget": "▣", "bar": "▰", "overlay": "□", "panel": "▤", "menu": "☰", "service": "⚙", "other": "?"}

function normalized(kinds) {
  var found = {}
  if (kinds && typeof kinds !== "string" && typeof kinds.length === "number") {
    for (var i = 0; i < Math.min(kinds.length, 32); i++) {
      var kind = kinds[i]
      found[keys.indexOf(kind) >= 0 ? kind : "other"] = true
    }
  }
  if (!Object.keys(found).length) found.other = true
  return keys.filter(function(kind) { return !!found[kind] })
}

function matches(kinds, selected) {
  return normalized(kinds).some(function(kind) { return selected.indexOf(kind) >= 0 })
}
