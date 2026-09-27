"""Typed Private Quarters overview ports; ALAS owns room and task flow."""
from dataclasses import dataclass
import re
import math
from typing import Mapping, Optional, Tuple
from .contracts import ActionReceipt, Point
from .errors import SemanticGateClosed, SemanticTargetMissing

ROOT = 'UICamera/Canvas/UIMain/SelectDorm3DUI(Clone)/'
LEVEL_UP_ROOT = 'OverlayCamera/Overlay/UIMain/LevelUpWindow/'


@dataclass(frozen=True)
class PrivateQuartersOverview:
    generation: int
    remaining: int
    capacity: int
    locale: str


@dataclass(frozen=True)
class PrivateQuartersCollider:
    instance_id: int
    name: str
    path: str
    is_trigger: bool
    world_center: Tuple[float, float, float]
    extents: Tuple[float, float, float]
    screen: Optional[Tuple[float, float, float]]
    input_point: Optional[Tuple[float, float]] = None
    raycast_top: Optional[bool] = None
    ui_clear: Optional[bool] = None
    nearest_id: int = 0
    ui_top_path: str = ''


@dataclass(frozen=True)
class PrivateQuartersPhysics:
    generation: int
    camera_path: str
    colliders: Tuple[PrivateQuartersCollider, ...]
    scene_handle: int = 0


@dataclass(frozen=True)
class PrivateQuartersPhysicsReceipt:
    semantic_id: str
    generation: int
    point: Point
    path: str
    collider_id: int
    camera_path: str
    ui_receiver: str = ''


