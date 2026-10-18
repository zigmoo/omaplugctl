import QtQuick
import QtQuick.Controls as Controls
import Quickshell.Io
import qs.Commons as Commons
import qs.Ui as Ui

Column {
  id: root
  required property var host
  property var configData: ({options: [], selected: "", machine: ""})
  property string draftBinding: ""
  property string draftGroup: ""
  property string message: ""
  property bool failed: false
  readonly property bool busy: reader.running
  readonly property Item focusTarget: agentPicker
  readonly property var groups: {
    var seen = {}, result = []
    for (var i = 0; i < (configData.options || []).length; i++) {
      var option = configData.options[i]
      if (!seen[option.group]) { seen[option.group] = true; result.push({id: option.group, label: option.agentLabel}) }
    }
    return result
  }
  readonly property var models: (configData.options || []).filter(function(o) { return o.group === root.draftGroup })
  readonly property var draft: models.filter(function(o) { return o.id === root.draftBinding })[0] || ({})
  spacing: Commons.Style.space(12)
  onVisibleChanged: if (visible) load()
  Component.onCompleted: if (visible) load()
  function restoreBindings() {
    agentPicker.currentIndex = Qt.binding(function() { return root.groups.map(function(o) { return o.id }).indexOf(root.draftGroup) })
    modelPicker.currentIndex = Qt.binding(function() { return root.models.map(function(o) { return o.id }).indexOf(root.draftBinding) })
  }
  function load() { invoke("reviewer-config", "") }
  function invoke(action, id) {
    if (busy) return
    message = host.text(action === "set-reviewer" ? "config.saving" : "config.loading")
    failed = false
    reader.command = ["python3", host.helper, action].concat(id ? [id] : [])
    reader.running = true
  }
  Process {
    id: reader
    stdout: StdioCollector { id: output; waitForEnd: true }
    stderr: StdioCollector { id: errors; waitForEnd: true }
    onExited: {
      try {
        var result = JSON.parse(output.text)
        root.failed = !result.ok
        if (result.ok) {
          root.configData = result.config
          root.draftBinding = root.configData.selected || ""
          var selected = root.configData.options.filter(function(o) { return o.id === root.draftBinding })[0]
          root.draftGroup = selected ? selected.group : ""
          root.message = root.configData.message || ""
          Qt.callLater(root.restoreBindings)
        } else root.message = result.message || errors.text
      } catch (e) { root.failed = true; root.message = errors.text || String(e) }
    }
  }
  Text {
    text: root.host.text("config.title")
    textFormat: Text.PlainText
    color: Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Commons.Style.font.title
  }
  Text {
    objectName: "reviewerConfigSummary"
    width: parent.width
    text: root.host.text("config.current").arg(root.configData.machine || "…").arg(root.configData.currentLabel || "…")
    textFormat: Text.PlainText
    color: Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Commons.Style.font.body
    wrapMode: Text.WordWrap
  }
  Text {
    width: parent.width
    text: root.host.text("config.assent")
    textFormat: Text.PlainText
    color: Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Commons.Style.font.caption
    wrapMode: Text.WordWrap
  }
  Text {
    text: root.host.text("config.source")
    textFormat: Text.PlainText
    color: Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Commons.Style.font.caption
  }
  Row {
    spacing: Commons.Style.space(16)
    Repeater {
      model: ["dil", "omarchy"]
      Controls.RadioButton {
        id: sourceChoice
        required property string modelData
        objectName: "reviewerSource_" + modelData
        text: modelData === "dil" ? "DIL" : "Omarchy"
        checked: root.configData.sourceType === modelData
        enabled: !root.busy && (modelData !== "dil" || !!root.configData.dilAvailable)
        font.family: root.host.themeFont
        font.pixelSize: Commons.Style.font.body
        indicator: Rectangle {
          implicitWidth: Commons.Style.space(16)
          implicitHeight: implicitWidth
          x: sourceChoice.leftPadding
          y: (sourceChoice.height - height) / 2
          radius: width / 2
          color: "transparent"
          border.color: sourceChoice.enabled ? Commons.Color.popups.text : Qt.darker(Commons.Color.popups.text, 1.7)
          Rectangle {
            anchors.centerIn: parent
            width: parent.width / 2
            height: width
            radius: width / 2
            visible: sourceChoice.checked
            color: Commons.Color.accent
          }
        }
        contentItem: Text {
          text: sourceChoice.text
          textFormat: Text.PlainText
          font: sourceChoice.font
          color: Commons.Color.popups.text
          leftPadding: sourceChoice.indicator.width + Commons.Style.space(8)
          verticalAlignment: Text.AlignVCenter
        }
        onClicked: {
          checked = Qt.binding(function() { return root.configData.sourceType === sourceChoice.modelData })
          if (root.configData.sourceType !== modelData) root.invoke("set-reviewer-source", modelData)
        }
      }
    }
  }
  Text {
    text: root.host.text("config.harness")
    textFormat: Text.PlainText
    color: Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Commons.Style.font.caption
  }
  ThemedPicker {
    id: agentPicker
    objectName: "reviewerHarnessPicker"
    width: parent.width
    model: root.groups.map(function(o) { return o.label })
    enabled: !root.busy && root.groups.length > 0
    fontFamily: root.host.themeFont
    onActivated: function(index) {
      root.draftGroup = root.groups[index].id
      root.draftBinding = root.models.length ? root.models[0].id : ""
      root.restoreBindings()
    }
  }
  Text {
    text: root.host.text("config.model")
    textFormat: Text.PlainText
    color: Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Commons.Style.font.caption
  }
  ThemedPicker {
    id: modelPicker
    objectName: "reviewerModelPicker"
    width: parent.width
    model: root.models.map(function(o) { return o.label })
    enabled: !root.busy && root.models.length > 0
    fontFamily: root.host.themeFont
    onActivated: function(index) { root.draftBinding = root.models[index].id; root.restoreBindings() }
  }
  Text {
    width: parent.width
    text: root.draft.id ? root.host.text("config.effort").arg(root.draft.effort || "default") : ""
    textFormat: Text.PlainText
    color: Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Commons.Style.font.caption
  }
  Ui.Button {
    objectName: "saveReviewerButton"
    text: root.host.text("config.apply")
    enabled: !root.busy && !!root.draftBinding && root.draftBinding !== root.configData.selected
    fontFamily: root.host.themeFont
    foreground: Commons.Color.popups.text
    focusable: true
    onClicked: root.invoke("set-reviewer", root.draftBinding)
  }
  Text {
    width: parent.width
    text: root.message
    textFormat: Text.PlainText
    color: root.failed ? Commons.Color.urgent : Commons.Color.popups.text
    font.family: root.host.themeFont
    font.pixelSize: Commons.Style.font.caption
    wrapMode: Text.WordWrap
  }
}
