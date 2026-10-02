"""Compile the observer's narrow preparation-control selector."""

import pathlib
import shutil
import subprocess
import tempfile

import pytest


def test_native_repair_raycast_keeps_other_strategy_panels_out():
    compiler = shutil.which('clang++') or shutil.which('g++')
    if compiler is None:
        pytest.skip('C++ compiler unavailable')
    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'overlays/angle-g3/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp').read_text(encoding='utf-8')
    helpers = 'bool EndsWith' + source.split('bool EndsWith', 1)[1].split('bool ShouldEvaluateToggleTopRaycast', 1)[0]
    program = '#include <string_view>\n#include <string>\n#include <array>\n#include <algorithm>\n#include <cassert>\n' + helpers + '''
int main() {
    assert(ShouldEvaluateTopRaycast("bgNormal$", "UICamera/Canvas/UIMain/EventUI(Clone)/scrollRect$/content/0/bgNormal$"));
    assert(ShouldEvaluateTopRaycast("bgEmergence$", "UICamera/Canvas/UIMain/EventUI(Clone)/scrollRect$/content/12/bgEmergence$"));
    assert(!ShouldEvaluateTopRaycast("bgEmergence$", "OtherUI(Clone)/scrollRect$/content/0/bgEmergence$"));
    assert(!ShouldEvaluateTopRaycast("bgEmergence$", "EventUI(Clone)/scrollRect$/content/x/bgEmergence$"));
    assert(!ShouldEvaluateTopRaycast("bgNormal$", "EventUI(Clone)/scrollRect$/content/0/bgEmergence$"));
    assert(ShouldEvaluateTopRaycast("mouseChild", "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/adapt/middle/HeroContainer/info/sebao_root/mouseChild"));
    assert(!ShouldEvaluateTopRaycast("mouseChild", "OtherUI(Clone)/adapt/middle/HeroContainer/info/sebao_root/mouseChild"));
    assert(ShouldEvaluateTopRaycast("strategy", "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/adapt/middle/strategy"));
    assert(ShouldEvaluateTopRaycast("back_btn", "OverlayCamera/Overlay/UIMain/ChapterPreCombatUI(Clone)/adapt/top/back_btn"));
    assert(!ShouldEvaluateTopRaycast("back_btn", "OtherUI(Clone)/adapt/top/back_btn"));
    assert(ShouldEvaluateTopRaycast("use_button", "OverlayCamera/Overlay/UIMain/strategy_info/window/panel/actions/use_button"));
    assert(ShouldEvaluateTopRaycast("cancel_button", "OverlayCamera/Overlay/UIMain/strategy_info/window/panel/actions/cancel_button"));
    assert(!ShouldEvaluateTopRaycast("strategy", "OtherUI(Clone)/adapt/middle/strategy"));
    assert(!ShouldEvaluateTopRaycast("use_button", "OtherUI(Clone)/strategy_info/window/panel/actions/use_button"));
}
'''
    with tempfile.TemporaryDirectory(prefix='alas-repair-raycast-') as directory:
        cpp = pathlib.Path(directory) / 'selector.cpp'
        exe = pathlib.Path(directory) / 'selector.exe'
        cpp.write_text(program, encoding='utf-8')
        subprocess.run([compiler, '-std=c++17', str(cpp), '-o', str(exe)], check=True, capture_output=True)
        subprocess.run([str(exe)], check=True, capture_output=True)


