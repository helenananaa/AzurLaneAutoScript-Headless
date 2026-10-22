import copy
import pytest
from alas_headless import MissionDisposition, SemanticGateClosed
from alas_headless.adapter.legacy_environment import translate_legacy_semantic_environment
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_ui


def weekly(enabled=True):
    root = 'root/TaskScene(Clone)'
    path = root+'/pages/TaskListForWeekPage(Clone)/task_progress/get_btn'
    bounds = {'left':1094,'top':64,'right':1247,'bottom':218}
    backend = FakeBackend([make_button('back_btn',root+'/blur_panel/adapt/top/back_btn',58,53),
                           make_button('get_btn',path,1094,64,bounds,raycast_top=None)])
    images = [make_image(root+'/blur_panel/adapt/left_length/frame/tagRoot/weekly/selected/Image','icon_week_sel'),
              make_image(path,'get_btn',bounds),
              make_image(root+'/pages/TaskListForWeekPage(Clone)/right_panel/content/10025/frame/unfinish_bg','unfinish_frame')]
    if enabled:
        images.append(make_image(path+'/enable','finish_btn_tran_1',{'left':1191,'top':69,'right':1247,'bottom':125}))
    backend.ui = make_ui([],images=images)
    return backend,make_oracle(backend),path


def test_weekly_progress_is_original_single_claim_and_exact_input_port():
    backend,oracle,path=weekly()
    page=oracle.mission_page_state()
    assert page.disposition == MissionDisposition.CLAIMABLE_ROW
    assert [row.path for row in page.claim_rows] == [path]
    receipt=oracle.click_mission_claim_row(path)
    assert receipt.semantic_id == 'task/weekly-progress/claim'
    assert backend.taps == [(1170,141)]


def test_weekly_unfinished_marker_with_disabled_progress_has_no_claim():
    backend,oracle,_=weekly(False)
    assert oracle.mission_page_state().disposition == MissionDisposition.UNFINISHED
    assert backend.taps == []


@pytest.mark.parametrize('change',['unknown_marker','truncated','duplicate_enable','missing_selected'])
def test_unknown_weekly_surface_does_not_infer_safe_completion_or_input(change):
    backend,oracle,path=weekly(change not in ('unknown_marker',))
    if change=='unknown_marker':
        backend.ui['images'][2]['sprite']='unknown_future_state'
        assert oracle.mission_page_state().disposition == MissionDisposition.UNKNOWN
    else:
        if change=='truncated': backend.ui['image_truncated']=True
        elif change=='duplicate_enable': backend.ui['images'].append(copy.deepcopy(backend.ui['images'][-1]))
        else: backend.ui['images'][0]['sprite']='unknown_future_selected'
        with pytest.raises(SemanticGateClosed): oracle.mission_page_state()
    assert backend.taps == []


def test_mission_integer_budget_preserves_zero_and_once_compatibility():
    base={'ALAS_SEMANTIC_MODE':'1','ALAS_SEMANTIC_DRIVER_REVISION':'a'*40}
    assert translate_legacy_semantic_environment(base).grant('mission.claim') == 0
    assert translate_legacy_semantic_environment(dict(base,ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE='1')).grant('mission.claim') == 1
    assert translate_legacy_semantic_environment(dict(base,ALAS_SEMANTIC_MISSION_CLAIM_BUDGET='20')).grant('mission.claim') == 20
    with pytest.raises(SemanticGateClosed):
        translate_legacy_semantic_environment(dict(base,ALAS_SEMANTIC_MISSION_CLAIM_BUDGET='-1'))
