"""Complete, read-only Unity world-grid observations for the ALAS OS camera."""

from dataclasses import dataclass
from collections.abc import Mapping
import math
import re
from typing import Tuple

from .contracts import CampaignMapCellState, Point
from .errors import SemanticGateClosed, SemanticViewportReanchorRequired


@dataclass(frozen=True)
class OperationSirenMapAttachment:
    row: int
    column: int
    kind: str
    object_id: int
    path: str
    sprites: Tuple[Tuple[str, str], ...]


def reviewed_logging_tower(attachment: OperationSirenMapAttachment) -> bool:
    model = attachment.path + '/icon/model/xinxita(Clone)'
    return (attachment.kind == 'event' and attachment.object_id == 1101
            and len(attachment.sprites) == 5
            and frozenset(attachment.sprites) == frozenset((
                (model, 'xinxita1'), (model+'/0', 'xinxita'),
                (model+'/2', 'xinxita2'), (model+'/3', 'xinxita3'),
                (model+'/4', 'xinxita4'))))


@dataclass(frozen=True)
class OperationSirenMapGeometry:
    generation: int
    zone_name: str
    rows: int
    columns: int
    cells: Tuple[CampaignMapCellState, ...]
    attachments: Tuple[OperationSirenMapAttachment, ...]
    current_fleet: int = 0
    fleet_cells: Tuple[Tuple[int, str], ...] = ()
    unresolved_fog_images: Tuple[str, ...] = ()


@dataclass(frozen=True)
class OperationSirenMapSwipeIntent:
    name: str
    pixel_vector: tuple
    box: tuple
    duration_range: tuple
    geometry: OperationSirenMapGeometry
    blacklist_areas: tuple = ()


@dataclass(frozen=True)
class OperationSirenMapSwipeReceipt:
    semantic_id: str
    pre_generation: int
    proof_generation: int
    post_generation: int
    start: tuple
    end: tuple
    duration_ms: int
    handler_instance_id: int
    zone_name: str
    observed_displacement: tuple


