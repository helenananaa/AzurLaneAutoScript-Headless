import pytest
from alas_headless import AlasSemanticUnmapped
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


@pytest.mark.parametrize('ready',[False,True])
def test_exact_task_shell_proves_white_mail_home_alias_absent(ready):
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values['task/page/back']=True
    oracle.enabled_values['task/page/back']=ready
    assert adapter.appear(NamedButton('GOTO_MAIN_WHITE')) is False
    assert oracle.click_calls==[]


def test_unknown_page_keeps_white_home_probe_unmapped():
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    with pytest.raises(AlasSemanticUnmapped): adapter.appear(NamedButton('GOTO_MAIN_WHITE'))
    assert oracle.click_calls==[]
