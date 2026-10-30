"""Compile the actual observer selector for three observed Storage tabs."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_storage_tab_raycast_is_limited_to_exact_observed_owner(tmp_path):
    compiler = shutil.which('clang++') or shutil.which('g++')
    if compiler is None:
        pytest.skip('C++ compiler unavailable')
    source = (Path(__file__).resolve().parents[1]/'overlays/angle-g3/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp').read_text(encoding='utf-8')
    helpers = source[source.index('bool EndsWith('):source.index('bool IsArchivesRewardMarker(')]
    program = '#include <string_view>\n#include <string>\n#include <array>\n#include <algorithm>\n#include <cassert>\n'+helpers+r'''
int main() {
  const std::string summary="OverlayCamera/Overlay/UIMain/StoreHouseDestroyConfirmView(Clone)/frame/";
  for (const std::string name : {"confirm_btn", "cancel_btn"}) {
    assert(IsStorageEquipmentSummaryControl(name,summary+"actions/"+name));
    assert(ShouldEvaluateTopRaycast(name,summary+"actions/"+name));
    assert(!IsStorageEquipmentSummaryControl(name,summary+"actions/"+name+"/child"));
    assert(!IsStorageEquipmentSummaryControl(name,"OtherUI/"+name));
  }
  assert(IsStorageEquipmentSummaryControl("btnBack",summary+"top/btnBack"));
  assert(!IsStorageEquipmentSummaryControl("confirm_btn",summary+"top/btnBack"));
  const std::string cellRoot="UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/equipment_scrollview/equipment_grid/";
  assert(IsStorageEquipmentCellControl("0",cellRoot+"0"));
  assert(ShouldEvaluateTopRaycast("26",cellRoot+"26"));
  assert(!IsStorageEquipmentCellControl("",cellRoot));
  assert(!IsStorageEquipmentCellControl("1a",cellRoot+"1a"));
  assert(!IsStorageEquipmentCellControl("0",cellRoot+"0/frame"));
  assert(!IsStorageEquipmentCellControl("0","OtherUI/equipment_grid/0"));
  const std::string storage="UICamera/Canvas/UIMain/StoreHouseUI(Clone)/";
  for (const std::string layout : {"", "adapt/"}) {
    const std::string material=storage+layout+"item_scrollview";
    const std::string equipment=storage+layout+"equipment_scrollview";
    assert(IsStoreHouseScrollRoot(material));
    assert(IsStoreHouseScrollRoot(equipment));
    assert(!IsStoreHouseScrollRoot(equipment+"/child"));
    // Both bars exist. A hidden bar remains observable only when linked to
    // the current active list, so native Scroll.appear can return false.
    assert(StorageScrollbarMatchesActiveList(equipment+"/Scrollbar",false,1,equipment));
    assert(!StorageScrollbarMatchesActiveList(material+"/Scrollbar",false,1,equipment));
    assert(StorageScrollbarMatchesActiveList(material+"/Scrollbar",false,1,material));
    assert(!StorageScrollbarMatchesActiveList(equipment+"/Scrollbar",true,2,equipment));
    // For custom ScrollRects, an active parent list can prove the owner even
    // when the bar itself is hidden; no active parent means no fallback.
    assert(StorageScrollbarMatchesActiveList(equipment+"/Scrollbar",true,0,""));
    assert(!StorageScrollbarMatchesActiveList(equipment+"/Scrollbar",false,0,""));
    assert(!StorageScrollbarMatchesActiveList(equipment+"/Scrollbar/child",true,0,""));
  }
  assert(!StorageScrollbarMatchesActiveList("OtherUI/equipment_scrollview/Scrollbar",true,0,""));
  const std::string filter = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/buttons/index_button";
  assert(IsStorageEquipmentFilterControl("index_button",filter));
  assert(!IsStorageEquipmentFilterControl("purchase",filter));
  assert(!IsStorageEquipmentFilterControl("index_button",filter+"/child"));
  assert(!IsStorageEquipmentFilterControl("index_button","OtherUI/index_button"));
  const std::string rarity = "OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/layout/container/indexsort_rarity/bg/";
  for (const std::string name : {"tpl","1","2","3","4","5"}) {
    assert(IsEquipmentRarityFilterControl(name,rarity+name));
    assert(ShouldEvaluateTopRaycast(name,rarity+name));
    assert(!IsEquipmentRarityFilterControl("other",rarity+name));
    assert(!IsEquipmentRarityFilterControl(name,rarity+name+"/child"));
    assert(!IsEquipmentRarityFilterControl(name,"OtherUI/rarity/"+name));
  }
  assert(!IsEquipmentRarityFilterControl("6",rarity+"6"));
  for (const std::string name : {"ok","cancel"}) {
    const std::string footer="OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/layout/btns/";
    assert(IsEquipmentRarityFilterControl(name,footer+name));
    assert(ShouldEvaluateTopRaycast(name,footer+name));
    assert(!IsEquipmentRarityFilterControl(name,footer+name+"/child"));
  }
  const std::string root = "OverlayCamera/Overlay/UIMain/topItems/adapt/bottom_back/types/";
  for (const std::string name : {"material", "weapon", "design"}) {
    assert(ShouldEvaluateToggleTopRaycast(name, root+name));
    assert(!ShouldEvaluateToggleTopRaycast("other", root+name));
    assert(!ShouldEvaluateToggleTopRaycast(name, root+name+"/child"));
    assert(!ShouldEvaluateToggleTopRaycast(name, "OtherUI/types/"+name));
  }
  assert(!ShouldEvaluateToggleTopRaycast("purchase", root+"purchase"));
  for (const std::string name : {"confirm_button", "cancel_button"}) {
    const std::string panel = "OverlayCamera/Overlay/UIMain/topItems/adapt/select_panel/";
    assert(ShouldEvaluateTopRaycast(name, panel+name));
    assert(!ShouldEvaluateTopRaycast(name, panel+name+"/child"));
    assert(!ShouldEvaluateTopRaycast(name, "OtherUI/select_panel/"+name));
  }
  for (const auto &control : std::array<std::pair<std::string,std::string>,2>{{
      {"dispos","OverlayCamera/Overlay/UIMain/topItems/adapt/bottom_back/dispos"},
      {"index_button","OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/buttons/index_button"}}}) {
    assert(ShouldEvaluateTopRaycast(control.first,control.second));
    assert(!ShouldEvaluateTopRaycast("other",control.second));
    assert(!ShouldEvaluateTopRaycast(control.first,control.second+"/child"));
    assert(!ShouldEvaluateTopRaycast(control.first,"OtherUI/"+control.first));
  }
}
'''
    cpp=tmp_path/'storage_tabs.cpp';binary=tmp_path/'storage_tabs.exe'
    cpp.write_text(program,encoding='utf-8')
    subprocess.run([compiler,'-std=c++17',str(cpp),'-o',str(binary)],check=True,capture_output=True)
    subprocess.run([str(binary)],check=True,capture_output=True)
