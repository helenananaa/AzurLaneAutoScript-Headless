from tests.alas_test_source import patched_alas_root
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless.oracle.errors import SemanticGateClosed, SemanticTargetNotActionable


def original_feed_enter():
    path=patched_alas_root() / 'module/dorm/dorm.py'
    tree=ast.parse(path.read_text(encoding='utf8'))
    method=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='dorm_feed_enter')
    names=('DORM_CHECK','DORM_FEED_CHECK','DORM_FEED_ENTER','DORM_FEED_CANCEL',
           'DORM_MANAGE_CHECK','DORM_FURNITURE_SHOP_QUIT',
           'DORM_FURNITURE_SHOP_FIRST','DORM_FURNITURE_SHOP_FIRST_SELECTED')
    scope={name:name for name in names}
    scope.update(logger=SimpleNamespace(info=Mock()),SemanticTargetNotActionable=SemanticTargetNotActionable)
    exec(compile(ast.Module(body=[method],type_ignores=[]),str(path),'exec'),scope)
    return scope['dorm_feed_enter']


@pytest.mark.parametrize('case', ['statistics','unknown','stale','other-target','unclassified'])
def test_original_loop_recovers_only_classified_feed_refusal_with_fresh_statistics(case):
    state={'feed':True,'statistics':case=='statistics','panel':False,'attempts':0,'inputs':[]}
    oracle=SimpleNamespace(
        read_state=lambda:SimpleNamespace(generation=9 if case=='stale' else 11),
        enabled=lambda target: (state['feed'] if target=='dorm/feed' else
                                (case in ('statistics','stale') if target=='dorm/statistics/confirm' else False)))
    adapter=SimpleNamespace(open=lambda:SimpleNamespace(oracle=oracle))

    def click(button):
        state['attempts']+=1
        if state['attempts']==1:
            state['feed']=False
            if case=='unclassified':raise SemanticGateClosed('semantic target is not actionable')
            raise SemanticTargetNotActionable('dorm/feed/close' if case=='other-target' else 'dorm/feed',10)
        state['inputs'].append(button)
        state['panel']=True

    def additional(**_):
        assert state['statistics']
        state['statistics']=False
        state['feed']=True
        return True

    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,click=click),
        interval_clear=Mock(),loop=lambda **_:iter(range(4)),
        appear=lambda name,**_: name=='DORM_FEED_CHECK' and state['panel'],
        ui_additional=Mock(side_effect=additional))
    run=original_feed_enter()
    if case=='statistics':
        run(host)
        host.ui_additional.assert_called_once_with(get_ship=False)
        assert state['inputs']==['DORM_FEED_ENTER'] and state['panel']
    else:
        with pytest.raises(SemanticGateClosed):run(host)
        host.ui_additional.assert_not_called()
        assert state['inputs']==[]
