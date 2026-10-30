"""Typed AP admission preserves the original caller's rest-of-day policy."""
from datetime import datetime,timedelta
from types import SimpleNamespace as N
from unittest.mock import Mock
import pytest
from alas_headless import SemanticOracleError,validate_alas_opsi_action_point_purchase
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.oracle.contracts import OperationSirenActionPointState
from tests.test_alas_config_branch_compatibility import method


class ActionPointLimit(Exception):pass


@pytest.mark.parametrize('semantic',[False,True])
@pytest.mark.parametrize('hour,minute,current,check,keep,expected',[
    (20,0,190,True,True,True),  # Current+24 remaining points exceeds200.
    (20,0,190,False,True,'preserve'),  # Caller did not request rest check.
    (23,0,190,True,True,'preserve'),  # Only6 points remain today.
    (20,0,176,True,True,True),  # Native threshold is >=200, including equality.
    (1,20,100,True,True,True),  # After midnight native rest check can allow it.
    (23,0,190,False,False,True),  # Caller already disabled preservation.
])
def test_original_ap_policy_and_typed_branch_agree(semantic,hour,minute,current,check,keep,expected):
    now=datetime(2026,10,29,hour,minute)
    midnight=datetime.combine(now.date()+timedelta(days=1),datetime.min.time())
    run=method('module/os_handler/action_point.py','ActionPointHandler','handle_action_point',
        datetime=N(now=lambda:now),get_server_next_update=lambda _:midnight,logger=Mock(),
        SemanticOracleError=SemanticOracleError,AlasSemanticActionDeferred=AlasSemanticActionDeferred,
        validate_alas_opsi_action_point_purchase=validate_alas_opsi_action_point_purchase,
        ActionPointLimit=ActionPointLimit)
    state=OperationSirenActionPointState(10,current,(0,0,0,0),1,None,None,None,None)
    closed=[]
    adapter=N(operation_siren_action_point_state=lambda:state,
        click_operation_siren_action_point_control=lambda consume:closed.append(consume))if semantic else None
    host=N(device=N(semantic_adapter=adapter),config=N(OS_ACTION_POINT_BOX_USE=True,
        OS_ACTION_POINT_PRESERVE=200,OpsiGeneral_BuyActionPointLimit=0,OpsiGeneral_OilLimit=1000),
        _is_in_action_point=lambda:True,action_point_safe_get=lambda:None,
        _action_point_current=current,_action_point_total=current,action_point_quit=lambda:closed.append(False))
    if expected=='preserve':
        with pytest.raises(ActionPointLimit):run(host,None,None,cost=70,keep_current_ap=keep,check_rest_ap=check)
    else:assert run(host,None,None,cost=70,keep_current_ap=keep,check_rest_ap=check)is True
    assert closed==[False]  # Never use AP items or purchase to satisfy this test.
