import pathlib
import shutil
import subprocess
import tempfile

import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_text, make_ui, make_oracle


@pytest.mark.parametrize('raycast', [None, True, False])
def test_dock_controls_accept_native_owned_and_reject_covered(raycast):
    root = 'root/CommanderCatUI(Clone)/blur_panel/'
    dock = root + 'pages/CommanderCatDockUI(Clone)/box/'
    backend = FakeBackend([
        make_button(name, dock + name, raycast_top=raycast)
        for name in ('home', 'reserve_btn', 'boxes_btn')
    ] + [make_button('back_btn', root + 'top/back_btn', raycast_top=raycast)])
    backend.ui = make_ui([
        make_text(text, dock + suffix + '/Text')
        for suffix, text in [('home', '0/8'), ('boxes_btn', '0/10'), ('reserve_btn', '0/15'), ('capcity', '34/40')]
    ] + [make_text(text, root + 'top/res/' + key + '/Text')
         for key, text in [('gold', '65000'), ('1', '20'), ('2', '30'), ('3', '40')]])
    oracle = make_oracle(backend)
    if raycast is False:
        with pytest.raises(SemanticGateClosed):
            oracle.meowfficer_dock_state()
        assert not oracle.enabled('meowfficer/buy/enter')
    else:
        assert oracle.meowfficer_dock_state().purchased == 15
        assert oracle.enabled('meowfficer/buy/enter')


def test_native_purchase_raycast_selector_is_scoped():
    compiler = shutil.which('clang++') or shutil.which('g++')
    if compiler is None:
        pytest.skip('C++ compiler unavailable')
    root = pathlib.Path(__file__).resolve().parents[1]
    source = (root / 'overlays/angle-g3/src/libANGLE/renderer/null/Il2CppNamespaceProbe.cpp').read_text(encoding='utf-8')
    selector = 'bool IsMeowfficerPurchaseControl' + source.split('bool IsMeowfficerPurchaseControl', 1)[1].split('bool ShouldEvaluateTopRaycast', 1)[0]
    program = '''
#include <string>
#include <string_view>
#include <cassert>
bool EndsWith(std::string_view v, std::string_view s) {
    return v.size() >= s.size() && v.substr(v.size()-s.size()) == s;
}
''' + selector + '''
int main() {
    assert(IsMeowfficerPurchaseControl("reserve_btn", "UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/pages/CommanderCatDockUI(Clone)/box/reserve_btn"));
    assert(IsMeowfficerPurchaseControl("Button", "OverlayCamera/Overlay/UIMain/CommanderReserveUI(Clone)/frame/bg1/Button"));
    assert(!IsMeowfficerPurchaseControl("other", "CommanderReserveUI(Clone)/frame/bg1/Button"));
    assert(!IsMeowfficerPurchaseControl("Button", "OtherUI(Clone)/frame/bg1/Button"));
    assert(!IsMeowfficerPurchaseControl("Button", "CommanderReserveUI(Clone)/frame/bg2/Button"));
}
'''
    with tempfile.TemporaryDirectory() as directory:
        cpp, exe = pathlib.Path(directory) / 'selector.cpp', pathlib.Path(directory) / 'selector.exe'
        cpp.write_text(program, encoding='utf-8')
        subprocess.run([compiler, '-std=c++17', str(cpp), '-o', str(exe)], check=True, capture_output=True)
        subprocess.run([str(exe)], check=True, capture_output=True)
