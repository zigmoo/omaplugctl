import QtQuick
import qs.Commons
import qs.Commons as Commons

Item {
  id: root
  property string pluginId: ""
  property bool defaultOmarchy: false
  property color ink: Commons.Color.popups.text
  property string fontFamily: Style.font.family
  property var liveIcon: null
  property bool captureArtwork: false
  property int artworkTick: 0
  property var capturedArtwork: null
  property bool capturing: false
  readonly property string liveGlyph: liveIcon && liveIcon.glyph ? liveIcon.glyph : ""
  readonly property Item artwork: liveIcon && liveIcon.artwork ? liveIcon.artwork : null
  implicitWidth: Style.font.icon * (defaultOmarchy && hasOwnIcon ? 2 : 1) + (defaultOmarchy && hasOwnIcon ? Style.space(4) : 0)
  implicitHeight: Style.font.icon
  readonly property string sourceId: pluginId === "moo.dropbox" ? "omarchy.dropbox" : pluginId === "promaa.clock" ? "omarchy.clock" : pluginId === "moo.workspaces" ? "omarchy.workspaces" : pluginId
  readonly property var marks: ({
    "gladimdim.ai-limits": "󰚩", "omarchy.active-window": "󰖯", "omarchy.agents": "󱚣",
    "omarchy.audio": "󰕾", "omarchy.bluetooth": "󰂯", "io.github.shawnyeager.briotune": "󰖠",
    "omarchy.clock": "󰥔", "omarchy.monitor": "󰍺", "omarchy.elsewhen": "󰇧",
    "bjarneo.hyperpower": "\uf205", "omarchy.indicators": "󰀦", "omarchy.keyboard-layout": "󰌌",
    "omarchy.media": "󰐊", "omarchy.microphone": "󰍬", "omarchy.workspaces": "\uDB85\uDCFB",
    "omarchy.network": "󰤨", "omarchy.menu": "\ue900", "omarchy.system-update": "\uf021",
    "io.github.rodrix2000.photodock": "󰄀", "omarchy.power": "󰁹", "omarchy.spacer": "↔",
    "omarchy.tray": "\uf053", "davefano.trackpad-plus": "󰟸", "omarchy.weather": "󰖙",
    "crmne.hyprmoncfg": "󰍺", "moo.omathemectl": "󰏘", "moo.omaremotes": "󰢹"
  })
  readonly property bool custom: ["moo.omaplugctl", "omarchy.tailscale", "omarchy.dropbox", "com.80kv.omatris", "bjarneo.ring-light", "com.omastorm.radar"].indexOf(sourceId) >= 0
  readonly property bool hasOwnIcon: sourceId !== "omarchy.menu" && (liveGlyph !== "" || capturedArtwork !== null || custom || marks[sourceId] !== undefined)
  function capture() {
    if (!captureArtwork || capturing || !artwork || !artwork.visible || artwork.width <= 0 || artwork.height <= 0) return
    let item = artwork
    capturing = true
    if (!item.grabToImage(function(result) {
      if (!root) return
      root.capturing = false
      if (root.captureArtwork && root.artwork === item && result) root.capturedArtwork = result
    }, Qt.size(48, 48))) capturing = false
  }
  onArtworkChanged: { capturedArtwork = null; capture() }
  onCaptureArtworkChanged: if (captureArtwork) capture()
  onArtworkTickChanged: capture()
  Text {
    objectName: "omarchyIdentityIcon"
    visible: root.defaultOmarchy
    anchors.left: parent.left
    anchors.verticalCenter: parent.verticalCenter
    width: root.height
    text: "\ue900"
    textFormat: Text.PlainText
    color: root.ink
    font.family: "omarchy"
    font.pixelSize: root.height
  }
  Item {
    objectName: "pluginOwnIdentityIcon"
    visible: !root.defaultOmarchy || root.hasOwnIcon
    anchors.right: parent.right
    width: root.defaultOmarchy ? root.height : root.width
    height: root.height
  Text {
    anchors.centerIn: parent
    objectName: "pluginGlyph"
    visible: root.capturedArtwork === null && (root.liveGlyph !== "" || !root.custom)
    text: root.liveGlyph || root.marks[root.sourceId] || "󰐱"
    color: root.ink
    font.family: root.liveGlyph && root.liveIcon.font ? root.liveIcon.font : root.sourceId === "omarchy.menu" ? "omarchy" : root.fontFamily
    font.pixelSize: Math.min(root.width, root.height)
    rotation: root.liveGlyph ? root.liveIcon.rotation : 0
    textFormat: Text.PlainText
  }
  Image {
    objectName: "pluginLiveArtwork"
    anchors.fill: parent
    visible: root.capturedArtwork !== null
    source: root.capturedArtwork ? root.capturedArtwork.url : ""
    fillMode: Image.PreserveAspectFit
    cache: false
  }
  Canvas {
    id: drawing
    anchors.fill: parent
    visible: root.custom && !root.liveGlyph && root.capturedArtwork === null
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    Connections { target: root; function onInkChanged() { drawing.requestPaint() }
    function onSourceIdChanged() { drawing.requestPaint() } }
    onPaint: {
      var c = getContext("2d")
      c.reset(); c.clearRect(0, 0, width, height)
      c.scale(width / 24, height / 24)
      c.fillStyle = root.ink; c.strokeStyle = root.ink; c.lineWidth = 1.8
      if (root.sourceId === "moo.omaplugctl") {
        // US plug: two flat blades, a round grounding pin, body and cord.
        c.fillRect(6, 1, 3, 8); c.fillRect(15, 1, 3, 8)
        c.beginPath(); c.arc(12, 7, 1.5, 0, 2 * Math.PI); c.fill()
        c.fillRect(10.5, 7, 3, 3)
        c.beginPath(); c.moveTo(4, 10); c.lineTo(20, 10); c.lineTo(20, 14)
        c.quadraticCurveTo(20, 20, 12, 20); c.quadraticCurveTo(4, 20, 4, 14); c.closePath(); c.fill()
        c.fillRect(10.5, 19, 3, 5)
      } else if (root.sourceId === "omarchy.tailscale") {
        for (var y = 0; y < 3; y++) for (var x = 0; x < 3; x++) {
          c.globalAlpha = y === 1 || (y === 2 && x === 1) ? 1 : 0.24
          c.beginPath(); c.arc(4 + x * 8, 4 + y * 8, 2.8, 0, Math.PI * 2); c.fill()
        }
      } else if (root.sourceId === "omarchy.dropbox") {
        var tiles = [[6,4],[18,4],[6,12],[18,12],[12,19]]
        for (var i = 0; i < tiles.length; i++) {
          var t = tiles[i]; c.beginPath(); c.moveTo(t[0], t[1]-4); c.lineTo(t[0]+6,t[1]); c.lineTo(t[0],t[1]+4); c.lineTo(t[0]-6,t[1]); c.closePath(); c.fill()
        }
      } else if (root.sourceId === "com.80kv.omatris") {
        var blocks = [[8,4],[0,12],[8,12],[16,12]]
        for (var b = 0; b < blocks.length; b++) c.fillRect(blocks[b][0]+1,blocks[b][1],7,7)
      } else if (root.sourceId === "bjarneo.ring-light") {
        c.beginPath(); c.arc(12,12,9,0,Math.PI*2); c.stroke()
      } else if (root.sourceId === "com.omastorm.radar") {
        for (var r = 3; r <= 10; r += 3.5) { c.beginPath(); c.arc(12,12,r,0,Math.PI*2); c.stroke() }
        c.beginPath(); c.moveTo(12,12); c.lineTo(19,5); c.stroke()
      }
    }
  }
  }
}