def test_native_retirement_selector_is_scoped_to_real_controls():
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("C++ compiler unavailable")
    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / "overlays/angle-g3/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp").read_text(encoding="utf-8")
    selector = source.split("bool IsRetirementControl", 1)[1].split("bool IsCampaignPreparationSwitch", 1)[0]
    program = '''
#include <string_view>
#include <cassert>
bool EndsWith(std::string_view v, std::string_view s) {
    return v.size() >= s.size() && v.substr(v.size()-s.size()) == s;
}
bool IsRetirementControl''' + selector + '''
int main() {
    assert(IsRetirementControl("OverlayCamera/Overlay/UIMain/blur_panel/select_panel/quick_select"));
    assert(IsRetirementControl("OverlayCamera/Overlay/UIMain/DestoryInfoUI(Clone)/frame/confirm_button"));
    assert(IsRetirementControl("ResolveEquipmentUI(Clone)/main/cancel_btn"));
    assert(IsRetirementControl("UICamera/Canvas/UIOrigin/blur_panel/adapt/top/back"));
    assert(!IsRetirementControl("OtherCamera/Canvas/UIOrigin/blur_panel/adapt/top/back"));
    assert(!IsRetirementControl("OtherUI(Clone)/frame/confirm_button"));
    assert(!IsRetirementControl("ResolveEquipmentUI(Clone)/main/confirm_btn"));
}
'''
    with tempfile.TemporaryDirectory(prefix="alas-retirement-raycast-") as directory:
        cpp = pathlib.Path(directory) / "selector.cpp"
        exe = pathlib.Path(directory) / "selector.exe"
        cpp.write_text(program, encoding="utf-8")
        subprocess.run([compiler, "-std=c++17", str(cpp), "-o", str(exe)], check=True, capture_output=True)
        subprocess.run([str(exe)], check=True, capture_output=True)


def test_native_preparation_selector_accepts_only_the_reviewed_controls():
    compiler = shutil.which("clang++") or shutil.which("g++")
    if compiler is None:
        pytest.skip("C++ compiler unavailable")
    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / "overlays/angle-g3/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp").read_text(encoding="utf-8")
    selector = source.split("bool IsCampaignPreparationSwitch", 1)[1].split("bool ShouldEvaluateTopRaycast", 1)[0]
    program = '''
#include <string_view>
#include <string>
#include <cassert>
bool EndsWith(std::string_view value, std::string_view suffix) {
    return value.size() >= suffix.size() && value.substr(value.size()-suffix.size()) == suffix;
}
bool IsCampaignPreparationSwitch''' + selector + '''
int main() {
    assert(IsCampaignPreparationSwitch("Toggle", "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle"));
    assert(IsCampaignPreparationSwitch("Toggle", "UICamera/Canvas/UIOrigin/LevelInfoSPUI(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle"));
    assert(IsCampaignPreparationSwitch("sp", "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/Fixed/sp"));
    assert(IsCampaignPreparationSwitch("Item", "OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/SpList/Item"));
    assert(!IsCampaignPreparationSwitch("Item", "OtherView(Clone)/Window/Fixed/SpList/Item"));
    assert(IsCampaignPreparationSwitch("ButtonGO", "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonGO"));
    assert(!IsCampaignPreparationSwitch("ButtonGO", "OtherView(Clone)/Window/Fixed/ButtonGO"));
    assert(IsCampaignPreparationSwitch("switch_button", "LevelStageView(Clone)/bottom_stage/Normal/switch_button"));
    assert(IsCampaignPreparationSwitch("collapse", "LevelStageView(Clone)/right_stage/event/collapse"));
    assert(IsCampaignPreparationSwitch("click", "LevelStageView(Clone)/right_stage/event/detail/click"));
    assert(IsCampaignPreparationSwitch("icon", "LevelStageView(Clone)/right_stage/event/detail/items/item(Clone)/icon"));
    assert(!IsCampaignPreparationSwitch("icon", "OtherView(Clone)/right_stage/event/detail/items/item(Clone)/icon"));
    assert(!IsCampaignPreparationSwitch("sp", "OtherView(Clone)/panel/Fixed/sp"));
    assert(!IsCampaignPreparationSwitch("item", "LevelFleetSelectView(Clone)/panel/Fixed/sp/item"));
    assert(!IsCampaignPreparationSwitch("Toggle", "LevelStageInfoView(Clone)/panel/quickPlay"));
    assert(!IsCampaignPreparationSwitch("start_button", "LevelFleetSelectView(Clone)/panel/Fixed/start_button"));
}
'''
    with tempfile.TemporaryDirectory(prefix="alas-preparation-raycast-") as directory:
        cpp = pathlib.Path(directory) / "selector.cpp"
        exe = pathlib.Path(directory) / "selector.exe"
        cpp.write_text(program, encoding="utf-8")
        subprocess.run([compiler, "-std=c++17", str(cpp), "-o", str(exe)], check=True, capture_output=True)
        subprocess.run([str(exe)], check=True, capture_output=True)
