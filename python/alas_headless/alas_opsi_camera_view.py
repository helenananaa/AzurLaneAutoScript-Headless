"""Supply typed visible grids to the original ALAS Operation Siren View port."""
from dataclasses import dataclass
import math
import numpy as np
from .alas_camera_view import _fit_projective_camera
from .oracle.errors import SemanticGateClosed
from .oracle.opsi_map import OperationSirenMapGeometry, reviewed_logging_tower


@dataclass(frozen=True)
class AlasOpsiCameraObservation:
    generation: int
    zone_name: str
    camera_location: tuple
    maximum_residual: float
    rms_residual: float
    visible_nodes: tuple


class AlasSemanticOpsiView:
    def __init__(self, state, config):
        # Reuse ALAS' native grids and selection/filter implementation. The
        # adapter supplies the observations their pixel predictor would fill.
        from module.map_detection.os_grid import OSGridInfo
        if not isinstance(state, OperationSirenMapGeometry):
            raise SemanticGateClosed('operation siren camera requires typed geometry')
        if state.unresolved_fog_images:
            raise SemanticGateClosed('operation siren rescan visibility unavailable: native fog layer may hide attachments')
        center, maximum, rms, self._projector = _fit_projective_camera(state, config.SCREEN_CENTER)
        camera = tuple(math.floor(v) for v in center)
        # This is the existing OS camera's viewport, used only for observation.
        visible = [c for c in state.cells if 239 <= c.point.x <= 993 and 128 <= c.point.y <= 628]
        if not visible:
            raise SemanticGateClosed('operation siren visible grid is absent')
        left = min(c.column-1 for c in visible); right=max(c.column-1 for c in visible)
        lower = min(c.row-1 for c in visible); upper=max(c.row-1 for c in visible)
        self._origin=np.array((left,lower),dtype=int)
        self.center_loca=tuple(np.array(camera)-self._origin)
        self.center_offset=np.array(center)-np.array(camera)
        self.shape=np.array((right-left,upper-lower),dtype=int)
        self.left_edge=left==0;self.right_edge=right==state.columns-1
        self.lower_edge=lower==0;self.upper_edge=upper==state.rows-1
        self.semantic_observation=AlasOpsiCameraObservation(state.generation,state.zone_name,camera,
            maximum,rms,tuple(c.node for c in visible))
        self.semantic_state=state
        self.grids={}
        fleets=dict(state.fleet_cells)
        for cell in visible:
            grid=OSGridInfo()
            grid.location=tuple(np.array((cell.column-1,cell.row-1))-self._origin)
            grid.button=(cell.bounds.left,cell.bounds.top,cell.bounds.right,cell.bounds.bottom)
            grid.outer=grid.button
            grid.semantic_path=cell.button_path
            grid.semantic_point=cell.point
            grid.semantic_bounds=cell.bounds
            grid.semantic_generation=state.generation
            grid.semantic_os_cell=(cell.column-1,cell.row-1)
            grid.semantic_os_zone=state.zone_name
            grid.semantic_os_dimensions=(state.rows,state.columns)
            grid.is_fleet=cell.node in fleets.values()
            grid.is_current_fleet=fleets.get(state.current_fleet)==cell.node
            grid.semantic_passable_decorations=()
            # Each record is a native ALAS OSGridInfo, not another map model.
            for attachment in state.attachments:
                if attachment.row!=cell.row or attachment.column!=cell.column:
                    continue
                # Reviewed island families have obstacle=6 and no event
                # action. Match each reviewed ID to its complete native model.
                island_model = ('1x1XWIsLand_1' if attachment.object_id in range(9051,9060)
                                else '1x1XWIsLand_2' if attachment.object_id in range(9071,9080)
                                else '1x1XWIsLand_3' if attachment.object_id in range(9031,9040)
                                else None)
                reviewed_island=(attachment.kind=='event' and island_model is not None
                    and attachment.sprites==((attachment.path+'/icon/model/'+island_model+'(Clone)', island_model),))
                reviewed_damaged_control=(attachment.kind=='event' and attachment.object_id in (5103,5204)
                    and attachment.sprites==((attachment.path+'/icon/model/qihouzhuangzhi_huai(Clone)', 'qihouzhuangzhi_huai'),))
                reviewed_stopped_reinforcement=(attachment.kind=='event' and attachment.object_id==5705
                    and attachment.sprites==((attachment.path+'/icon/model/fubiao1(Clone)', 'fubiao1'),))
                # Event 1101 is the native information collection device.
                # ALAS calls this LoggingTower and owns its interaction flow.
                logging_tower=reviewed_logging_tower(attachment)
                # Native event 10240202 is a chess-piece combat encounter
                # displayed through expedition_icon=211011, not an inert tile.
                reviewed_chess_enemy=(attachment.kind=='event' and attachment.object_id==10240202
                    and len(attachment.sprites)==2 and frozenset(attachment.sprites)==frozenset((
                        (attachment.path+'/live/icon/size/bg_m', 'zhong'),
                        (attachment.path+'/live/icon/pic', 'qz1'))))
                if reviewed_island:
                    grid.is_land=True
                elif reviewed_chess_enemy:
                    grid.is_enemy=True
                    grid.enemy_scale=2
                    grid.enemy_genre='Enemy'
                elif logging_tower:
                    grid.is_logging_tower=True
                    grid.is_enemy=True
                    grid.enemy_genre='LoggingTower'
                elif reviewed_damaged_control or reviewed_stopped_reinforcement:
                    # These stopped devices have no event_op, auto priority
                    # or compass event; obstacle 2 permits arrive/pass/leave.
                    # 5705 retains an inactive story effect, not an ALAS
                    # interaction target. Original event handling still owns
                    # any story actually opened by the game during movement.
                    grid.semantic_passable_decorations += (attachment,)
                else:
                    raise SemanticGateClosed('operation siren map attachment classification unavailable: '
                                             + attachment.path)
            def project(points, _location=np.array((cell.column-1,cell.row-1))):
                return self._projector.grid_to_screen(np.asarray(points,dtype=float)+_location)
            grid.grid2screen=project
            self.grids[grid.location]=grid
        # Match View.load's local center metric, rather than averaging offscreen cells.
        points=self._projector.grid_to_screen(np.array([[.5,0],[-.5,0],[0,.5],[0,-.5]])+np.array(camera))
        self.swipe_base=np.array([np.linalg.norm(points[0]-points[1]),np.linalg.norm(points[2]-points[3])])
        self.semantic_swipe_prediction=True

    def __iter__(self):return iter(self.grids.values())
    def __contains__(self,location):return tuple(location) in self.grids
    def __getitem__(self,location):return self.grids[tuple(location)]
    def select(self,**conditions):
        from module.map.map_grids import SelectedGrids
        return SelectedGrids([g for g in self if all(getattr(g,k)==v for k,v in conditions.items())])
    def predict(self):pass
    def show(self):pass
    def predict_swipe(self,current,**kwargs):
        if not isinstance(current,AlasSemanticOpsiView) or current.semantic_state.zone_name!=self.semantic_state.zone_name:
            raise SemanticGateClosed('operation siren swipe lost the owned map')
        return tuple(np.array(current.semantic_observation.camera_location)-np.array(self.semantic_observation.camera_location))


def install_alas_opsi_camera_view(owner, state):
    view=AlasSemanticOpsiView(state,owner.config)
    owner.view=view
    camera=view.semantic_observation.camera_location
    if not 0 <= camera[0] < state.columns or not 0 <= camera[1] < state.rows:
        # Complete coherent geometry still defines the native swipe projection.
        # Report View.load's existing condition to ALAS' own camera recovery;
        # never clamp the observed camera or hide an invalid/unknown map.
        from module.exception import MapDetectionError
        offset=tuple(value if value < 0 else max(value-size+1,0)
                     for value,size in zip(camera,(state.columns,state.rows)))
        raise MapDetectionError(f'Camera outside map: offset={offset}')
    if getattr(owner,'_prev_view',None) is None:
        owner.camera=view.semantic_observation.camera_location
    owner.semantic_camera_view_observation=view.semantic_observation
    return view.semantic_observation
