import QtQuick
import QtQuick.Window
import QtTest
import Quickshell
import qs.Commons as Commons
import "PluginKinds.js" as Kinds

ShellRoot {
  QtObject {
    id: host
    property string themeFont: "JetBrainsMono Nerd Font"
    property var translations: Commons.Translations { directory: Qt.resolvedUrl("i18n") }
    function text(key) { return translations.t(key) }
  }
  Window {
    id: win
    visible: true
    width: 640
    height: 700
    color: Commons.Color.popups.background
    Column {
      x: 15; y: 15; width: win.width - 30; spacing: 15
      PluginKindFilter {
        id: filter
        width: parent.width
        host: host
        plugins: [{id:"widget", kinds:["bar-widget"], enabled:true}, {id:"bar", kinds:["bar"]},
          {id:"machine", kinds:["overlay"], enabled:true, favorite:true, update:{status:"available"}}, {id:"panel", kinds:["panel"]}, {id:"menu", kinds:["menu"]},
          {id:"worker", kinds:["service"], favorite:true, installed:false, update:{status:"rewritten"}}, {id:"manager", kinds:["service","bar-widget"], update:{status:"unchecked"}},
          {id:"unknown", kinds:["future-kind"]}]
      }
      PluginKindBadges { id: badges; width: parent.width; host: host; kinds: Kinds.keys }
    }
    TestCase {
      name: "PluginKindFilter"
      when: win.visible
      function init() { filter.close(); filter.values=Kinds.keys.slice(); badges.kinds=Kinds.keys.slice(); wait(50) }
      function test_default_all_kinds_and_labels() {
        compare(filter.filteredPlugins.length, 8)
        compare(filter.selectionLabel(), "All kinds")
        let icons = {}
        for (let kind of Kinds.keys) {
          let badge=findChild(badges,"kindBadge_"+kind)
          verify(badge !== null); verify(badge.visible)
          verify(host.text("kind."+kind+".label").indexOf("kind.") !== 0)
          icons[Kinds.icons[kind]]=true
        }
        compare(Object.keys(icons).length, 7)
        grabImage(win.contentItem).save(Qt.resolvedUrl("kind-badges.png").toString().replace(/^file:\/\//,""))
      }
      function test_any_selected_kind_and_no_duplicate_plugins() {
        filter.values=["overlay","service"]
        compare(filter.filteredPlugins.map(function(p){return p.id}).join(","),"machine,worker,manager")
        compare(filter.selectionLabel(),"2 selected")
      }
      function test_enabled_appears_first_and_filters_independently() {
        compare(filter.resolvedOptions[0].label, "Enabled")
        mouseClick(filter, filter.width / 2, filter.height / 2)
        tryCompare(filter, "popupOpen", true, 3000)
        wait(50)
        keyClick(Qt.Key_Return)
        compare(filter.selectionLabel(), "Enabled")
        compare(filter.filteredPlugins.map(function(p) { return p.id }).join(","), "widget,machine")
        filter.values = ["enabled", "overlay", "panel"]
        compare(filter.filteredPlugins.map(function(p) { return p.id }).join(","), "machine")
        filter.values = ["enabled"]
        compare(filter.filteredPlugins.length, 2)
        filter.selectAllKinds()
        compare(filter.filteredPlugins.length, 8)
      }
      function test_update_available_combines_with_enabled_and_kinds() {
        compare(filter.resolvedOptions[1].label, "Update Available")
        filter.values = ["updates"]
        compare(filter.selectionLabel(), "Update Available")
        compare(filter.filteredPlugins.map(function(p) { return p.id }).join(","), "machine,worker")
        filter.values = ["enabled", "updates"]
        compare(filter.selectionLabel(), "Enabled with updates")
        compare(filter.filteredPlugins.map(function(p) { return p.id }).join(","), "machine")
        filter.values = ["updates", "service"]
        compare(filter.filteredPlugins.map(function(p) { return p.id }).join(","), "worker")
      }
      function test_favorites_includes_saved_uninstalled_entries() {
        compare(filter.resolvedOptions[2].label, "Favorites")
        filter.values = ["favorites"]
        compare(filter.selectionLabel(), "Favorites")
        compare(filter.filteredPlugins.map(function(p) { return p.id }).join(","), "machine,worker")
        filter.values = ["favorites", "enabled"]
        compare(filter.filteredPlugins.map(function(p) { return p.id }).join(","), "machine")
      }
      function test_none_and_other_are_explicit() {
        filter.values=[]; compare(filter.filteredPlugins.length,0);compare(filter.selectionLabel(),"None selected")
        filter.values=["other"];compare(filter.filteredPlugins[0].id,"unknown")
        compare(Kinds.normalized(["<img src=x>"])[0],"other")
      }
      function test_multi_kind_badges_wrap_without_losing_a_kind() {
        badges.kinds=["bar-widget","service","overlay","bar-widget"]
        badges.width=150; wait(50)
        verify(findChild(badges,"kindBadge_bar-widget") !== null)
        verify(findChild(badges,"kindBadge_service") !== null)
        verify(findChild(badges,"kindBadge_overlay") !== null)
        verify(badges.height > findChild(badges,"kindBadge_overlay").height)
        badges.width=Qt.binding(function(){return badges.parent.width})
      }
      function option(item, value) {
        if(item.modelData && item.modelData.value === value) return item
        let children=item.children || []
        for(let child of children) { let found=option(child,value);if(found)return found }
        return null
      }
      function test_pointer_selection_keeps_dropdown_open() {
        filter.values=[]
        mouseClick(filter,filter.width/2,filter.height/2)
        tryCompare(filter,"popupOpen",true,3000)
        let row=null
        tryVerify(function(){row=option(win.contentItem,"enabled");return row!==null},3000)
        wait(50)
        mouseClick(row,row.width/2,row.height/2)
        compare(filter.values.length,1);compare(filter.values[0],"enabled")
        compare(filter.filteredPlugins.map(function(p){return p.id}).join(","),"widget,machine")
        verify(filter.popupOpen)
        grabImage(win.contentItem).save(Qt.resolvedUrl("kind-filter.png").toString().replace(/^file:\/\//,""))
        filter.close()
      }
      function cleanup() { console.log("KIND FILTER TEST",qtest_results.functionName,qtest_results.failed) }
      function cleanupTestCase() { console.log("KIND FILTER FAIL COUNT",qtest_results.failCount);Qt.callLater(function(){Qt.quit()}) }
    }
  }
}
