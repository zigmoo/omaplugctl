import QtQuick

ListView {
  id: root
  property real wheelStep: 56

  property real _lastWheelAt: 0
  property int _wheelDirection: 0
  property real _wheelSpeed: 1

  function resetWheel() {
    _lastWheelAt = 0
    _wheelDirection = 0
    _wheelSpeed = 1
  }

  onVisibleChanged: resetWheel()
  onInteractiveChanged: resetWheel()

  // Behind the content, so nested controls receive wheel events first.
  // Follow the viewport without intercepting clicks, drags or hover.
  MouseArea {
    parent: root.contentItem
    x: root.contentX
    y: root.contentY
    width: root.width
    height: root.height
    z: -1
    enabled: root.interactive
    acceptedButtons: Qt.NoButton
    scrollGestureEnabled: false

    onWheel: function(event) {
      event.accepted = false
      if (event.pixelDelta.x !== 0 || event.pixelDelta.y !== 0
          || event.angleDelta.x !== 0 || event.angleDelta.y === 0
          || event.modifiers !== Qt.NoModifier) {
        root.resetWheel()
        return
      }

      var now = Date.now()
      var direction = event.angleDelta.y > 0 ? 1 : -1
      var elapsed = now - root._lastWheelAt
      root._wheelSpeed = direction === root._wheelDirection && elapsed >= 0 && elapsed < 300
        ? Math.min(3, root._wheelSpeed + 0.25 * Math.min(1, Math.abs(event.angleDelta.y) / 120))
        : 1
      root._lastWheelAt = now
      root._wheelDirection = direction

      var top = root.originY - root.topMargin
      var bottom = Math.max(top, root.originY + root.contentHeight - root.height + root.bottomMargin)
      var next = Math.max(top, Math.min(bottom,
        root.contentY - event.angleDelta.y / 120 * root.wheelStep * root._wheelSpeed))
      if (next === root.contentY) {
        root.resetWheel()
        return
      }
      root.cancelFlick()
      root.contentY = next
      event.accepted = true
    }
  }
}