class PrivateQuartersOracle:
    def private_quarters_entry_destination_visible(self) -> bool:
        return (self.private_quarters_room_visible()
                or self.observation_target_present('private-quarters/dialogue/continue'))

    def private_quarters_download_prompt_absent(self) -> bool:
        state = self.read_state()
        active = [b for b in state.buttons if b.active_in_hierarchy and b.active_and_enabled]
        if any('Msgbox' in b.path or 'MessageBox' in b.path for b in active):
            return False
        return (any(b.path == 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)' for b in active)
                or self.private_quarters_page_visible() or self.private_quarters_entry_destination_visible())

    def private_quarters_loading_visible(self) -> bool:
        state = self.read_state()
        if any(b.path == 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'
               and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons):
            return True
        if self.private_quarters_page_visible() or self.private_quarters_entry_destination_visible():
            return False
        raise SemanticGateClosed('Private Quarters loading surface is not yet identified')

    def private_quarters_intimacy_max(self) -> bool:
        if not self.private_quarters_room_visible():
            raise SemanticGateClosed('Private Quarters room is absent')
        ui = self.read_ui_state()
        path = 'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/base/top/favor_level/Text'
        values = [t for t in ui.texts if t.path == path and t.active_in_hierarchy
                  and t.active_and_enabled and not t.truncated]
        if len(values) != 1:
            raise SemanticGateClosed('Private Quarters intimacy progress is ambiguous')
        match = re.fullmatch(r'([0-9]+)/([1-9][0-9]*)', re.sub(r'<[^>]*>', '', values[0].text).strip())
        if match and int(match[1]) < int(match[2]):
            return False
        raise SemanticGateClosed('Private Quarters max-intimacy state is not yet reviewed')

    def private_quarters_new_jersey_visible(self) -> bool:
        physics = self.private_quarters_physics()
        path = 'xinzexi_noshoes(Clone)/all/Bip001/Bip001 Pelvis/Bip001 Spine/Bip001 Spine1/BodyCollider'
        targets = [c for c in physics.colliders if c.path == path]
        if len(targets) != 1:
            raise SemanticGateClosed('Private Quarters target collider is absent or ambiguous')
        screen = targets[0].screen
        return bool(screen is not None and screen[2] > 0
                    and 0 <= screen[0] < self.fingerprint.width
                    and 0 <= screen[1] < self.fingerprint.height)

    def private_quarters_loft_visible(self) -> bool:
        if not self.private_quarters_page_visible():
            return False
        state = self.read_state()
        floors = {b.path[len(ROOT + 'Map/'):].split('/')[0] for b in state.buttons
                  if b.path.startswith(ROOT + 'Map/floor_')
                  and b.active_in_hierarchy and b.active_and_enabled}
        if len(floors) != 1:
            raise SemanticGateClosed('Private Quarters current floor is absent or ambiguous')
        return floors == {'floor_2'}

    def click_private_quarters_page(self, direction: str) -> ActionReceipt:
        if direction not in ('left', 'right') or not self.private_quarters_page_visible():
            raise SemanticGateClosed('Private Quarters page navigation is unavailable')
        return self.click('private-quarters/page/' + direction)

    def private_quarters_interact_visible(self) -> bool:
        state = self.read_state()
        targets = [b for b in self._matches(state, 'private-quarters/interact')
                   if b.active_in_hierarchy and b.active_and_enabled]
        if not targets:
            return False
        if len(targets) != 1:
            raise SemanticGateClosed('Private Quarters touch choices are ambiguous')
        target = targets[0]
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('Private Quarters touch frames are incoherent')
        texts = [t for t in ui.texts if t.path == target.path+'/bg/Text' and t.active_in_hierarchy
                 and t.active_and_enabled and not t.truncated]
        icons = [i for i in ui.images if i.path == target.path+'/bg/Image' and i.active_in_hierarchy
                 and i.active_and_enabled and not i.truncated]
        if len(texts) != 1 or not texts[0].text.startswith('触摸') or len(icons) != 1 or icons[0].sprite != 'icon_touch':
            raise SemanticGateClosed('Private Quarters touch identity is unsupported')
        return target.actionable and not self._blocking_rules(state, 'private-quarters/interact')

    def click_private_quarters_interact(self) -> ActionReceipt:
        if not self.private_quarters_interact_visible():
            state = self.read_state()
            if not any(b.active_in_hierarchy and b.active_and_enabled
                       for b in self._matches(state, 'private-quarters/interact')):
                raise SemanticTargetMissing('Private Quarters touch control is absent')
            raise SemanticGateClosed('Private Quarters touch control is not actionable')
        state = self.read_state()
        target = self._unique(state, 'private-quarters/interact')
        if (not target.actionable or target.raycast_top is not True or target.point is None
                or target.bounds is None or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'private-quarters/interact')):
            raise SemanticGateClosed('Private Quarters touch control is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before Private Quarters touch')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='private-quarters/interact', generation=state.generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def click_private_quarters_new_jersey_body(self) -> PrivateQuartersPhysicsReceipt:
        physics = self.private_quarters_physics()
        path = 'xinzexi_noshoes(Clone)/all/Bip001/Bip001 Pelvis/Bip001 Spine/Bip001 Spine1/BodyCollider'
        targets = [c for c in physics.colliders if c.path == path]
        if len(targets) != 1:
            raise SemanticGateClosed('Private Quarters body collider is absent or ambiguous')
        target = targets[0]
        room_receiver = 'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/POVControl/Move'
        ui_qualified = target.ui_clear is True or (target.ui_clear is False and target.ui_top_path == room_receiver)
        if (physics.camera_path.rsplit('/', 1)[-1] != 'BackYardMainCamera'
                or target.raycast_top is not True or not ui_qualified
                or target.nearest_id != target.instance_id or target.input_point is None
                or target.screen is None or target.screen[2] <= 0):
            raise SemanticGateClosed('Private Quarters body raycast is not qualified')
        x, y = target.input_point
        if not (x.is_integer() and y.is_integer() and 0 <= x < self.fingerprint.width and 0 <= y < self.fingerprint.height):
            raise SemanticGateClosed('Private Quarters body point is invalid')
        state = self.read_state()
        if (state.scene_handle != physics.scene_handle or not physics.generation <= state.generation <= physics.generation+2
                or not any(b.path.endswith('Dorm3dMainUI(Clone)/UI/base/btn_back') and b.active_in_hierarchy for b in state.buttons)
                or any(b.active_in_hierarchy and b.active_and_enabled and not b.path.startswith(
                    'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/base/') for b in state.buttons)
                or self._blocking_rules(state, 'private-quarters/character/new-jersey')):
            raise SemanticGateClosed('Private Quarters body frame changed or is blocked')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before Private Quarters body input')
        self._tap(int(x), int(y))
        return PrivateQuartersPhysicsReceipt('private-quarters/character/new-jersey', physics.generation,
                                             Point(x, y), target.path, target.instance_id, physics.camera_path, target.ui_top_path)

    def private_quarters_physics(self) -> PrivateQuartersPhysics:
        """Read collider geometry, never authorization to click projected points."""
        state = self.read_state()
        if not any(b.path.endswith('Dorm3dMainUI(Clone)/UI/base/btn_back')
                   and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons):
            raise SemanticGateClosed('Private Quarters room is absent')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('Private Quarters physics frames are incoherent')
        data = ui.snapshot.get('private_quarters_physics')
        if (not isinstance(data, Mapping) or data.get('schema') != 'alas-headless.private-colliders/v1'
                or type(data.get('status')) is not int or data['status'] != 1):
            raise SemanticGateClosed('Private Quarters physics observation is unavailable')
        if data.get('truncated') is not False or type(data.get('error_count')) is not int or data['error_count']:
            raise SemanticGateClosed('Private Quarters physics observation is incomplete')
        camera = data.get('camera_path')
        rows = data.get('colliders')
        if not isinstance(camera, str) or not isinstance(rows, (list, tuple)):
            raise SemanticGateClosed('Private Quarters physics observation is malformed')
        def vector(value):
            if (not isinstance(value, (list, tuple)) or len(value) != 3 or any(
                    type(v) not in (int, float) or not math.isfinite(v) for v in value)):
                raise SemanticGateClosed('Private Quarters physics vector is malformed')
            return tuple(float(v) for v in value)
        colliders, ids = [], set()
        for row in rows:
            if (not isinstance(row, Mapping) or type(row.get('instance_id')) is not int
                    or not row['instance_id'] or row['instance_id'] in ids
                    or not isinstance(row.get('name'), str) or not row['name']
                    or not isinstance(row.get('path'), str) or not row['path']
                    or type(row.get('is_trigger')) is not bool or row.get('truncated') is not False):
                raise SemanticGateClosed('Private Quarters collider identity is incomplete or ambiguous')
            center, extents = vector(row.get('world_center')), vector(row.get('extents'))
            if any(v < 0 for v in extents):
                raise SemanticGateClosed('Private Quarters collider extents are invalid')
            screen = None if row.get('screen') is None else vector(row['screen'])
            ids.add(row['instance_id'])
            point = row.get('input_point')
            if point is not None:
                if (not isinstance(point, (list, tuple)) or len(point) != 2 or any(
                        type(v) not in (int, float) or not math.isfinite(v) for v in point)):
                    raise SemanticGateClosed('Private Quarters physics input point is malformed')
                point = tuple(float(v) for v in point)
            for key in ('raycast_top', 'ui_clear'):
                if row.get(key) is not None and type(row[key]) is not bool:
                    raise SemanticGateClosed('Private Quarters physics hit flag is malformed')
            nearest = row.get('nearest_id', 0)
            if type(nearest) is not int:
                raise SemanticGateClosed('Private Quarters physics hit identity is malformed')
            ui_top_path = row.get('ui_top_path', '')
            if not isinstance(ui_top_path, str):
                raise SemanticGateClosed('Private Quarters UI receiver identity is malformed')
            colliders.append(PrivateQuartersCollider(row['instance_id'], row['name'], row['path'],
                                                    row['is_trigger'], center, extents, screen, point,
                                                    row.get('raycast_top'), row.get('ui_clear'), nearest, ui_top_path))
        return PrivateQuartersPhysics(ui.generation, camera, tuple(colliders), state.scene_handle)

    def private_quarters_interact_check_visible(self) -> bool:
        state = self.read_state()
        root = 'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/ik/'
        backs = [b for b in state.buttons if b.path == root+'btn_back'
                 and b.active_in_hierarchy and b.active_and_enabled]
        cameras = [b for b in state.buttons if b.path == root+'Right/btn_camera'
                   and b.active_in_hierarchy and b.active_and_enabled]
        if not backs and not cameras:
            return False
        if len(backs) != 1 or len(cameras) != 1:
            raise SemanticGateClosed('Private Quarters IK view is incomplete or ambiguous')
        return cameras[0].actionable and not self._blocking_rules(state, 'private-quarters/room/back')

    def private_quarters_room_visible(self) -> bool:
        state = self.read_state()
        return any(b.active_in_hierarchy and b.active_and_enabled
                   for b in self._matches(state, 'private-quarters/room/back'))

    def private_quarters_room_back_control_identity(self) -> str:
        state = self.read_state()
        if self._private_quarters_level_up_present(state):
            target = self._private_quarters_level_up_target(state)
            return 'PRIVATE_QUARTERS_ROOM_BACK@' + target.path
        target = self._unique(state, 'private-quarters/room/back')
        if not target.actionable or self._blocking_rules(state, 'private-quarters/room/back'):
            raise SemanticGateClosed('Private Quarters room back is not actionable')
        return 'PRIVATE_QUARTERS_ROOM_BACK@' + target.path

    def click_private_quarters_room_back(self) -> ActionReceipt:
        state = self.read_state()
        if self._private_quarters_level_up_present(state):
            return self.click_private_quarters_level_up_close()
        target = self._unique(state, 'private-quarters/room/back')
        if (not target.actionable or target.raycast_top is not True or target.point is None
                or target.bounds is None or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'private-quarters/room/back')):
            raise SemanticGateClosed('Private Quarters room back is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before Private Quarters room back')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='private-quarters/room/back', generation=state.generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def _private_quarters_level_up_present(self, state) -> bool:
        return any(b.path.startswith(LEVEL_UP_ROOT) and b.active_in_hierarchy
                   and b.active_and_enabled for b in state.buttons)

    def _private_quarters_level_up_target(self, state):
        # The shared popup is owned here only over the real PrivateQuarters room.
        if not any(b.path == 'UICamera/Canvas/UIMain/Dorm3dMainUI(Clone)/UI/base/btn_back'
                   and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons):
            raise SemanticGateClosed('Private Quarters level-up room is absent')
        target = self._unique(state, 'private-quarters/level-up/close')
        if (target.path != LEVEL_UP_ROOT + 'bg' or not target.actionable
                or target.raycast_top is not True or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or target.point.x != round(target.point.x) or target.point.y != round(target.point.y)
                or self._blocking_rules(state, 'private-quarters/level-up/close')):
            raise SemanticGateClosed('Private Quarters level-up close is not actionable')
        return target

    def click_private_quarters_level_up_close(self, timeout_seconds=5.0) -> ActionReceipt:
        state = self.read_state()
        target = self._private_quarters_level_up_target(state)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before Private Quarters level-up close')
        self._tap(int(target.point.x), int(target.point.y))
        deadline = self._monotonic() + timeout_seconds
        while self._monotonic() < deadline:
            self._sleep(0.25)
            after = self.read_state()
            if after.generation <= state.generation or self._private_quarters_level_up_present(after):
                continue
            if not self._matches(after, 'private-quarters/room/back'):
                continue
            back = self._unique(after, 'private-quarters/room/back')
            if back.actionable and back.raycast_top is True and not self._blocking_rules(after, 'private-quarters/room/back'):
                return ActionReceipt(semantic_id='private-quarters/level-up/close',
                                     generation=state.generation, point=target.point,
                                     bounds=target.bounds, path=target.path)
        raise SemanticGateClosed('Private Quarters level-up close postcondition was not proven; input already sent')

    def click_private_quarters_new_jersey_dialogue(self) -> ActionReceipt:
        state = self.read_state()
        if not self._matches(state, 'private-quarters/dialogue/continue'):
            raise SemanticTargetMissing('Private Quarters dialogue control is absent')
        target = self._unique(state, 'private-quarters/dialogue/continue')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('Private Quarters dialogue frames are incoherent')
        names = [t for t in ui.texts if t.path.startswith(target.path+'/front/dialogue/')
                 and t.path.endswith('/content/name/Text') and t.active_in_hierarchy
                 and t.active_and_enabled and not t.truncated]
        if len(names) != 1 or re.sub(r'<[^>]*>', '', names[0].text).strip() != '新泽西':
            raise SemanticGateClosed('Private Quarters dialogue speaker is unsupported')
        content_path = names[0].path.removesuffix('/name/Text')
        content = [t for t in ui.texts if t.path == content_path and t.active_in_hierarchy
                   and t.active_and_enabled and not t.truncated and t.text.strip()]
        others = [b for b in state.buttons if b.active_in_hierarchy and b.active_and_enabled
                  and b.path.startswith(target.path+'/') and not b.path.endswith('/hide_ui_button')]
        if (len(content) != 1 or others or not target.actionable or target.raycast_top is not True
                or target.point is None or target.bounds is None or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'private-quarters/dialogue/continue')):
            raise SemanticGateClosed('Private Quarters dialogue is not a single actionable line')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before Private Quarters dialogue')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='private-quarters/dialogue/continue', generation=state.generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def private_quarters_new_jersey_unlocked(self) -> bool:
        if not self.private_quarters_page_visible():
            raise SemanticGateClosed('Private Quarters overview is absent')
        state = self.read_state()
        path = ROOT+'Map/floor_2/Xinzexi'
        matches = [b for b in state.buttons if b.path == path and b.active_in_hierarchy
                   and b.active_and_enabled]
        if len(matches) != 1:
            raise SemanticGateClosed('Private Quarters New Jersey room is absent or ambiguous')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('Private Quarters room frames are incoherent')
        icons = [i for i in ui.images if i.path == path+'/icon' and i.active_in_hierarchy
                 and i.active_and_enabled and not i.truncated]
        if len(icons) != 1 or icons[0].sprite != 'room_icon_xinzexi':
            raise SemanticGateClosed('Private Quarters room identity is unsupported')
        locks = [i for i in ui.images if i.path == path+'/front/lock/Image'
                 and i.active_in_hierarchy and i.active_and_enabled and not i.truncated]
        favor = [t for t in ui.texts if t.path == path+'/front/complete/favor/Text'
                 and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if len(locks) == 1 and locks[0].sprite == 'state_lock' and not favor:
            return False
        if locks or len(favor) != 1 or re.fullmatch(r'[0-9]+', favor[0].text.strip()) is None:
            raise SemanticGateClosed('Private Quarters room unlock state is unknown')
        return True

    def click_private_quarters_new_jersey(self) -> ActionReceipt:
        if not self.private_quarters_new_jersey_unlocked():
            raise SemanticGateClosed('Private Quarters New Jersey room is locked')
        state = self.read_state()
        target = self._unique(state, 'private-quarters/room/new-jersey')
        if (not target.actionable or target.raycast_top is not True or target.point is None
                or target.bounds is None or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'private-quarters/room/new-jersey')):
            raise SemanticGateClosed('Private Quarters room is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before Private Quarters room input')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='private-quarters/room/new-jersey', generation=state.generation,
                             point=target.point, bounds=target.bounds, path=target.path)

    def private_quarters_page_visible(self) -> bool:
        return any(b.path == ROOT+'Main/btn_back' and b.active_in_hierarchy
                   and b.active_and_enabled for b in self.read_state().buttons)

    def private_quarters_overview(self) -> PrivateQuartersOverview:
        state = self.read_state()
        back = [b for b in state.buttons if b.path == ROOT+'Main/btn_back'
                and b.active_in_hierarchy and b.active_and_enabled]
        if len(back) != 1:
            raise SemanticGateClosed('Private Quarters overview is absent or ambiguous')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation+2:
            raise SemanticGateClosed('Private Quarters overview frames are incoherent')
        def text(suffix):
            matches = [t for t in ui.texts if t.path == ROOT+suffix and
                       t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
            if len(matches) != 1:
                raise SemanticGateClosed('Private Quarters text is missing or ambiguous: '+suffix)
            return matches[0].text.strip()
        if text('Main/title/Text/en') != 'PRIVATE QUARTERS':
            raise SemanticGateClosed('Private Quarters title is unsupported')
        count = re.fullmatch(r'([0-9]+)/([1-9][0-9]*)', text('Main/stamina/Text'))
        if count is None or int(count[1]) > int(count[2]):
            raise SemanticGateClosed('Private Quarters daily count is malformed')
        locale = text('Main/btn_switch/switch/currentName')
        if not locale:
            raise SemanticGateClosed('Private Quarters locale is absent')
        if self._blocking_rules(state, 'private-quarters/observe'):
            raise SemanticGateClosed('Private Quarters overview is obscured')
        return PrivateQuartersOverview(state.generation, int(count[1]), int(count[2]), locale)

    def click_private_quarters_home(self) -> ActionReceipt:
        if not self.private_quarters_page_visible():
            raise SemanticGateClosed('Private Quarters overview is absent')
        state = self.read_state()
        target = self._unique(state, 'private-quarters/home')
        if (not target.actionable or target.raycast_top is not True or target.point is None
                or target.bounds is None or not target.bounds.contains(target.point)
                or self._blocking_rules(state, 'private-quarters/home')):
            raise SemanticGateClosed('Private Quarters home is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before Private Quarters input')
        self._tap(round(target.point.x), round(target.point.y))
        return ActionReceipt(semantic_id='private-quarters/home', generation=state.generation,
                             point=target.point, bounds=target.bounds, path=target.path)
