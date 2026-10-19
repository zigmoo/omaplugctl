import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui

Item {
  id: root
  required property var plugin
  required property var host
  property bool expanded: false
  readonly property bool confirming: host.confirmingId === plugin.id
  readonly property bool available: !host.busy && host.confirmingId === ""
  readonly property color ink: Commons.Color.popups.text
  implicitHeight: body.implicitHeight + Style.space(8)

  Column {
    id: body
    width: parent.width
    spacing: Style.space(5)
    Item {
      id: summary
      width: parent.width
      height: Math.max(labels.implicitHeight, actions.implicitHeight)
      HoverHandler { id: rowHover }
      Ui.PanelToolTip {
        id: descriptionTip
        objectName: "pluginDescriptionTooltip"
        visible: rowHover.hovered && !actionHover.hovered && !root.host.busy
        text: root.plugin.description || root.host.noDescriptionText
        fontFamily: root.host.themeFont
        width: Math.min(root.width, Style.space(360))
        x: 0
        y: summary.height + Style.space(4)
        contentItem: Item {
          readonly property real insetLeft: Border.left(descriptionTip.panelBorderSpec) + Style.spacing.controlPaddingX
          readonly property real insetRight: Border.right(descriptionTip.panelBorderSpec) + Style.spacing.controlPaddingX
          readonly property real insetTop: Border.top(descriptionTip.panelBorderSpec) + Style.spacing.controlPaddingY
          readonly property real insetBottom: Border.bottom(descriptionTip.panelBorderSpec) + Style.spacing.controlPaddingY
          implicitHeight: tooltipBody.implicitHeight + insetTop + insetBottom
          Column {
            id: tooltipBody
            x: parent.insetLeft
            y: parent.insetTop
            width: parent.width - parent.insetLeft - parent.insetRight
            spacing: Style.space(7)
            Text {
              objectName: "pluginDescriptionText"
              width: parent.width
              text: descriptionTip.text
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
              color: descriptionTip.panelForeground
              font.family: descriptionTip.fontFamily
              font.pixelSize: descriptionTip.fontSize
            }
            Rectangle {
              width: parent.width
              height: Math.max(1, Style.space(1))
              color: Qt.alpha(descriptionTip.panelForeground, 0.2)
            }
            Text {
              objectName: "pluginMetadataText"
              width: parent.width
              text: root.host.pluginFooter(root.plugin)
              textFormat: Text.PlainText
              wrapMode: Text.WordWrap
              color: Qt.alpha(descriptionTip.panelForeground, 0.7)
              font.family: descriptionTip.fontFamily
              font.pixelSize: Style.font.caption
            }
          }
        }
      }
      PluginIcon {
        id: mark
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        pluginId: root.plugin.id
        ink: root.ink
        fontFamily: root.host.themeFont
        width: Style.font.icon
        height: width
      }
      Column {
        id: labels
        anchors.left: mark.right
        anchors.leftMargin: Style.space(8)
        anchors.right: actions.left
        anchors.rightMargin: Style.space(8)
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(1)
        Text {
          width: parent.width
          text: root.plugin.name
          font.family: root.host.themeFont
          font.pixelSize: Style.font.body
          color: root.ink
          textFormat: Text.PlainText
          elide: Text.ElideRight
        }
        Text {
          objectName: "pluginOperationStatus"
          width: parent.width
          visible: !!root.plugin.operation && !!root.plugin.operation.message
          text: root.plugin.operation ? root.plugin.operation.message || "" : ""
          textFormat: Text.PlainText
          color: root.plugin.operation && root.plugin.operation.status === "error" ? Commons.Color.urgent : Commons.Color.accent
          font.family: root.host.themeFont
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
          maximumLineCount: 3
          elide: Text.ElideRight
        }
        Text {
          width: parent.width
          objectName: "pluginUpdateStatus"
          visible: !!root.plugin.update && (["current", "available"].indexOf(root.plugin.update.status) === -1 || !!root.plugin.update.dirty)
          text: root.host.updateLabel(root.plugin)
          textFormat: Text.PlainText
          font.family: root.host.themeFont
          font.pixelSize: Style.font.caption
          color: root.plugin.update && root.plugin.update.status === "available" ? Commons.Color.accent : Qt.darker(root.ink, 1.4)
          elide: Text.ElideRight
        }
        Text {
          width: parent.width
          text: {
            if (!root.plugin.enabled) return "Disabled · not on the bar"
            if (root.plugin.instances.length > 1) return "Enabled · " + root.plugin.instances.length + " positions"
            var p = root.plugin.instances[0]
            return p ? "Position: " + p.section.charAt(0).toUpperCase() + p.section.slice(1) + " · slot " + (p.index + 1) : "Enabled · not on the bar"
          }
          font.family: root.host.themeFont
          font.pixelSize: Style.font.caption
          color: Qt.darker(root.ink, 1.4)
          elide: Text.ElideRight
        }

      }
      Row {
        id: actions
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: Style.space(3)
        HoverHandler { id: actionHover }
        UpdateIndicator {
          visible: !!root.plugin.update && root.plugin.update.kind !== "omarchy" && ["available", "rewritten", "diverged"].indexOf(root.plugin.update.status) !== -1
          plugin: root.plugin
          host: root.host
          enabled: root.available && (!root.plugin.operation || root.plugin.operation.status !== "working")
          onClicked: root.host.updatePlugin(root.plugin)
        }
        Ui.PanelActionButton {
          objectName: "pluginEnableButton"
          iconText: root.plugin.enabled ? "󰏤" : "󰐊"
          tooltipText: root.plugin.isSelf ? root.host.text("updates.controllerProtected") : (root.plugin.enabled ? "Disable " : "Enable ") + root.plugin.name
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: root.available && root.plugin.canDisable !== false
          onClicked: root.host.invoke(root.plugin.enabled ? "disable" : "enable", root.plugin.id)
        }
        Ui.PanelActionButton {
          iconText: "󰋽"
          tooltipText: "About " + root.plugin.name
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: root.available
          onClicked: root.host.invoke("about", root.plugin.id)
        }
        Ui.PanelActionButton {
          iconText: root.expanded ? "󰅀" : "󰇙"
          objectName: "pluginMoreButton"
          tooltipText: root.expanded ? "Close controls" : "Move or uninstall " + root.plugin.name
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: !root.host.busy && (root.host.confirmingId === "" || root.confirming)
          onClicked: { if (root.confirming) root.host.confirmingId = ""; root.expanded = !root.expanded }
        }
      }
    }
    Column {
      width: parent.width
      visible: root.expanded
      spacing: Style.space(4)
      Repeater {
        model: root.plugin.instances
        delegate: Row {
          required property var modelData
          id: location
          width: body.width
          spacing: Style.space(5)
          Text {
            text: "Move " + location.modelData.section + " · " + (location.modelData.index + 1) + " to"
            anchors.verticalCenter: parent.verticalCenter
            font.family: root.host.themeFont
            font.pixelSize: Style.font.caption
            color: Qt.darker(root.ink, 1.4)
          }
          Repeater {
            model: ["left", "center", "right"].filter(function(s) { return s !== location.modelData.section })
            delegate: Ui.Button {
              required property string modelData
              text: modelData.charAt(0).toUpperCase() + modelData.slice(1)
              horizontalPadding: Style.space(4)
              verticalPadding: Style.space(2)
              fontFamily: root.host.themeFont
              foreground: root.ink
              focusable: true
              enabled: root.available
              onClicked: root.host.invoke("move", root.plugin.id, modelData, location.modelData.section, location.modelData.index)
            }
          }
        }
      }
      Ui.Button {
        text: "Uninstall…"
        visible: root.plugin.canRemove && !root.confirming
        horizontalPadding: Style.space(4)
        verticalPadding: Style.space(2)
        fontFamily: root.host.themeFont
        foreground: root.ink
        focusable: true
        enabled: root.available
        onClicked: root.host.confirmingId = root.plugin.id
      }
      Text {
        width: parent.width
        visible: root.confirming
        text: "Uninstall " + root.plugin.name + "? This removes its local plugin checkout."
        wrapMode: Text.WordWrap
        textFormat: Text.PlainText
        font.family: root.host.themeFont
        font.pixelSize: Style.font.caption
        color: root.ink
      }
      Row {
        spacing: Style.space(6)
        visible: root.confirming
        Ui.Button {
          text: "Confirm uninstall"
          horizontalPadding: Style.space(4)
          verticalPadding: Style.space(2)
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: !root.host.busy
          onClicked: root.host.invoke("remove", root.plugin.id, "", "", -1, true)
        }
        Ui.Button {
          text: "Cancel"
          horizontalPadding: Style.space(4)
          verticalPadding: Style.space(2)
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          onClicked: root.host.confirmingId = ""
        }
      }
    }
  }
  Ui.PanelSeparator { anchors.bottom: parent.bottom; width: parent.width; foreground: root.ink }
}
