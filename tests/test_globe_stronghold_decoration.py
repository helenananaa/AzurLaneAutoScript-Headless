"""A decorative line sprite does not identify the selected Stronghold."""

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)


ROOT = 'OverlayCamera/Overlay/UIMain/top/'
PANEL = ROOT + 'SVFloatPanel(Clone)/point/'


def stronghold(line_sprite=''):
    backend = FakeBackend([make_button('back_button', ROOT + 'adapt/top_chapter/back_button', raycast_top=None)])
    values = {
        PANEL + 'line/bg/title/name/subText': '西北航道E-塞壬要塞海域',
        PANEL + 'line/bg/icon/marking/Text': '塞壬要塞',
        PANEL + 'line/bg/danger_text': '7',
        PANEL + 'line/bg/title/achievement/number': '4/5',
        ROOT + 'adapt/top_chapter/reset_coutdown/Text': '距离大型作战重置15天',
    }
    info = ROOT + 'adapt/right_chapter/line/display_panel/world_info/'
    for suffix, value in (('explore/achievement/number', '80/100'),
                          ('explore/pressing/number', '10'), ('explore/mileage/number', '20'),
                          ('power/bg/Number', '10000'), ('buff/buff_damage/Text', '50'),
                          ('buff/buff_health/Text', '60'), ('buff/buff_attack/Text', '70')):
        values[info + suffix] = value
    images = [('line/bg/icon', 'daxuanwo'), ('line/bg/icon/marking', 'mark_danger'),
              ('line/bg/icon/marking/mark_bg', 'mark_bg_danger'),
              ('line/bg/sairen', 'sairen_mask'), ('line/bg', 'bg_danger'),
              ('', 'click_point_danger')]
    backend.ui = make_ui([make_text(v, p) for p, v in values.items()],
        images=[make_image(PANEL + suffix if suffix else PANEL[:-1], sprite)
                for suffix, sprite in images])
    if line_sprite is not None:
        backend.ui['images'].append(make_image(PANEL + 'line', line_sprite))
        backend.ui['image_count'] += 1
    return backend, make_oracle(backend)


@pytest.mark.parametrize('sprite', ['', 'click_point_danger', 'updated_decoration', None])
def test_stronghold_recognition_survives_decorative_line_drift(sprite):
    backend, oracle = stronghold(sprite)
    state = oracle.operation_siren_globe_state()
    assert state.zone_name == '西北航道E' and state.zone_type == '塞壬要塞'
    assert not backend.taps and not backend.swipes


@pytest.mark.parametrize('case', ['missing-icon', 'duplicate-icon', 'wrong-point', 'stale', 'foreign'])
def test_actual_stronghold_identity_is_still_required(case):
    backend, oracle = stronghold()
    images = backend.ui['images']
    if case == 'missing-icon':
        images.pop(0)
        backend.ui['image_count'] -= 1
    elif case == 'duplicate-icon':
        images.append(dict(images[0]))
        backend.ui['image_count'] += 1
    elif case == 'wrong-point':
        next(i for i in images if i['path'] == PANEL[:-1])['sprite'] = 'click_point_safe'
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    else:
        backend.snapshot['package'] = 'other.package'
    with pytest.raises(SemanticGateClosed):
        oracle.operation_siren_globe_state()
    assert not backend.taps and not backend.swipes
