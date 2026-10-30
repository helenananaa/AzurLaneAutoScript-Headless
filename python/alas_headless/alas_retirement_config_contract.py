"""Fail-closed contract for ALAS retirement mode selection."""

from __future__ import annotations

from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


RETIREMENT_MODES = ("one_click_retire", "enhance", "old_retire")


@dataclass(frozen=True)
class AlasRetirementConfigSnapshot:
    mode: str

    @property
    def semantic_admitted(self) -> bool:
        """Whether Headless has a reviewed task transaction for this mode."""

        return self.mode in RETIREMENT_MODES

    def require_semantic_entry(self) -> None:
        """Require a recognized mode; each typed action still checks its own capability."""

        if not self.semantic_admitted:
            raise SemanticGateClosed(
                "Retirement.RetireMode has no implemented semantic entry"
            )


def validate_alas_retirement_config(*, mode: object) -> AlasRetirementConfigSnapshot:
    """Validate the complete pinned ALAS retirement mode declaration."""

    if type(mode) is not str or mode not in RETIREMENT_MODES:
        raise SemanticGateClosed(
            "Retirement.RetireMode is outside the pinned ALAS surface"
        )
    return AlasRetirementConfigSnapshot(mode=mode)
