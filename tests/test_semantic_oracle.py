"""Compatibility imports for shared fixtures; regression cases live in sibling modules."""

from tests.semantic_support.campaign_fixtures import (
    make_campaign_map_backend as make_campaign_map_backend,
    make_event_preparation_backend as make_event_preparation_backend,
    make_live_eventsp_fleet_preparation_backend as make_live_eventsp_fleet_preparation_backend,
    make_live_eventsp_map_preparation_backend as make_live_eventsp_map_preparation_backend,
    make_normal_fleet_preparation_backend as make_normal_fleet_preparation_backend,
)
from tests.semantic_support.observer_fixtures import (
    COMPONENT as COMPONENT,
    DRIVER_REVISION as DRIVER_REVISION,
    FakeBackend as FakeBackend,
    PACKAGE as PACKAGE,
    make_button as make_button,
    make_buttons as make_buttons,
    make_current_raid_backend as make_current_raid_backend,
    make_image as make_image,
    make_oracle as make_oracle,
    make_snapshot as make_snapshot,
    make_text as make_text,
    make_toggle as make_toggle,
    make_ui as make_ui,
    set_commission_scroll_view as set_commission_scroll_view,
    set_enhancement_page as set_enhancement_page,
    set_retirement_selection as set_retirement_selection,
    set_retirement_settings as set_retirement_settings,
)
