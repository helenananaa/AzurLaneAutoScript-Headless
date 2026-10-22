"""Run the materialized ALAS Scroll loop through its typed one-drag boundary."""
import ast
from types import SimpleNamespace
from unittest.mock import Mock
import numpy as np
from alas_headless.oracle.storage import StorageOracle
from tests.test_alas_config_branch_compatibility import source


def test_original_scroll_loop_owns_partial_progress_retries_and_screenshot_timing():
    node=next(n for n in ast.parse(source('module/ui/scroll.py')).body
              if isinstance(n,ast.ClassDef) and n.name=='Scroll')
    scope={'np':np,'logger':Mock()}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'native-ALAS-Scroll','exec'),scope)
    cls=scope['Scroll']
    states=[SimpleNamespace(direction=2,value=v,size=.1,
                           controls=(SimpleNamespace(active_in_hierarchy=True),))
            for v in (1,.023749,0)]
    session=SimpleNamespace(storage_material_scroll_state=Mock(side_effect=states),
                            storage_material_scroll_drag_toward=Mock(),
                            open=lambda:SimpleNamespace(oracle=StorageOracle))
    main=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session,
                          screenshot=Mock(),swipe=Mock(side_effect=AssertionError('raw input'))))
    scroll=cls.__new__(cls)
    scroll.name='METERIAL_SCROLL';scroll.total=500;scroll.length=50
    scroll.drag_interval=Mock();scroll.drag_interval.reached.return_value=True
    scroll.drag_timeout=Mock()
    assert scroll.set(1,main)==2
    assert session.storage_material_scroll_drag_toward.call_count==2
    assert all(call.args==(1.,) for call in session.storage_material_scroll_drag_toward.call_args_list)
    assert main.device.screenshot.call_count==2
    main.device.swipe.assert_not_called()



def test_native_box_loop_owns_use_amount_and_screenshots_without_pixels():
    from tests.test_alas_config_branch_compatibility import method
    candidate=object()
    session=SimpleNamespace(storage_box_candidate=Mock(return_value=candidate))
    timer=Mock();timer.start.return_value=timer;timer.reached.return_value=False
    run=method('module/storage/storage.py','StorageHandler','_storage_use_box_in_page',
               Timer=Mock(return_value=timer),rgb2gray=Mock(side_effect=AssertionError('pixels')))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session,screenshot=Mock()),
                         _storage_use_one_box=Mock(return_value=3))
    assert run(host,1,3)==3
    session.storage_box_candidate.assert_called_once_with(1)
    host._storage_use_one_box.assert_called_once_with(candidate,3)
    assert host.device.screenshot.call_count==1


def test_missing_optional_box_capability_remains_local_to_research():
    import pytest
    from alas_headless import AlasSemanticUnmapped
    from alas_headless.adapter.task_lifecycle import semantic_task_scope,TaskCapabilityUnavailable
    from tests.test_alas_config_branch_compatibility import method
    timer=Mock();timer.start.return_value=timer;timer.reached.return_value=False
    run=method('module/storage/storage.py','StorageHandler','_storage_use_box_in_page',Timer=Mock(return_value=timer))
    storage=SimpleNamespace(storage_box_candidate=Mock(side_effect=AlasSemanticUnmapped('typed box unavailable')))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=storage,screenshot=Mock()))
    session=SimpleNamespace(discard_task_state=Mock(),trace=None)
    with pytest.raises(TaskCapabilityUnavailable,match='typed box unavailable'):
        with semantic_task_scope(session,'research'):run(host,1,15)
    with semantic_task_scope(session,'commission'):pass
    assert session.last_task_outcome['outcome']=='returned'
