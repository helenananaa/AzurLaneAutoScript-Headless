"""Bind original ALAS road/grid aliases while its real battle branch executes."""
import copy
from contextlib import contextmanager

from .alas_decision_preview import _native_map_overlay
from .alas_map_sync import AlasCampaignMapProjection
from .semantic_oracle import SemanticGateClosed


@contextmanager
def bind_alas_campaign_execution_map(campaign):
    """Share the existing typed projection with class-level RoadGrids aliases.

    ALAS owns all decisions and actions inside the scope. Preserve its resulting
    instance-map mutations, but restore class-level objects even on exceptions.
    No task loop, independent map model, input policy or execution lock is added.
    """
    if not isinstance(getattr(campaign, 'semantic_map_projection', None), AlasCampaignMapProjection):
        raise SemanticGateClosed('ALAS execution requires its typed map projection')
    with _native_map_overlay(campaign.MAP, campaign.map) as native_map:
        campaign.map = native_map
        try:
            yield
        finally:
            if campaign.map is native_map:
                campaign.map = copy.deepcopy(native_map)
