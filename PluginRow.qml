import QtQuick
import qs.Commons
import qs.Commons as Commons
import qs.Ui as Ui

Item {
  id: root
  required property var plugin
  required property var host
  property bool expanded: false
  property bool favorite: plugin.favorite === true
  property bool favoritePending: false
  property bool barHidden: false
  property var liveIcon: null
  property bool captureArtwork: false
  property int artworkTick: 0
  readonly property bool notInstalled: plugin.installed === false
  readonly property bool barHovered: visible && rowHover.hovered && plugin.enabled === true && plugin.isBarWidget === true
  readonly property bool confirming: host.confirmingId === plugin.id
  readonly property bool confirmingPause: confirming && plugin.isSelf
  readonly property bool available: !host.busy && host.confirmingId === ""
  readonly property bool isFullBar: (plugin.kinds || []).indexOf("bar") !== -1
  readonly property bool isActiveBar: isFullBar && plugin.active === true
  readonly property bool opensWithoutBar: plugin.canOpen === true && !plugin.isBarWidget && !isFullBar
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
        visible: rowHover.hovered && !kindBadges.hovered && !actionHover.hovered && !root.host.busy
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
        objectName: "pluginIdentityIcon"
        anchors.left: parent.left
        anchors.verticalCenter: parent.verticalCenter
        pluginId: root.plugin.id
        defaultOmarchy: root.plugin.firstParty === true && !root.plugin.clonedFrom
        ink: root.ink
        fontFamily: root.host.themeFont
        liveIcon: root.liveIcon
        captureArtwork: root.captureArtwork
        artworkTick: root.artworkTick
        width: implicitWidth
        height: Style.font.icon
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
        PluginKindBadges {
          id: kindBadges
          width: parent.width
          host: root.host
          kinds: root.plugin.kinds || []
          foreground: root.ink
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
            if (root.notInstalled) return root.host.text(root.plugin.canReinstall ? "plugin.notInstalled" : "plugin.noReinstallSource")
            if (root.isFullBar) return root.host.text(root.isActiveBar ? "bar.active" : "bar.inactive")
            if (!root.plugin.isBarWidget) return root.host.text(root.plugin.enabled ? "plugin.noBarIcon" : "plugin.disabled")
            if (!root.plugin.enabled) return "Disabled · not on the bar"
            if (root.barHidden) return root.host.text("plugin.barHidden")
            if (root.plugin.instances.length > 1) return "Enabled · " + root.plugin.instances.length + " positions"
            var p = root.plugin.instances[0]
            return p ? "Position: " + p.section.charAt(0).toUpperCase() + p.section.slice(1) + " · slot " + (p.index + 1) : root.host.text("plugin.noBarSlot")
          }
          objectName: "pluginPositionStatus"
          textFormat: Text.PlainText
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
        Ui.PanelActionButton {
          objectName: "pluginFavoriteButton"
          iconText: root.favorite ? "󰓎" : "󰓒"
          tooltipText: root.host.text(root.favorite ? "plugin.unfavorite" : "plugin.favorite")
          fontFamily: root.host.themeFont
          foreground: root.favorite ? Commons.Color.accent : root.ink
          focusable: true
          enabled: root.available || root.favoritePending
          onClicked: if (root.available) root.host.invoke(root.favorite ? "unfavorite" : "favorite", root.plugin.id)
        }
        UpdateIndicator {
          visible: !!root.plugin.update && root.plugin.update.kind !== "omarchy" && ["available", "rewritten", "diverged"].indexOf(root.plugin.update.status) !== -1
          plugin: root.plugin
          host: root.host
          enabled: root.available && (!root.plugin.operation || root.plugin.operation.status !== "working")
          onClicked: root.host.updatePlugin(root.plugin)
        }
        Ui.Button {
          objectName: "pluginOpenButton"
          visible: root.opensWithoutBar
          text: root.host.text("plugin.openAction")
          tooltipText: root.host.text("plugin.open")
          height: openIconButton.implicitHeight
          horizontalPadding: Style.space(5)
          verticalPadding: 0
          fontSize: Style.font.caption
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: root.available && root.plugin.enabled
          onClicked: root.host.invoke("open", root.plugin.id)
        }
        Ui.PanelActionButton {
          id: openIconButton
          objectName: "pluginOpenIconButton"
          visible: !!root.plugin.canOpen && !root.opensWithoutBar
          iconText: "󰏋"
          tooltipText: root.host.text("plugin.open")
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: root.available && root.plugin.enabled
          onClicked: root.host.invoke("open", root.plugin.id)
        }
        Ui.PanelActionButton {
          objectName: "pluginEnableButton"
          visible: !root.notInstalled
          iconText: (root.isFullBar ? root.isActiveBar : root.plugin.enabled) ? "󰏤" : "󰐊"
          tooltipText: {
            if (root.isActiveBar && root.plugin.isDefaultBar) return root.host.text("bar.chooseReplacement")
            if (root.isActiveBar) return root.host.text("bar.pause").arg(root.plugin.name)
            if (root.isFullBar) return root.plugin.isDefaultBar ? root.host.text("bar.useDefault") : root.host.text("bar.usePlugin").arg(root.plugin.name)
            return (root.plugin.enabled ? "Disable " : "Enable ") + root.plugin.name
          }
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: root.available && (root.isFullBar || !root.plugin.enabled || root.plugin.canDisable !== false)
          onClicked: {
            if (root.isActiveBar && root.plugin.isDefaultBar) {
              root.host.showReplacementBars()
              return
            }
            if (root.plugin.isSelf && root.plugin.enabled) {
              root.expanded = true
              root.host.confirmingId = root.plugin.id
              return
            }
            var action = root.isFullBar ? (root.isActiveBar ? "reset-bar" : "use-bar") : (root.plugin.enabled ? "disable" : "enable")
            root.host.invoke(action, root.plugin.id)
          }
        }
        Ui.PanelActionButton {
          objectName: "pluginReinstallButton"
          visible: root.notInstalled
          iconText: "󰇚"
          tooltipText: root.host.text("plugin.reinstall")
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: root.available && root.plugin.canReinstall === true
          onClicked: root.host.invoke("reinstall", root.plugin.id)
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
          tooltipText: root.expanded ? "Close controls" : root.plugin.isBarWidget ? "Move or uninstall " + root.plugin.name : root.host.text("plugin.controls")
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: !root.host.busy && (root.host.confirmingId === "" || root.confirming)
          onClicked: { if (root.confirming) root.host.confirmingId = ""; root.expanded = !root.expanded }
        }
      }
    }
    Repeater {
      model: root.notInstalled ? [] : (root.plugin.services || [])
      delegate: Item {
        id: serviceRow
        objectName: "pluginServiceRow"
        required property var modelData
        x: mark.width + Style.space(8)
        width: body.width - x
        height: Math.max(serviceLabel.implicitHeight, serviceAction.visible ? serviceAction.implicitHeight : 0)
        Text {
          id: serviceLabel
          objectName: "pluginServiceStatus"
          anchors.left: parent.left
          anchors.right: serviceAction.visible ? serviceAction.left : parent.right
          anchors.rightMargin: serviceAction.visible ? Style.space(8) : 0
          anchors.verticalCenter: parent.verticalCenter
          text: serviceRow.modelData.name + " · " + root.host.text("service." + serviceRow.modelData.state)
          textFormat: Text.PlainText
          elide: Text.ElideRight
          font.family: root.host.themeFont
          font.pixelSize: Style.font.caption
          color: Qt.alpha(root.ink, 0.8)
        }
        Ui.Button {
          id: serviceAction
          objectName: "pluginServiceAction"
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          visible: !!serviceRow.modelData.action || serviceRow.modelData.state === "setup"
          text: root.host.text("service." + (serviceRow.modelData.action || "instructions"))
          fontFamily: root.host.themeFont
          fontSize: Style.font.caption
          horizontalPadding: Style.space(5)
          verticalPadding: Style.space(1)
          foreground: root.ink
          focusable: true
          enabled: root.available
          onClicked: {
            if (serviceRow.modelData.action) root.host.invoke("service-" + serviceRow.modelData.action, root.plugin.id, "", serviceRow.modelData.unit)
            else root.host.invoke("about", root.plugin.id)
          }
        }
      }
    }
    Column {
      width: parent.width
      visible: root.expanded
      spacing: Style.space(4)
      Repeater {
        model: root.plugin.isBarWidget ? root.plugin.instances : []
        delegate: Row {
          required property var modelData
          id: location
          objectName: "pluginMoveInstance"
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
      Repeater {
        model: ["about", "author-github", "author-x"]
        delegate: Row {
          id: linkRow
          required property string modelData
          visible: !root.confirming
          spacing: Style.space(4)
          height: Math.max(visit.height, copy.height)
          Ui.Button {
            id: visit
            objectName: "pluginLink_" + linkRow.modelData
            anchors.verticalCenter: parent.verticalCenter
            text: root.host.text("plugin.link." + linkRow.modelData)
            horizontalPadding: Style.space(4)
            verticalPadding: Style.space(2)
            fontFamily: root.host.themeFont
            foreground: root.ink
            focusable: true
            enabled: root.available
            onClicked: root.host.invoke(linkRow.modelData, root.plugin.id)
          }
          Ui.PanelActionButton {
            id: copy
            objectName: "pluginCopyLink_" + linkRow.modelData
            anchors.verticalCenter: parent.verticalCenter
            iconText: "󰆏"
            tooltipText: root.host.text("plugin.copy." + linkRow.modelData)
            Accessible.name: tooltipText
            fontFamily: root.host.themeFont
            foreground: root.ink
            focusable: true
            enabled: root.available
            onClicked: root.host.invoke("copy-" + linkRow.modelData, root.plugin.id)
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
        text: root.confirmingPause ? root.host.text("plugin.pauseManagerHelp").arg(root.plugin.id)
          : "Uninstall " + root.plugin.name + "? This removes its local plugin checkout."
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
          objectName: "pluginConfirmAction"
          text: root.confirmingPause ? root.host.text("plugin.confirmPause") : "Confirm uninstall"
          horizontalPadding: Style.space(4)
          verticalPadding: Style.space(2)
          fontFamily: root.host.themeFont
          foreground: root.ink
          focusable: true
          enabled: !root.host.busy
          onClicked: root.host.invoke(root.confirmingPause ? "disable" : "remove", root.plugin.id, "", "", -1, true)
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