class OpsiMapOracle:
    def operation_siren_map_geometry(self, zone_name: str, *, rows: int, columns: int):
        """Supply geometry and raw attachments; never infer event absence from a slice."""
        if not zone_name or any(isinstance(n, bool) or not isinstance(n, int)
                                or not 1 <= n <= limit
                                for n, limit in ((rows, 99), (columns, 26))):
            raise SemanticGateClosed('operation siren map dimensions or zone are malformed')
        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed('operation siren local-map identity is absent')
        before = self.read_state()
        ui = self.read_ui_state()
        if (not before.generation <= ui.generation <= before.generation + 2
                or ui.image_truncated or ui.skipped_count):
            raise SemanticGateClosed('operation siren map images are incomplete or incoherent')
        titles = [t for t in ui.texts if t.path.endswith('/top_stage/title/name')
                  and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
        if len(titles) != 1 or titles[0].text.strip() != zone_name:
            raise SemanticGateClosed('operation siren map zone does not match ALAS')
        root = 'LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/'
        pattern = re.compile(re.escape(root) + r'quads/world_quad_([0-9]+)_([0-9]+)/walk_quad$')
        cells = {}
        for image in ui.images:
            match = pattern.fullmatch(image.path)
            if match is None or not image.active_in_hierarchy or not image.active_and_enabled:
                continue
            raw_row, raw_column = map(int, match.groups())
            key = (raw_row, raw_column)
            point = image.raw.get('adb_point')
            if (key in cells or image.truncated or image.bounds is None
                    or not isinstance(point, Mapping)):
                raise SemanticGateClosed('operation siren map cell projection is absent or ambiguous')
            values = (point.get('x'), point.get('y'))
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                raise SemanticGateClosed('operation siren map native point is malformed')
            native = Point(*values)
            if not image.bounds.contains(native):
                raise SemanticGateClosed('operation siren map native point is outside its cell')
            cells[key] = CampaignMapCellState(raw_row + 1, raw_column + 1,
                chr(65 + raw_column) + str(raw_row + 1), image.path, native, image.bounds)
        expected = {(r, c) for r in range(rows) for c in range(columns)}
        if set(cells) != expected:
            raise SemanticGateClosed('operation siren map topology disagrees with ALAS zone shape')
        attachment_pattern = re.compile(re.escape(root) +
            r'cells/cell_([0-9]+)_([0-9]+)/attachments/([^/]+)_([0-9]+)(?:/|$)')
        groups = {}
        for image in ui.images:
            match = attachment_pattern.match(image.path)
            if match is None or not image.active_in_hierarchy or not image.active_and_enabled:
                continue
            row, column, kind, object_id = match.groups()
            row, column, object_id = int(row), int(column), int(object_id)
            if (row, column) not in cells or image.truncated:
                raise SemanticGateClosed('operation siren map attachment is malformed')
            base = root + f'cells/cell_{row}_{column}/attachments/{kind}_{object_id}'
            groups.setdefault((row, column, kind, object_id, base), []).append((image.path, image.sprite))
        attachments = tuple(OperationSirenMapAttachment(r+1,c+1,k,i,p,tuple(sorted(s)))
                            for (r,c,k,i,p),s in sorted(groups.items()))
        fleet_cells = []
        fleet_pattern = re.compile(re.escape(root) + r'cells/fleet_([1-4])/shadow$')
        for image in ui.images:
            match = fleet_pattern.fullmatch(image.path)
            if match is None or not image.active_in_hierarchy or not image.active_and_enabled:
                continue
            point = image.raw.get('adb_point')
            if image.truncated or not isinstance(point, Mapping):
                raise SemanticGateClosed('operation siren fleet native anchor is absent')
            values = (point.get('x'), point.get('y'))
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                raise SemanticGateClosed('operation siren fleet native anchor is malformed')
            candidates = [cell for cell in cells.values()
                          if math.hypot(cell.point.x-values[0], cell.point.y-values[1]) <= 0.05]
            if len(candidates) != 1:
                raise SemanticGateClosed('operation siren fleet does not join one native cell')
            fleet_cells.append((int(match.group(1)), candidates[0].node))
        # An active nontransparent fog layer may hide attachment images. Its
        # alpha/bounds do not prove per-cell visibility or event absence.
        unresolved_fog = tuple(image.path for image in ui.images
            if image.path.startswith(root+'cells/fogs/fog/')
            and image.active_in_hierarchy and image.active_and_enabled
            and (image.truncated or image.color[3] > 0 and (
                not isinstance(image.raw.get('inherited_alpha'),(int,float))
                or isinstance(image.raw.get('inherited_alpha'),bool)
                or not math.isfinite(image.raw['inherited_alpha'])
                or image.raw['inherited_alpha'] != 0)))
        current_fleet = self._operation_siren_current_fleet_from_ui_state(ui) if fleet_cells else 0
        if (len({i for i, _ in fleet_cells}) != len(fleet_cells)
                or fleet_cells and current_fleet not in {i for i, _ in fleet_cells}):
            raise SemanticGateClosed('operation siren fleet anchor is missing or ambiguous')
        return OperationSirenMapGeometry(ui.generation, zone_name, rows, columns,
                                        tuple(cells[key] for key in sorted(cells)), attachments,
                                        current_fleet, tuple(sorted(fleet_cells)), unresolved_fog)

    def operation_siren_map_drag_proof(self, start, end):
        """Observe the actual enabled DragLayer handler for ALAS' selected path."""
        if any(not isinstance(pair,(tuple,list)) or len(pair)!=2 for pair in (start,end)):
            raise SemanticGateClosed('operation siren drag endpoint shape is invalid')
        if any(isinstance(v,bool) or not isinstance(v,int) or not 0 <= v < limit
               for pair in (start,end) for v,limit in zip(pair,(1280,720))):
            raise SemanticGateClosed('operation siren drag endpoints are invalid')
        before=self.read_ui_state()
        ack=self._request('GET /v1/os-map-drag %d %d %d %d\n' % (*start,*end))
        if ack.get('status')!='ok' or ack.get('scope')!='read-only-os-map-drag':
            raise SemanticGateClosed('operation siren native drag proof is unavailable')
        for _ in range(20):
            self._sleep(0.1)
            ui=self.read_ui_state()
            proof=ui.snapshot.get('operation_siren_map_drag',{})
            if ui.generation<=before.generation or proof.get('endpoints')!=list((*start,*end)):
                continue
            handler='LevelCamera/Canvas/UIMain/LevelGrid/DragLayer'
            if (proof.get('status')!=1 or proof.get('handler_path')!=handler
                    or isinstance(proof.get('handler_instance_id'),bool)
                    or not isinstance(proof.get('handler_instance_id'),int)
                    or proof['handler_instance_id']==0):
                raise SemanticGateClosed('operation siren enabled drag handler is unavailable')
            samples=proof.get('samples')
            if not isinstance(samples,list) or len(samples)!=33:
                raise SemanticGateClosed('operation siren drag path proof is incomplete')
            reward_obscured = False
            for index,sample in enumerate(samples):
                if not isinstance(sample,Mapping):raise SemanticGateClosed('operation siren drag sample is malformed')
                fraction=index/32
                expected=(start[0]+fraction*(end[0]-start[0]),start[1]+fraction*(end[1]-start[1]))
                values=(sample.get('x'),sample.get('y'))
                if (any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)
                        or abs(v-e)>0.001 for v,e in zip(values,expected))
                        or not isinstance(sample.get('top_path'),str)):
                    raise SemanticGateClosed('operation siren drag path is obscured or unowned')
                path = sample['top_path']
                reward_roots = ('WorldAutoFightRewardUI(Clone)',
                                'OverlayCamera/Overlay/UIMain/WorldAutoFightRewardUI(Clone)')
                if sample.get('owned') is False and any(
                        path == root or path.startswith(root+'/') for root in reward_roots):
                    reward_obscured = True
                elif (sample.get('owned') is not True
                        or not (path == handler or path.startswith(handler+'/'))):
                    raise SemanticGateClosed('operation siren drag path is obscured or unowned')
            if reward_obscured:
                # No gesture: refresh through original Camera recovery so its
                # existing os_auto_search_quit owns this late reward popup.
                raise SemanticViewportReanchorRequired('auto-search reward covers the camera path')
            return ui.generation,proof
        raise SemanticGateClosed('operation siren fresh drag proof did not arrive')

    def operation_siren_map_swipe(self, expected, start, end, duration_ms):
        """Dispatch one reviewed OS camera gesture; ALAS owns subsequent scanning."""
        if self._swipe is None or not isinstance(expected,OperationSirenMapGeometry):
            raise SemanticGateClosed('operation siren map swipe capability is unavailable')
        if (start==end or isinstance(duration_ms,bool) or not isinstance(duration_ms,int)
                or duration_ms<=0):
            raise SemanticGateClosed('operation siren camera gesture has no movement or invalid duration')
        def identity(state):
            return (state.current_fleet,state.fleet_cells,
                    tuple((a.row,a.column,a.kind,a.object_id,a.path,a.sprites) for a in state.attachments))
        for attempt_index in range(30):
            blocked=self._blocking_rules(self.read_state(),'os/map/camera-swipe')
            if blocked:
                if any(r.blocker_id!='loading' for r in blocked):
                    raise SemanticGateClosed('operation siren map is obscured before camera swipe: '+','.join(r.blocker_id for r in blocked))
                self._sleep(0.1)
                continue
            before=self.operation_siren_map_geometry(expected.zone_name,rows=expected.rows,columns=expected.columns)
            if identity(before)!=identity(expected):
                raise SemanticGateClosed('operation siren logical map changed before camera swipe')
            proof_generation,proof=self.operation_siren_map_drag_proof(start,end)
            blocked=self._blocking_rules(self.read_state(),'os/map/camera-swipe')
            if not blocked:break
            if any(r.blocker_id!='loading' for r in blocked):
                raise SemanticGateClosed('operation siren map became obscured before camera swipe: '+','.join(r.blocker_id for r in blocked))
            self._sleep(0.1)
        else:
            raise SemanticGateClosed('operation siren loading did not clear before camera swipe')
        if self._foreground_component()!=self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before operation siren camera swipe')
        attempts=getattr(self,'_operation_siren_map_swipe_attempts',None)
        if attempts is None:
            attempts=[];self._operation_siren_map_swipe_attempts=attempts
        attempt={'zone_name':expected.zone_name,'pre_generation':before.generation,
                 'proof_generation':proof_generation,'start':start,'end':end,
                 'duration_ms':duration_ms,'handler_instance_id':proof['handler_instance_id'],
                 'dispatched':False,'postcondition_proven':False}
        attempts.append(attempt)
        self._swipe(*start,*end,duration_ms)
        attempt['dispatched']=True
        for _ in range(12):
            self._sleep(0.25)
            after=self.operation_siren_map_geometry(expected.zone_name,rows=expected.rows,columns=expected.columns)
            if after.generation<=proof_generation:continue
            if identity(after)!=identity(before):
                raise SemanticGateClosed('operation siren logical map changed during camera swipe')
            prior={c.node:c for c in before.cells}
            deltas=[(c.point.x-prior[c.node].point.x,c.point.y-prior[c.node].point.y) for c in after.cells]
            # Game-native centers prove movement; original ALAS resolves the new camera.
            delta=(sum(d[0] for d in deltas)/len(deltas),sum(d[1] for d in deltas)/len(deltas))
            if math.hypot(*delta)>1 and delta[0]*(end[0]-start[0])+delta[1]*(end[1]-start[1])>0:
                attempt.update(postcondition_proven=True,post_generation=after.generation,observed_displacement=delta)
                return OperationSirenMapSwipeReceipt('os/map/camera-swipe',before.generation,proof_generation,
                    after.generation,start,end,duration_ms,proof['handler_instance_id'],expected.zone_name,delta)
        raise SemanticGateClosed('operation siren camera swipe did not advance native map state')
