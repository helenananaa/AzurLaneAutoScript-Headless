"""Fail-closed contract for the pinned ALAS Research chooser surface."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from .semantic_oracle import SemanticGateClosed


RESEARCH_PRESET_FILTERS = (
    "custom",
    "series_9_blueprint_ta152",
    "series_9_blueprint_only",
    "series_9_ta152_only",
    "series_8_blueprint_305",
    "series_8_blueprint_only",
    "series_8_305_only",
    "series_7_blueprint_la9",
    "series_7_blueprint_only",
    "series_7_la9_only",
    "series_6_blueprint_203",
    "series_6_blueprint_only",
    "series_6_203_only",
    "series_5_blueprint_152",
    "series_5_blueprint_only",
    "series_5_152_only",
    "series_4_blueprint_tenrai",
    "series_4_blueprint_only",
    "series_4_tenrai_only",
    "series_3_blueprint_234",
    "series_3_blueprint_only",
    "series_3_234_only",
    "series_2_than_3_457_234",
    "series_2_blueprint_457",
    "series_2_blueprint_only",
    "series_2_457_only",
)
RESEARCH_RESOURCE_STRATEGIES = (
    "always_use",
    "only_05_hour",
    "only_no_project",
    "do_not_use",
)


@dataclass(frozen=True)
class AlasResearchConfigSnapshot:
    preset_filter: str
    custom_filter: str | None
    allow_delay: bool
    use_coin: str
    use_cube: str
    use_part: str


def _nonempty_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SemanticGateClosed(f"Research.{name} must be non-empty text")
    return value


def _resource_strategy(name: str, value: object, options: object) -> str:
    declaration = options.get(name, {}) if isinstance(options, Mapping) else {}
    declared = declaration.get("option", ()) if isinstance(declaration, Mapping) else ()
    installed_option = (
        isinstance(declared, (list, tuple))
        and isinstance(value, str)
        and value in declared
    )
    if not isinstance(value, str) or not value.strip() or (
        value not in RESEARCH_RESOURCE_STRATEGIES and not installed_option
    ):
        raise SemanticGateClosed(
            f"Research.{name} is not declared by the installed ALAS strategy surface"
        )
    return value


def validate_alas_research_allow_delay(value: object) -> bool:
    """Validate the delay switch at every branch that can postpone a project."""

    if type(value) is not bool:
        raise SemanticGateClosed("Research.AllowDelay must be a bool")
    return value


def validate_alas_research_selector_config(
    *,
    preset_filter: object,
    custom_filter: object,
    allow_delay: object,
    use_coin: object,
    use_cube: object,
    use_part: object,
    resource_options: object = None,
) -> AlasResearchConfigSnapshot:
    """Validate all six public fields before Research selection can branch."""

    # Unknown non-empty preset names intentionally remain valid here.  The
    # pinned ALAS selector logs them and falls back to its generated default.
    preset = _nonempty_text("PresetFilter", preset_filter)
    # Only the custom branch reads CustomFilter.  Preset users can retain an
    # obsolete or empty custom expression without blocking project selection.
    custom = _nonempty_text("CustomFilter", custom_filter) if preset == "custom" else None
    return AlasResearchConfigSnapshot(
        preset_filter=preset,
        custom_filter=custom,
        allow_delay=validate_alas_research_allow_delay(allow_delay),
        use_coin=_resource_strategy("UseCoin", use_coin, resource_options),
        use_cube=_resource_strategy("UseCube", use_cube, resource_options),
        use_part=_resource_strategy("UsePart", use_part, resource_options),
    )


__all__ = (
    "AlasResearchConfigSnapshot",
    "RESEARCH_PRESET_FILTERS",
    "RESEARCH_RESOURCE_STRATEGIES",
    "validate_alas_research_allow_delay",
    "validate_alas_research_selector_config",
)
