import json
from pathlib import Path
import pytest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_ui, make_oracle

@pytest.mark.parametrize('sprite,accepted', [('sea_day',True),('sea_tiger_2',True),('unknown',False),('',False)])
def test_event_map_entry_tolerates_sea_art_drift_with_full_structure(sprite,accepted):
    path=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r31-readonly-20260930.json'
    if not path.exists():pytest.skip('retained native event map unavailable')
    r=json.loads(path.read_text(encoding='utf8'))
    b=FakeBackend(r['state']['buttons_snapshot']['buttons'])
    u=r['ui']['snapshot']
    b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    sea=next(x for x in b.ui['images'] if x['path'].endswith('/plane/display/mask/sea'))
    sea['sprite']=sprite
    o=make_oracle(b)
    if accepted:assert o.campaign_is_in_map() is True
    else:
        with pytest.raises(SemanticGateClosed):o.campaign_map_entry_state()
    assert b.taps==[]

def test_event_map_missing_back_anchor_still_rejected():
    path=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-r31-readonly-20260930.json'
    if not path.exists():pytest.skip('retained native event map unavailable')
    r=json.loads(path.read_text(encoding='utf8'))
    b=FakeBackend(r['state']['buttons_snapshot']['buttons']);u=r['ui']['snapshot']
    b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles'])
    b.ui['images']=[x for x in b.ui['images'] if not x['path'].endswith('/back_button/mask/Image')]
    with pytest.raises(SemanticGateClosed):make_oracle(b).campaign_map_entry_state()
    assert b.taps==[]
