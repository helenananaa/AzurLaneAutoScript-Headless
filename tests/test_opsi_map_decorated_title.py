"""The geometry reader compares the same zone identity as native ALAS."""
import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from tests.test_semantic_oracle_opsi_map_geometry import setup_map


@pytest.mark.parametrize('title', [
    '东北航道A','东北航道A-安全海域','东北航道A-普通海域',
    ' 东北航道A - 危险海域 ','东北航道A-新增状态描述',
])
def test_native_zone_identity_accepts_harmless_title_decoration(title):
    backend,oracle=setup_map()
    backend.ui['texts'][0]['text']=title
    result=oracle.operation_siren_map_geometry('东北航道A',rows=3,columns=3)
    assert result.zone_name=='东北航道A' and len(result.cells)==9
    assert backend.taps==[] and backend.swipes==[]


@pytest.mark.parametrize('fault',['wrong-zone','ambiguous','truncated','wrong-topology'])
def test_decoration_never_admits_another_zone_or_incomplete_proof(fault):
    backend,oracle=setup_map()
    backend.ui['texts'][0]['text']='东北航道A-安全海域'
    if fault=='wrong-zone': backend.ui['texts'][0]['text']='东北航道B-安全海域'
    elif fault=='ambiguous':
        backend.ui['texts'].append(dict(backend.ui['texts'][0]));backend.ui['text_count']+=1
    elif fault=='truncated': backend.ui['texts'][0]['flags'] |= 0x10
    with pytest.raises(SemanticGateClosed):
        oracle.operation_siren_map_geometry('东北航道A',rows=4 if fault=='wrong-topology' else 3,columns=3)
    assert backend.taps==[] and backend.swipes==[]


def test_retained_r63_decorated_map_title_keeps_complete_native_geometry():
    from alas_headless.semantic_oracle import SemanticOracle,OracleFingerprint
    from tests.semantic_support.observer_fixtures import FakeBackend
    path=Path(__file__).resolve().parents[1]/'artifacts/continuity-20261004/goal-scheduler-r63.json'
    if not path.exists(): pytest.skip('retained r63 live frame unavailable')
    task=json.loads(path.read_text(encoding='utf8'))['tasks'][-1]
    frame=task['failure_leased_frame'];backend=FakeBackend([])
    backend.snapshot=frame['snapshot'];backend.buttons=frame['buttons_snapshot']
    backend.ui=task['failure_observation']['ui']['snapshot']
    # Adjacent live endpoints become one static replay generation; retained
    # semantic contents and original evidence files are unchanged.
    for snapshot in (backend.snapshot,backend.buttons,backend.ui):
        snapshot['generation']=backend.ui['generation']
    oracle=SemanticOracle(backend.request,backend.foreground_component,backend.tap,
        OracleFingerprint(package=backend.snapshot['package'],component=backend.foreground,
            driver_revision=backend.snapshot['driver_revision'],expected_pid=backend.snapshot['pid']))
    import re
    cells=[re.search(r'/world_quad_(\d+)_(\d+)/walk_quad$',image['path'])
        for image in backend.ui['images'] if image['active_in_hierarchy']]
    cells=[match for match in cells if match]
    rows=max(int(match[1]) for match in cells)+1
    columns=max(int(match[2]) for match in cells)+1
    assert (rows,columns)==(8,18)  # Native ALAS zone143 shape R8.
    result=oracle.operation_siren_map_geometry('东北航道C',rows=rows,columns=columns)
    assert len(result.cells)==rows*columns
    assert result.zone_name=='东北航道C'
    assert backend.taps==[] and backend.swipes==[]
