from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession
from alas_headless.oracle.storage import StorageMaterialItemsPending
from tests.test_game_tips_loading_presence import host
from tests.test_alas_config_branch_compatibility import method

@pytest.mark.parametrize('drift',[False,True])
def test_unrelated_unloaded_cell_does_not_disable_a_ready_t1_box(drift):
    backend,o,a=host(drift,'storage-bottom-items-r37.json')
    backend.ui['images']=[i for i in backend.ui['images'] if not i['path'].endswith('/item_grid/294/bg/icon_bg/icon')]
    backend.ui['image_count']=len(backend.ui['images'])
    s=AlasSemanticSession.__new__(AlasSemanticSession);s.open=lambda:a
    candidate=s.storage_box_candidate(1)
    assert candidate.slot=='311' and candidate.rarity==1
    assert not backend.taps


def test_incomplete_candidate_view_does_not_claim_no_boxes():
    backend,o,a=host(fixture='storage-bottom-items-r37.json')
    for i in backend.ui['images']:
        if i['sprite']=='30001':i['sprite']='different-material'
    backend.ui['images']=[i for i in backend.ui['images'] if not i['path'].endswith('/item_grid/294/bg/icon_bg/icon')]
    backend.ui['image_count']=len(backend.ui['images'])
    s=AlasSemanticSession.__new__(AlasSemanticSession);s.open=lambda:a
    with pytest.raises(StorageMaterialItemsPending):s.storage_box_candidate(1)
    assert not backend.taps

@pytest.mark.parametrize('recovers',[False,True])
def test_original_box_loop_owns_pending_screenshot_and_timeout(recovers):
    pending=StorageMaterialItemsPending('loading')
    candidate=object();timer=Mock();timer.start.return_value=timer
    timer.reached.side_effect=[False,False if recovers else True]
    session=SimpleNamespace(storage_box_candidate=Mock(side_effect=[pending,candidate]))
    run=method('module/storage/storage.py','StorageHandler','_storage_use_box_in_page',Timer=Mock(return_value=timer))
    h=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session,screenshot=Mock()),_storage_use_one_box=Mock(return_value=1))
    if recovers:
        assert run(h,1,1)==1
        assert h.device.screenshot.call_count==2
        h._storage_use_one_box.assert_called_once_with(candidate,1)
    else:
        with pytest.raises(StorageMaterialItemsPending):run(h,1,1)
        h._storage_use_one_box.assert_not_called()
