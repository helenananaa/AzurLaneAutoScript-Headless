import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter
from tests.semantic_support.observer_fixtures import FakeBackend,make_ui,make_oracle

def test_event_stage_structure_isolated_from_normal_chapter_parser():
    path=Path(__file__).resolve().parents[1]/'artifacts/semantic-cn-original-scheduler-r35-20260930.json'
    if not path.exists():pytest.skip('retained native event selector unavailable')
    r=json.loads(path.read_text(encoding='utf8'))['tasks'][-1]['failure_observation']
    b=FakeBackend(r['state']['buttons_snapshot']['buttons']);u=r['ui']['snapshot']
    b.ui=make_ui(u['texts'],images=u['images'],toggles=u['toggles']);o=make_oracle(b)
    # Page sprite lookup may be absent while the complete exact stage-node
    # and unique story-switch Button structure is already mounted.
    o.event_campaign_page_visible=Mock(return_value=False)
    o.campaign_page_is_normal=Mock(side_effect=AssertionError('foreign chapter'))
    a=AlasSemanticAdapter(o,package_gate=lambda:None)
    assert a._campaign_notice_navigation_surface() is True
    o.campaign_page_is_normal.assert_not_called()
    assert b.taps==[]
